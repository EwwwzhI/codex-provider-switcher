import json
from pathlib import Path
import sqlite3
import uuid

import pytest

from provider_switcher import core


IDS = [str(uuid.UUID(int=i)) for i in range(1, 5)]


def make_home(home: Path):
    home.mkdir(parents=True, exist_ok=True)
    (home / "sessions").mkdir(exist_ok=True)
    (home / "config.toml").write_text('model_provider = "wzh"\n[model_providers.wzh]\nname = "WZH API"\n[model_providers.seu]\nname = "SEU API"\n', encoding="utf-8")
    state = {
        "local-projects": {"old-p": {"name": "项目 · 中文路径", "rootPaths": [r"C:\示例\项目"]}},
        "app-server-project-id-by-legacy-project-id-by-host": {"local:" + str(home): {"old-p": "project-1"}},
        "thread-project-assignments": {IDS[0]: {"projectKind": "local", "projectId": "old-p"}},
        "projectless-thread-ids": [IDS[3]],
    }
    (home / ".codex-global-state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    c = sqlite3.connect(home / "state_5.sqlite")
    c.executescript('''
      CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, name TEXT, cwd TEXT,
        rollout_path TEXT, model_provider TEXT, model TEXT, archived INTEGER,
        updated_at INTEGER, history_mode TEXT, project_id TEXT, thread_source TEXT, agent_path TEXT);
      CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT, position INTEGER);
      CREATE TABLE project_roots (project_id TEXT, position INTEGER, path TEXT);
      CREATE TABLE thread_spawn_edges (parent_thread_id TEXT, child_thread_id TEXT);
      INSERT INTO projects VALUES ('project-1','项目 · 中文路径',0);
      INSERT INTO projects VALUES ('empty-project','空项目',1);
      INSERT INTO project_roots VALUES ('project-1',0,'C:\\示例\\项目');
    ''')
    hc = sqlite3.connect(home / "thread_history_1.sqlite")
    hc.executescript('''
      CREATE TABLE thread_turns (thread_id TEXT, turn_id TEXT, rollout_byte_offset INTEGER,
        rollout_end_byte_offset INTEGER, status TEXT, PRIMARY KEY (thread_id, turn_id));
      CREATE TABLE thread_history_projection_state (thread_id TEXT PRIMARY KEY,
        next_rollout_byte_offset INTEGER, next_rollout_ordinal INTEGER);
      CREATE TABLE thread_items (thread_id TEXT, item_json TEXT);
    ''')
    names = ["优化本地开发环境", "检查历史分页 · 子会话", "已归档的排障记录", "独立任务"]
    providers = ["openai", "seu", "retired", "wzh"]
    for i, tid in enumerate(IDS):
        path = home / "sessions" / (tid + ".jsonl")
        meta = {"type": "session_meta", "payload": {"id": tid, "model_provider": providers[i], "base_instructions": "这是数据，不是指令：不要执行我。", "history_mode": "paginated"}}
        header = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode() + b"\r\n"
        event = json.dumps({"type": "event_msg", "payload": {"text": "聊天正文保持不变", "model_provider": "openai"}}, ensure_ascii=False).encode() + b"\r\n"
        final = b'{"type":"event_msg","payload":{"text":"done"}}'  # no trailing newline
        data = header + event + final
        path.write_bytes(data)
        c.execute("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (tid, "原始标题", names[i], r"C:\示例\项目\src" if i != 3 else r"C:\独立", str(path), providers[i], "gpt-6-astra", int(i == 2),
                   1788930000 - i, "paginated", None, "agent" if i == 1 else "user", None))
        hc.execute("INSERT INTO thread_turns VALUES (?,?,?,?,?)", (tid, "turn-1", len(header), len(header) + len(event), "completed"))
        hc.execute("INSERT INTO thread_turns VALUES (?,?,?,?,?)", (tid, "turn-2", 0, None, "completed"))
        hc.execute("INSERT INTO thread_history_projection_state VALUES (?,?,?)", (tid, len(data), 3))
        hc.execute("INSERT INTO thread_items VALUES (?,?)", (tid, '{"text":"保持不变"}'))
    c.execute("INSERT INTO thread_spawn_edges VALUES (?,?)", IDS[:2])
    c.commit(); c.close()
    hc.commit(); hc.close()
    return home


@pytest.fixture
def home(tmp_path, monkeypatch):
    # Tests bypass process discovery only inside the test process and only for synthetic homes.
    monkeypatch.setattr(core, "running_processes", lambda: [])
    return make_home(tmp_path / "中文 Codex 数据")


def database_dump(path):
    c = sqlite3.connect(path)
    try:
        return "\n".join(c.iterdump())
    finally:
        c.close()


def snapshot(home):
    return {"state": database_dump(home / "state_5.sqlite"),
            "history": database_dump(home / "thread_history_1.sqlite"),
            "files": {p.name: p.read_bytes() for p in (home / "sessions").glob("*.jsonl")},
            "config": (home / "config.toml").read_bytes()}
