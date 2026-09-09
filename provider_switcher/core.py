from __future__ import annotations

import contextlib
import csv
import ctypes
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import tomllib
import uuid


class SwitchError(RuntimeError):
    """An actionable validation or recovery failure."""


TERMINAL = {"committed", "restored", "rolled_back", "aborted"}
HISTORY_FIELDS = {
    "thread_turns": (["thread_id", "turn_id"], ["rollout_byte_offset", "rollout_end_byte_offset"]),
    "thread_history_projection_state": (["thread_id"], ["next_rollout_byte_offset"]),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def signature(obj) -> str:
    return digest(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def home_path(value=None) -> Path:
    return Path(value or os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()


def read_db(path: Path):
    if not path.is_file():
        raise SwitchError(f"数据库不存在：{path}")
    c = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
    c.row_factory = sqlite3.Row
    return c


def columns(c, table, schema="main"):
    return [r[1] for r in c.execute(f'PRAGMA {schema}.table_info("{table}")')]


def table_names(c, schema="main"):
    return [r[0] for r in c.execute(f"SELECT name FROM {schema}.sqlite_master WHERE type='table'")]


def check_state_schema(c):
    required = {"id", "rollout_path", "model_provider", "cwd", "title", "archived"}
    if not required.issubset(columns(c, "threads")):
        raise SwitchError("不支持的 state_5.sqlite 结构：缺少必要的会话字段。")


def providers(home: Path):
    try:
        cfg = tomllib.loads((home / "config.toml").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise SwitchError(f"无法读取 Provider 配置：{e}") from e
    result = {"openai": {"id": "openai", "name": "OpenAI / ChatGPT"}}
    for key, value in cfg.get("model_providers", {}).items():
        if isinstance(value, dict) and key and not any(ord(ch) < 32 for ch in key):
            # Deliberately expose no authentication or credential values.
            result[key] = {"id": key, "name": str(value.get("name", key))}
    return result


def normalized(path):
    p = str(path or "").replace("/", "\\")
    if p.startswith("\\\\?\\UNC\\"):
        p = "\\\\" + p[8:]
    elif p.startswith("\\\\?\\"):
        p = p[4:]
    return p.rstrip("\\").casefold()


def display_path(path):
    """Return a friendly Windows path without changing the stored path."""
    value = str(path or "")
    if value.startswith("\\\\?\\UNC\\"):
        return "\\\\" + value[8:]
    if value.startswith("\\\\?\\"):
        return value[4:]
    if value.startswith("//?/UNC/"):
        return "//" + value[8:]
    if value.startswith("//?/"):
        return value[4:]
    return value


def inside(path: Path, root: Path):
    # Path.is_relative_to considers C:\ and \\?\C:\ different anchors on Windows.
    # Resolve junctions first, then compare the equivalent Windows path spellings.
    p, r = normalized(path.resolve()), normalized(root.resolve())
    return p == r or p.startswith(r + "\\")


def catalog(home: Path):
    """Read only metadata; never deserialize conversational instruction payloads here."""
    with contextlib.closing(read_db(home / "state_5.sqlite")) as c:
        check_state_schema(c)
        rows = [dict(r) for r in c.execute("SELECT * FROM threads")]
        tables = table_names(c)
        projects = {}
        if "projects" in tables and {"id", "name"}.issubset(columns(c, "projects")):
            for r in c.execute("SELECT * FROM projects"):
                projects[r["id"]] = {"id": r["id"], "name": r["name"], "roots": [], "position": dict(r).get("position", 9999)}
        if "project_roots" in tables:
            for r in c.execute("SELECT project_id, path FROM project_roots ORDER BY position"):
                if r[0] in projects:
                    projects[r[0]]["roots"].append(r[1])
        parents = {}
        if "thread_spawn_edges" in tables:
            for r in c.execute("SELECT parent_thread_id, child_thread_id FROM thread_spawn_edges"):
                parents[r[1]] = r[0]
    state_file = home / ".codex-global-state.json"
    try:
        state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    except (OSError, ValueError) as e:
        raise SwitchError(f"项目归属文件无法读取：{e}") from e
    mappings = state.get("app-server-project-id-by-legacy-project-id-by-host", {})
    legacy_map = {}
    for host, mapping in mappings.items():
        if host.startswith("local:") and normalized(host[6:]) == normalized(home):
            legacy_map.update(mapping)
    for pid, p in state.get("local-projects", {}).items():
        canonical = legacy_map.get(pid, pid)
        if canonical not in projects:
            projects[canonical] = {"id": canonical, "name": p.get("name", pid), "roots": p.get("rootPaths", []), "position": 9999}
    assignments = state.get("thread-project-assignments", {})
    projectless = set(state.get("projectless-thread-ids", []))
    hints = state.get("thread-workspace-root-hints", {})
    result = []
    for r in rows:
        tid = r["id"]
        pid = r.get("project_id")
        a = assignments.get(tid, {})
        remote = bool(a and a.get("projectKind") not in (None, "local"))
        if pid not in projects:
            aid = a.get("projectId")
            pid = legacy_map.get(aid, aid)
        if pid not in projects and tid not in projectless and not remote:
            cwd = normalized(hints.get(tid) or r["cwd"])
            matches = [(len(normalized(root)), p["id"]) for p in projects.values() for root in p["roots"]
                       if normalized(root) and (cwd == normalized(root) or cwd.startswith(normalized(root) + "\\"))]
            longest = max((m[0] for m in matches), default=-1)
            candidates = {p for n, p in matches if n == longest}
            pid = next(iter(candidates)) if len(candidates) == 1 else None
        p = projects.get(pid)
        path = Path(r["rollout_path"])
        error = "仅支持本机会话" if remote else ("会话文件缺失" if not path.is_file() else "")
        title = (r.get("name") or r["title"] or "未命名会话").strip()
        source = r.get("thread_source") or ""
        result.append({
            "id": tid, "name": title, "project_id": p["id"] if p else None,
            "project_name": p["name"] if p else ("无项目会话" if tid in projectless else "未归属项目"),
            "cwd": display_path(r["cwd"]), "project_roots": p["roots"] if p else [],
            "model": r.get("model") or "未记录", "provider": r["model_provider"],
            "archived": bool(r["archived"]), "parent_id": parents.get(tid),
            "is_agent": tid in parents or source in ("subagent", "agent") or bool(r.get("agent_path")),
            "updated_at": r.get("updated_at_ms") or r.get("updated_at", 0) * 1000,
            "rollout_path": str(path), "error": error,
        })
    result.sort(key=lambda r: r["updated_at"], reverse=True)
    return {"home": str(home), "projects": sorted(projects.values(), key=lambda p: (p["position"], p["name"])),
            "threads": result, "providers": list(providers(home).values())}


def running_processes():
    if os.name != "nt":
        raise SwitchError("实际写入仅支持 Windows。")
    try:
        cp = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                            timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        if cp.returncode:
            raise SwitchError("无法检查运行进程，请稍后重试。")
        names = {row[0].casefold() for row in csv.reader(io.StringIO(cp.stdout.decode("utf-8", "replace"))) if row}
        return sorted(n for n in names if n in {"codex.exe", "chatgpt.exe", "codex-app-server.exe"})
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SwitchError("无法检查运行进程，已阻止写入。") from e


def require_stopped():
    running = running_processes()
    if running:
        raise SwitchError("请先完全退出 Codex / ChatGPT 及 Codex CLI 或 VS Code 中的 Codex 后端，再点击应用。正在运行：" + ", ".join(running))


@contextlib.contextmanager
def exclusive(home):
    """A per-CODEX_HOME Windows mutex, released by the OS after a crash."""
    if os.name != "nt":
        raise SwitchError("实际写入仅支持 Windows。")
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    k.CreateMutexW.restype = ctypes.c_void_p
    k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k.ReleaseMutex.argtypes = [ctypes.c_void_p]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = k.CreateMutexW(None, False, "Local\\ProviderSwitcher." + digest(normalized(home).encode())[:32])
    if not handle:
        raise SwitchError("无法取得工具互斥锁。")
    acquired = False
    try:
        acquired = k.WaitForSingleObject(handle, 0) in (0, 0x80)
        if not acquired:
            raise SwitchError("另一个切换或恢复操作正在运行。")
        yield
    finally:
        if acquired:
            k.ReleaseMutex(handle)
        k.CloseHandle(handle)


def atomic_bytes(path: Path, data: bytes):
    fd, temp = tempfile.mkstemp(prefix=".provider-switch-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save_manifest(folder, m):
    atomic_bytes(folder / "manifest.json", json.dumps(m, ensure_ascii=False, indent=2).encode("utf-8"))


def operations(home):
    root = home / "provider-switcher" / "operations"
    result = []
    if root.exists():
        for folder in sorted(root.iterdir(), reverse=True):
            if not folder.is_dir():
                continue
            try:
                m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
                result.append({"id": folder.name, "state": m["state"], "created_at": m.get("created_at", ""),
                               "count": len(m.get("entries", [])), "error": m.get("error", "")})
            except (OSError, ValueError, KeyError):
                result.append({"id": folder.name, "state": "unreadable", "count": 0,
                               "error": "操作日志缺失或损坏，请保留目录并人工检查。"})
    return result


def pending(home):
    return [o for o in operations(home) if o["state"] not in TERMINAL]


def rewrite_rollout(data: bytes, tid: str, old: str, new: str):
    output, edits, offset, count = [], [], 0, 0
    # Require true LF-separated records; bytes.splitlines also splits other control bytes.
    lines = data.split(b"\n")
    for index, part in enumerate(lines):
        raw = part + (b"\n" if index < len(lines) - 1 else b"")
        replacement = raw
        if raw.strip():
            try:
                obj = json.loads(raw)
            except (ValueError, UnicodeError) as e:
                raise SwitchError(f"会话 {tid} 第 {index + 1} 行不是有效 JSON，未修改。") from e
            if index == 0 and (not isinstance(obj, dict) or obj.get("type") != "session_meta"):
                raise SwitchError(f"会话 {tid} 缺少首行 session_meta。")
            if isinstance(obj, dict) and obj.get("type") == "session_meta":
                p = obj.get("payload", {})
                if not isinstance(p, dict) or p.get("id") != tid:
                    raise SwitchError(f"会话 {tid} 的元数据 ID 不一致。")
                if p.get("model_provider") != old:
                    raise SwitchError(f"会话 {tid} 的数据库与文件 Provider 不一致。")
                p["model_provider"] = new
                newline = b"\r\n" if raw.endswith(b"\r\n") else b"\n" if raw.endswith(b"\n") else b""
                replacement = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + newline
                edits.append([offset, offset + len(raw), len(replacement) - len(raw)])
                count += 1
        output.append(replacement)
        offset += len(raw)
    if not count:
        raise SwitchError(f"会话 {tid} 未找到 Provider 元数据。")
    return b"".join(output), edits


def shifted_offset(value, data, edits):
    if value is None:
        return None
    if not isinstance(value, int) or value < 0 or value > len(data):
        raise SwitchError(f"历史索引越界：{value} / {len(data)}。")
    if value not in (0, len(data)) and data[value - 1:value] != b"\n":
        raise SwitchError(f"历史索引 {value} 未指向 JSONL 行边界。")
    delta = 0
    for start, end, change in edits:
        if start < value < end:
            raise SwitchError("历史索引落在元数据行内部，无法安全切换。")
        if value >= end:
            delta += change
    return value + delta


def history_snapshot(home, tid, data, edits):
    path = home / "thread_history_1.sqlite"
    if not path.exists():
        return None
    snapshot = {}
    with contextlib.closing(read_db(path)) as c:
        tables = table_names(c)
        for table in tables:
            offsets = {n for n in columns(c, table) if "offset" in n}
            allowed = set(HISTORY_FIELDS.get(table, ([], []))[1])
            if offsets - allowed:
                raise SwitchError(f"未知历史索引字段：{table}，请更新工具后再写入。")
        for table, (keys, fields) in HISTORY_FIELDS.items():
            if table not in tables or not set(keys + fields).issubset(columns(c, table)):
                raise SwitchError(f"不支持的历史数据库结构：{table}。")
            rows = [dict(r) for r in c.execute(f'SELECT * FROM "{table}" WHERE thread_id=? ORDER BY ' + ",".join(keys), (tid,))]
            updates = []
            for row in rows:
                changed = dict(row)
                for f in fields:
                    changed[f] = shifted_offset(row[f], data, edits)
                updates.append({"keys": {k: row[k] for k in keys}, "before": {f: row[f] for f in fields},
                                "after": {f: changed[f] for f in fields}})
            after_rows = []
            for row, update in zip(rows, updates):
                after_rows.append({**row, **update["after"]})
            snapshot[table] = {"updates": updates, "before_hash": signature(rows), "after_hash": signature(after_rows)}
    return snapshot


def preview(home, ids, target):
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise SwitchError("请至少选择一个会话。")
    if target not in providers(home):
        raise SwitchError("目标 Provider 不在当前配置中。")
    cat = {t["id"]: t for t in catalog(home)["threads"]}
    entries = []
    with contextlib.closing(read_db(home / "state_5.sqlite")) as c:
        check_state_schema(c)
        for tid in ids:
            try:
                if str(uuid.UUID(tid)) != tid.lower():
                    raise ValueError()
            except ValueError as exc:
                raise SwitchError("无效的任务 ID，必须是完整 UUID。") from exc
            if tid not in cat:
                raise SwitchError(f"任务 ID 不存在：{tid}")
            t = cat[tid]
            if t["error"]:
                raise SwitchError(f"{t['name'][:60]}：{t['error']}")
            row = dict(c.execute("SELECT * FROM threads WHERE id=?", (tid,)).fetchone())
            path = Path(row["rollout_path"]).resolve()
            if not inside(path, home):
                raise SwitchError(f"会话文件位于 CODEX_HOME 之外，第一版不支持：{path}")
            data = path.read_bytes()
            new_data, edits = rewrite_rollout(data, tid, row["model_provider"], target)
            if row["model_provider"] == target:
                new_data, edits = data, []
            hist = history_snapshot(home, tid, data, edits)
            if row.get("history_mode") not in (None, "legacy", "paginated"):
                raise SwitchError("未知 history_mode，已阻止切换。")
            if row.get("history_mode") == "paginated" and hist is None:
                raise SwitchError("分页会话缺少历史数据库。")
            entries.append({"id": tid, "name": t["name"], "model": t["model"], "path": str(path),
                            "before_provider": row["model_provider"], "after_provider": target,
                            "before_row_hash": signature(row), "after_row_hash": signature({**row, "model_provider": target}),
                            "before_hash": digest(data), "after_hash": digest(new_data), "edits": edits,
                            "history": hist, "changed": row["model_provider"] != target,
                            "byte_delta": len(new_data) - len(data)})
    paths = [e["path"].casefold() for e in entries]
    if len(paths) != len(set(paths)):
        raise SwitchError("多个任务指向同一个会话文件，无法安全修改。")
    config_hash = digest((home / "config.toml").read_bytes())
    return {"home": str(home), "target": target, "entries": entries, "config_hash": config_hash,
            "count": sum(e["changed"] for e in entries), "token": signature([entries, config_hash])}


def sqlite_backup(src, dst):
    with contextlib.closing(read_db(src)) as s, contextlib.closing(sqlite3.connect(dst)) as d:
        s.backup(d)


def writable_db(home, use_history):
    # mode=rw prevents accidentally creating a missing database.
    c = sqlite3.connect((home / "state_5.sqlite").as_uri() + "?mode=rw", uri=True, timeout=2)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=2000")
    c.execute("PRAGMA synchronous=FULL")
    if use_history:
        hp = home / "thread_history_1.sqlite"
        if not hp.is_file():
            c.close()
            raise SwitchError("历史数据库已消失。")
        c.execute("ATTACH DATABASE ? AS hist", (hp.as_uri() + "?mode=rw",))
        c.execute("PRAGMA hist.synchronous=FULL")
    return c


def current_hashes(c, e):
    row = c.execute("SELECT * FROM threads WHERE id=?", (e["id"],)).fetchone()
    if row is None:
        raise SwitchError("任务已消失，无法继续。")
    result = {"row": signature(dict(row))}
    for table in e["history"] or {}:
        keys = HISTORY_FIELDS[table][0]
        rows = [dict(r) for r in c.execute(f'SELECT * FROM hist."{table}" WHERE thread_id=? ORDER BY ' + ",".join(keys), (e["id"],))]
        result[table] = signature(rows)
    return result


def update_entry(c, e, direction):
    c.execute("UPDATE threads SET model_provider=? WHERE id=?", (e[direction + "_provider"], e["id"]))
    for table, info in (e["history"] or {}).items():
        keys, fields = HISTORY_FIELDS[table]
        for row in info["updates"]:
            sql = f'UPDATE hist."{table}" SET ' + ",".join(f'"{f}"=?' for f in fields)
            sql += " WHERE " + " AND ".join(f'"{k}"=?' for k in keys)
            cur = c.execute(sql, [row[direction][f] for f in fields] + [row["keys"][k] for k in keys])
            if cur.rowcount != 1:
                raise SwitchError("历史索引记录发生变化。")


def validate_current(c, entries, direction):
    for e in entries:
        hashes = current_hashes(c, e)
        if hashes["row"] != e[direction + "_row_hash"]:
            raise SwitchError(f"任务 {e['id']} 的数据库记录已变化，请刷新。")
        for table, info in (e["history"] or {}).items():
            if hashes[table] != info[direction + "_hash"]:
                raise SwitchError(f"任务 {e['id']} 的历史索引已变化。")
        if digest(Path(e["path"]).read_bytes()) != e[direction + "_hash"]:
            raise SwitchError(f"任务 {e['id']} 的会话文件已变化；禁止覆盖新增内容。")


def switch(home, ids, target, expected_token=None, *, _fault=None):
    """Perform an offline switch. _fault is an internal failure-injection test hook."""
    with exclusive(home):
        require_stopped()
        if pending(home):
            raise SwitchError("发现未完成的操作。请先在“备份与恢复”中处理。")
        plan = preview(home, ids, target)
        if expected_token and plan["token"] != expected_token:
            raise SwitchError("预览后会话发生变化，请重新查看变更清单。")
        entries = [e for e in plan["entries"] if e["changed"]]
        if not entries:
            return {"state": "unchanged", "count": 0, "message": "选中会话已使用该 Provider。"}
        opid = dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:12]
        folder = home / "provider-switcher" / "operations" / opid
        folder.mkdir(parents=True, exist_ok=False)
        m = {"version": 1, "id": opid, "home": str(home), "state": "preparing",
             "created_at": dt.datetime.now().astimezone().isoformat(), "entries": entries}
        save_manifest(folder, m)
        c = None
        try:
            sqlite_backup(home / "state_5.sqlite", folder / "state_5.sqlite")
            if any(e["history"] is not None for e in entries):
                sqlite_backup(home / "thread_history_1.sqlite", folder / "thread_history_1.sqlite")
            for e in entries:
                original = Path(e["path"]).read_bytes()
                if digest(original) != e["before_hash"]:
                    raise SwitchError("备份前会话发生变化。")
                new, _ = rewrite_rollout(original, e["id"], e["before_provider"], e["after_provider"])
                if digest(new) != e["after_hash"]:
                    raise SwitchError("准备文件与预览不一致。")
                e["backup"] = e["id"] + ".before.jsonl"
                e["staged"] = e["id"] + ".after.jsonl"
                atomic_bytes(folder / e["backup"], original)
                atomic_bytes(folder / e["staged"], new)
            m["state"] = "prepared"
            save_manifest(folder, m)
            if _fault:
                _fault("prepared")
            require_stopped()
            if digest((home / "config.toml").read_bytes()) != plan["config_hash"]:
                raise SwitchError("Provider 配置在预览后发生变化，请刷新。")
            c = writable_db(home, any(e["history"] is not None for e in entries))
            c.execute("BEGIN IMMEDIATE")
            validate_current(c, entries, "before")
            m["state"] = "applying"
            save_manifest(folder, m)
            for i, e in enumerate(entries):
                require_stopped()
                atomic_bytes(Path(e["path"]), (folder / e["staged"]).read_bytes())
                update_entry(c, e, "after")
                if _fault:
                    _fault(f"entry:{i}")
            validate_current(c, entries, "after")
            require_stopped()
            if digest((home / "config.toml").read_bytes()) != plan["config_hash"]:
                raise SwitchError("切换过程中 Provider 配置发生变化。")
            c.commit()
            if _fault:
                _fault("committed")
            validate_current(c, entries, "after")
            m["state"] = "committed"
            save_manifest(folder, m)
            return {"id": opid, "state": "committed", "count": len(entries), "backup": str(folder),
                    "message": "本地修改已验证；恢复会话后的请求通道待验证。"}
        except Exception as exc:
            if c:
                c.rollback()
                c.close()
                c = None
            m["error"] = str(exc)
            if m["state"] in ("preparing", "prepared"):
                m["state"] = "aborted"
                save_manifest(folder, m)
            else:
                m["state"] = "needs_recovery"
                save_manifest(folder, m)
                try:
                    require_stopped()
                    _restore(home, folder, m)
                except Exception as recovery_error:
                    raise SwitchError(f"切换未完成，恢复需要处理：{recovery_error}。备份：{folder}") from exc
            raise SwitchError(f"切换失败，未保留本次修改：{exc}") from exc
        finally:
            if c:
                c.close()


def restore(home, operation_id):
    if not operation_id or Path(operation_id).name != operation_id or any(x in operation_id for x in ("/", "\\", ":")):
        raise SwitchError("无效的操作 ID。")
    with exclusive(home):
        require_stopped()
        folder = home / "provider-switcher" / "operations" / operation_id
        try:
            m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise SwitchError("操作日志缺失或损坏，请保留备份目录并人工检查。") from e
        if m.get("version") != 1 or normalized(m.get("home")) != normalized(home):
            raise SwitchError("备份版本或 CODEX_HOME 不匹配。")
        if m["state"] in {"restored", "rolled_back", "aborted"}:
            return {"id": operation_id, "state": m["state"], "message": "该操作已恢复或未执行修改。"}
        if m["state"] in {"preparing", "prepared"}:
            # All writes occur strictly after a durable 'applying' manifest.
            m["state"] = "aborted"
            save_manifest(folder, m)
            return {"id": operation_id, "state": "aborted", "message": "未开始写入，已清理操作状态。"}
        return _restore(home, folder, m)


def _restore(home, folder, m):
    entries = m["entries"]
    if m["state"] != "restoring":
        m["restore_result"] = "restored" if m["state"] == "committed" else "rolled_back"
    c = writable_db(home, any(e["history"] is not None for e in entries))
    try:
        c.execute("BEGIN IMMEDIATE")
        # Allow each DB/file component to be before OR after: a crash may split commits.
        # Reject anything else, including new chat messages. Never restore whole databases.
        for e in entries:
            path = Path(e["path"]).resolve()
            backup = (folder / e["backup"]).resolve()
            if not inside(path, home) or not inside(backup, folder):
                raise SwitchError("恢复路径越界。")
            if digest(backup.read_bytes()) != e["before_hash"]:
                raise SwitchError("备份校验失败。")
            if digest(path.read_bytes()) not in (e["before_hash"], e["after_hash"]):
                raise SwitchError(f"会话 {e['id']} 已新增内容或发生变化，已禁止覆盖。")
            hashes = current_hashes(c, e)
            if hashes["row"] not in (e["before_row_hash"], e["after_row_hash"]):
                raise SwitchError(f"会话 {e['id']} 数据库记录发生变化，已禁止恢复。")
            for table, info in (e["history"] or {}).items():
                if hashes[table] not in (info["before_hash"], info["after_hash"]):
                    raise SwitchError("历史记录发生变化，已禁止恢复。")
        require_stopped()
        m["state"] = "restoring"
        save_manifest(folder, m)
        for e in entries:
            require_stopped()
            path = Path(e["path"])
            if digest(path.read_bytes()) not in (e["before_hash"], e["after_hash"]):
                raise SwitchError("恢复过程中会话文件发生变化，已停止。")
            atomic_bytes(path, (folder / e["backup"]).read_bytes())
            update_entry(c, e, "before")
        validate_current(c, entries, "before")
        require_stopped()
        c.commit()
        validate_current(c, entries, "before")
        m["state"] = m["restore_result"]
        save_manifest(folder, m)
        return {"id": m["id"], "state": m["state"], "count": len(entries), "message": "已恢复本次操作涉及的会话和历史索引。"}
    except Exception:
        c.rollback()
        # Durable restoring state remains recoverable on the next launch.
        raise
    finally:
        c.close()
