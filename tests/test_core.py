import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from provider_switcher import cli, core
from conftest import IDS, snapshot, database_dump


def execute(home, sql, params=(), db="state_5.sqlite"):
    with sqlite3.connect(home / db) as c:
        c.execute(sql, params)


@pytest.mark.parametrize(("raw", "shown"), [
    (r"C:\projects\x", r"C:\projects\x"),
    (r"\\?\C:\projects\x", r"C:\projects\x"),
    ("\\\\?\\C:\\中文\\" + "长路径" * 20, "C:\\中文\\" + "长路径" * 20),
    (r"\\server\share\x", r"\\server\share\x"),
    (r"\\?\UNC\server\share\x", r"\\server\share\x"),
    ("//?/C:/projects/x", "C:/projects/x"),
    ("//?/UNC/server/share/x", "//server/share/x"),
])
def test_display_path_removes_only_extended_prefix(raw, shown):
    assert core.display_path(raw) == shown


def test_cli_json_paths_are_display_only():
    original = {
        "home": r"\\?\C:\Codex",
        "threads": [{
            "cwd": r"\\?\C:\项目",
            "rollout_path": r"\\?\UNC\server\share\session.jsonl",
            "project_roots": [r"\\?\C:\项目", r"\\server\share"],
        }],
    }
    shown = cli.display_json_paths(original)
    assert shown["home"] == r"C:\Codex"
    assert shown["threads"][0]["cwd"] == r"C:\项目"
    assert shown["threads"][0]["rollout_path"] == r"\\server\share\session.jsonl"
    assert shown["threads"][0]["project_roots"] == [r"C:\项目", r"\\server\share"]
    assert original["home"] == r"\\?\C:\Codex"
    assert original["threads"][0]["rollout_path"].startswith("\\\\?\\")


def test_catalog_project_mapping_names_and_parent(home):
    cat = core.catalog(home)
    rows = {r["id"]: r for r in cat["threads"]}
    assert rows[IDS[0]]["name"] == "优化本地开发环境"
    assert rows[IDS[0]]["project_id"] == "project-1"
    assert rows[IDS[1]]["project_id"] == "project-1"
    assert rows[IDS[1]]["parent_id"] == IDS[0]
    assert rows[IDS[1]]["is_agent"]
    assert rows[IDS[2]]["archived"]
    assert rows[IDS[3]]["project_name"] == "无项目会话"
    assert {p["id"] for p in cat["providers"]} == {"openai", "wzh", "seu"}
    assert len(cat["projects"]) == 2


@pytest.mark.parametrize("source,target", [("openai", "wzh"), ("wzh", "openai"), ("seu", "openai"), ("openai", "seu"), ("wzh", "seu")])
def test_switch_preserves_history_events_and_other_data(home, source, target):
    path = home / "sessions" / (IDS[0] + ".jsonl")
    data = path.read_bytes()
    obj, rest = data.split(b"\n", 1)
    meta = json.loads(obj)
    meta["payload"]["model_provider"] = source
    path.write_bytes(json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode() + b"\r\n" + rest)
    delta = len(path.read_bytes()) - len(data)
    execute(home, "UPDATE threads SET model_provider=? WHERE id=?", (source, IDS[0]))
    execute(home, "UPDATE thread_turns SET rollout_byte_offset=CASE WHEN rollout_byte_offset>0 THEN rollout_byte_offset+? ELSE rollout_byte_offset END, rollout_end_byte_offset=rollout_end_byte_offset+? WHERE thread_id=?", (delta, delta, IDS[0]), "thread_history_1.sqlite")
    execute(home, "UPDATE thread_history_projection_state SET next_rollout_byte_offset=next_rollout_byte_offset+? WHERE thread_id=?", (delta, IDS[0]), "thread_history_1.sqlite")
    before = snapshot(home)
    with sqlite3.connect(home / "thread_history_1.sqlite") as c:
        offsets = c.execute("SELECT rollout_byte_offset,rollout_end_byte_offset FROM thread_turns WHERE thread_id=? AND turn_id='turn-1'", (IDS[0],)).fetchone()
    old_data = path.read_bytes()
    event = old_data[offsets[0]:offsets[1]]
    preview = core.preview(home, [IDS[0]], target)
    assert snapshot(home) == before
    result = core.switch(home, [IDS[0]], target, preview["token"])
    assert result["state"] == "committed"
    new_data = path.read_bytes()
    assert new_data.split(b"\n", 1)[1] == old_data.split(b"\n", 1)[1]
    with sqlite3.connect(home / "thread_history_1.sqlite") as c:
        off = c.execute("SELECT rollout_byte_offset,rollout_end_byte_offset FROM thread_turns WHERE thread_id=? AND turn_id='turn-1'", (IDS[0],)).fetchone()
        end = c.execute("SELECT next_rollout_byte_offset FROM thread_history_projection_state WHERE thread_id=?", (IDS[0],)).fetchone()[0]
    assert new_data[off[0]:off[1]] == event
    assert end == len(new_data)
    after = snapshot(home)
    assert after["config"] == before["config"]
    for tid in IDS[1:]:
        assert after["files"][tid + ".jsonl"] == before["files"][tid + ".jsonl"]
    with sqlite3.connect(home / "state_5.sqlite") as c:
        assert c.execute("SELECT model FROM threads WHERE id=?", (IDS[0],)).fetchone()[0] == "gpt-6-astra"
    core.restore(home, result["id"])
    assert snapshot(home) == before


def test_multi_select_removed_provider_and_id_deduplication(home):
    before = snapshot(home)
    result = core.switch(home, [IDS[0], IDS[1], IDS[2], IDS[0]], "wzh")
    assert result["count"] == 3
    assert core.switch(home, IDS, "wzh")["state"] == "unchanged"
    core.restore(home, result["id"])
    assert snapshot(home) == before


@pytest.mark.parametrize("phase", ["prepared", "entry:0", "entry:1", "committed"])
def test_failures_automatically_restore_selected_records(home, phase):
    before = snapshot(home)
    def fault(point):
        if point == phase:
            raise RuntimeError("故障注入")
    with pytest.raises(core.SwitchError, match="切换失败"):
        core.switch(home, IDS[:2], "wzh", _fault=fault)
    assert snapshot(home) == before
    assert not core.pending(home)


@pytest.mark.parametrize("phase", ["prepared", "entry:0", "entry:1", "committed"])
def test_crash_recovery_after_next_launch(home, phase):
    before = snapshot(home)
    def crash(point):
        if point == phase:
            raise KeyboardInterrupt("模拟进程中断")
    with pytest.raises(KeyboardInterrupt):
        core.switch(home, IDS[:2], "wzh", _fault=crash)
    ops = core.pending(home)
    assert len(ops) == 1
    with pytest.raises(core.SwitchError, match="未完成"):
        core.switch(home, [IDS[0]], "wzh")
    core.restore(home, ops[0]["id"])
    assert snapshot(home) == before
    assert not core.pending(home)


def test_new_content_blocks_restore_without_overwrite(home):
    result = core.switch(home, [IDS[0]], "wzh")
    path = home / "sessions" / (IDS[0] + ".jsonl")
    path.write_bytes(path.read_bytes() + b'\n{"type":"event_msg","payload":{"text":"new"}}\n')
    after = snapshot(home)
    with pytest.raises(core.SwitchError, match="新增内容"):
        core.restore(home, result["id"])
    assert snapshot(home) == after


def test_restore_leaves_unrelated_new_tasks_untouched(home):
    result = core.switch(home, [IDS[0]], "wzh")
    execute(home, "UPDATE threads SET name='新名称' WHERE id=?", (IDS[3],))
    core.restore(home, result["id"])
    assert next(r for r in core.catalog(home)["threads"] if r["id"] == IDS[3])["name"] == "新名称"


def test_running_process_guard(home, monkeypatch):
    before = snapshot(home)
    monkeypatch.setattr(core, "running_processes", lambda: ["codex.exe"])
    assert core.preview(home, [IDS[0]], "wzh")["count"] == 1
    with pytest.raises(core.SwitchError, match="退出"):
        core.switch(home, [IDS[0]], "wzh")
    assert snapshot(home) == before
    assert not core.operations(home)


def test_database_lock(home):
    c = sqlite3.connect(home / "state_5.sqlite")
    c.execute("BEGIN IMMEDIATE")
    before = snapshot(home)
    try:
        with pytest.raises(core.SwitchError, match="locked"):
            core.switch(home, [IDS[0]], "wzh")
    finally:
        c.rollback(); c.close()
    assert snapshot(home) == before


def test_backup_failure(home, monkeypatch):
    before = snapshot(home)
    monkeypatch.setattr(core, "sqlite_backup", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(core.SwitchError, match="disk full"):
        core.switch(home, [IDS[0]], "wzh")
    assert snapshot(home) == before
    assert not core.pending(home)


@pytest.mark.parametrize("kind", ["missing", "id", "provider", "json", "index", "schema", "target", "outside"])
def test_invalid_data_blocks_entire_batch(home, kind):
    path = home / "sessions" / (IDS[1] + ".jsonl")
    if kind == "missing":
        path.unlink()
    elif kind in ("id", "provider"):
        data = path.read_bytes().replace(IDS[1].encode(), IDS[0].encode()) if kind == "id" else path.read_bytes().replace(b'"seu"', b'"wzh"')
        path.write_bytes(data)
    elif kind == "json":
        path.write_bytes(path.read_bytes() + b"\nbad json")
    elif kind == "index":
        execute(home, "UPDATE thread_turns SET rollout_byte_offset=2 WHERE thread_id=?", (IDS[1],), "thread_history_1.sqlite")
    elif kind == "schema":
        execute(home, "ALTER TABLE thread_turns ADD COLUMN unknown_offset INTEGER", db="thread_history_1.sqlite")
    elif kind == "outside":
        outside = home.parent / "external.jsonl"
        outside.write_bytes(path.read_bytes())
        execute(home, "UPDATE threads SET rollout_path=? WHERE id=?", (str(outside), IDS[1]))
    before = snapshot(home)
    with pytest.raises(core.SwitchError):
        core.switch(home, IDS[:2], "unknown" if kind == "target" else "wzh")
    assert snapshot(home) == before


def test_change_after_preview_is_rejected(home):
    plan = core.preview(home, [IDS[0]], "wzh")
    execute(home, "UPDATE threads SET name='已更新' WHERE id=?", (IDS[0],))
    before = snapshot(home)
    with pytest.raises(core.SwitchError, match="预览后"):
        core.switch(home, [IDS[0]], "wzh", plan["token"])
    assert snapshot(home) == before


def test_concurrent_file_change_during_preparation(home):
    path = home / "sessions" / (IDS[0] + ".jsonl")
    before = database_dump(home / "state_5.sqlite")
    def race(point):
        if point == "prepared":
            path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(core.SwitchError, match="变化"):
        core.switch(home, [IDS[0]], "wzh", _fault=race)
    assert database_dump(home / "state_5.sqlite") == before
    assert path.read_bytes().endswith(b"\n")


def test_legacy_without_history_db(home):
    (home / "thread_history_1.sqlite").unlink()
    execute(home, "UPDATE threads SET history_mode='legacy'")
    before = snapshot_without_history(home)
    result = core.switch(home, [IDS[0]], "wzh")
    core.restore(home, result["id"])
    assert snapshot_without_history(home) == before


def snapshot_without_history(home):
    return database_dump(home / "state_5.sqlite"), [p.read_bytes() for p in sorted((home / "sessions").glob("*"))]


def test_cli_json_and_dry_run(home):
    root = Path(__file__).resolve().parents[1]
    before = snapshot(home)
    cmd = [sys.executable, str(root / "cli_main.py"), "--codex-home", str(home), "--json"]
    cp = subprocess.run(cmd + ["list"], capture_output=True, encoding="utf-8")
    assert cp.returncode == 0, cp.stderr
    assert len(json.loads(cp.stdout)["threads"]) == 2
    cp = subprocess.run(cmd + ["switch", "--thread-id", IDS[0], "--to-provider", "wzh", "--dry-run"], capture_output=True, encoding="utf-8")
    assert cp.returncode == 0, cp.stderr
    assert json.loads(cp.stdout)["dry_run"]
    assert snapshot(home) == before


def test_mutex_blocks_another_process(home):
    cmd = [sys.executable, "-c", "from provider_switcher.core import *; import sys;\nwith exclusive(home_path(sys.argv[1])): print('locked')", str(home)]
    with core.exclusive(home):
        cp = subprocess.run(cmd, capture_output=True)
    assert cp.returncode != 0


def test_offset_zero_eof_and_interior():
    data = b"meta\nevent\n"
    edits = [[0, 5, -2]]
    assert core.shifted_offset(0, data, edits) == 0
    assert core.shifted_offset(5, data, edits) == 3
    assert core.shifted_offset(len(data), data, edits) == len(data) - 2
    assert core.shifted_offset(None, data, edits) is None
    with pytest.raises(core.SwitchError):
        core.shifted_offset(2, data, edits)


def test_windows_extended_path_and_long_path(home):
    source = home / "sessions" / (IDS[0] + ".jsonl")
    nested = home / "sessions" / ("长路径" * 25) / ("更多目录" * 20)
    nested.mkdir(parents=True)
    dest = nested / source.name
    source.replace(dest)
    extended = "\\\\?\\" + str(dest)
    execute(home, "UPDATE threads SET rollout_path=? WHERE id=?", (extended, IDS[0]))
    assert core.inside(Path(extended), home)
    result = core.switch(home, [IDS[0]], "wzh")
    core.restore(home, result["id"])
    assert json.loads(dest.read_bytes().split(b"\n")[0])["payload"]["model_provider"] == "openai"


def test_config_change_after_preview_is_rejected(home):
    plan = core.preview(home, [IDS[0]], "wzh")
    config = home / "config.toml"
    config.write_text(config.read_text() + '\n# externally changed\n')
    with pytest.raises(core.SwitchError, match="预览后"):
        core.switch(home, [IDS[0]], "wzh", plan["token"])


def test_partial_file_write_failure_rolls_back(home, monkeypatch):
    before = snapshot(home)
    atomic = core.atomic_bytes
    failed = [False]
    def fail_once(path, data):
        if path.name == IDS[1] + '.jsonl' and not failed[0]:
            failed[0] = True
            raise OSError("replacement denied")
        return atomic(path, data)
    monkeypatch.setattr(core, "atomic_bytes", fail_once)
    with pytest.raises(core.SwitchError, match="replacement denied"):
        core.switch(home, IDS[:2], "wzh")
    assert snapshot(home) == before


def test_interrupted_restore_can_resume(home, monkeypatch):
    before = snapshot(home)
    result = core.switch(home, IDS[:2], "wzh")
    atomic = core.atomic_bytes
    def fail_second(path, data):
        if path.name == IDS[1] + '.jsonl':
            raise OSError("restore interrupted")
        return atomic(path, data)
    monkeypatch.setattr(core, "atomic_bytes", fail_second)
    with pytest.raises(OSError, match="restore interrupted"):
        core.restore(home, result["id"])
    assert core.pending(home)[0]["state"] == "restoring"
    monkeypatch.setattr(core, "atomic_bytes", atomic)
    core.restore(home, result["id"])
    assert snapshot(home) == before


def test_app_restart_during_write_defers_recovery(home, monkeypatch):
    before = snapshot(home)
    def restart(phase):
        if phase == 'entry:0':
            monkeypatch.setattr(core, 'running_processes', lambda: ['codex.exe'])
    with pytest.raises(core.SwitchError, match="恢复需要处理"):
        core.switch(home, IDS[:2], 'wzh', _fault=restart)
    op = core.pending(home)[0]
    assert op['state'] == 'needs_recovery'
    monkeypatch.setattr(core, 'running_processes', lambda: [])
    core.restore(home, op['id'])
    assert snapshot(home) == before


def test_corrupt_backup_blocks_restore(home):
    result = core.switch(home, [IDS[0]], 'wzh')
    backup = Path(result['backup']) / (IDS[0] + '.before.jsonl')
    backup.write_bytes(b'corrupt')
    before = snapshot(home)
    with pytest.raises(core.SwitchError, match='备份校验失败'):
        core.restore(home, result['id'])
    assert snapshot(home) == before


@pytest.mark.parametrize('phase', ['entry:0', 'committed'])
def test_hard_process_exit_leaves_recoverable_journal(home, phase):
    before = snapshot(home)
    code = """
from provider_switcher import core
import os,sys
core.running_processes = lambda: []
def crash(point):
    if point == sys.argv[2]: os._exit(79)
core.switch(core.home_path(sys.argv[1]), sys.argv[3:], 'wzh', _fault=crash)
"""
    result = subprocess.run([sys.executable, '-c', code, str(home), phase, *IDS[:2]], capture_output=True)
    assert result.returncode == 79, result.stderr
    op = core.pending(home)[0]
    core.restore(home, op['id'])
    assert snapshot(home) == before
