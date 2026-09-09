from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from . import core


PATH_KEYS = {"home", "cwd", "rollout_path", "path", "backup"}
PATH_LIST_KEYS = {"roots", "project_roots"}


def display_json_paths(value, key=None):
    """Return a presentation copy with Windows extended path prefixes hidden."""
    if isinstance(value, dict):
        return {name: display_json_paths(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [display_json_paths(item, key) for item in value]
    if isinstance(value, str) and key in PATH_KEYS | PATH_LIST_KEYS:
        return core.display_path(value)
    return value


def main(argv=None):
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="按任务 ID 查询与离线切换 Codex 会话 Provider")
    parser.add_argument("--codex-home", help="Codex 数据目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="列出会话（默认普通未归档会话）")
    listing.add_argument("--search", default="")
    listing.add_argument("--provider")
    listing.add_argument("--include-archived", action="store_true")
    listing.add_argument("--include-agents", action="store_true")
    show = sub.add_parser("show", help="显示一个会话及完整文件检查")
    show.add_argument("--thread-id", required=True)
    switch = sub.add_parser("switch", help="预览或执行 Provider 切换")
    switch.add_argument("--thread-id", action="append", required=True, help="可重复提供")
    switch.add_argument("--to-provider", required=True)
    mode = switch.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    restore = sub.add_parser("restore", help="恢复某次操作")
    restore.add_argument("--operation-id", required=True)
    sub.add_parser("operations", help="列出备份与未完成操作")
    # Accept common options before or after the subcommand.
    for p in (listing, show, switch, restore, sub.choices["operations"]):
        p.add_argument("--codex-home", default=argparse.SUPPRESS)
        p.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        home = core.home_path(args.codex_home)
        if args.command == "list":
            result = core.catalog(home)
            query = args.search.casefold()
            result["threads"] = [r for r in result["threads"]
                                 if (args.include_archived or not r["archived"])
                                 and (args.include_agents or not r["is_agent"])
                                 and (not args.provider or r["provider"] == args.provider)
                                 and query in " ".join(str(r[k]) for k in ("name", "id", "cwd", "project_name")).casefold()]
        elif args.command == "show":
            rows = core.catalog(home)["threads"]
            result = next((r for r in rows if r["id"] == args.thread_id), None)
            if result is None:
                raise core.SwitchError("任务 ID 不存在。")
            try:
                # Validate without requiring the historical provider to still be configured.
                target = result["provider"] if result["provider"] in core.providers(home) else "openai"
                core.preview(home, [args.thread_id], target)
                result["validation"] = "文件、任务 ID、Provider 和历史索引检查通过"
            except (core.SwitchError, OSError, ValueError, sqlite3.Error) as e:
                result["validation"] = str(e)
        elif args.command == "switch":
            result = core.preview(home, args.thread_id, args.to_provider) if args.dry_run else core.switch(home, args.thread_id, args.to_provider)
            if args.dry_run:
                result["dry_run"] = True
        elif args.command == "restore":
            result = core.restore(home, args.operation_id)
        else:
            result = {"operations": core.operations(home)}
        if args.json:
            print(json.dumps(display_json_paths(result), ensure_ascii=False, indent=2))
        elif args.command == "list":
            print(f"{len(result['threads'])} 个会话 | {home}")
            for r in result["threads"]:
                name = " ".join(r["name"].split())[:80]
                print(f"{r['id']}  [{r['provider']}]  {r['project_name']} / {name}" + (f"  ({r['error']})" if r["error"] else ""))
        elif args.command == "switch" and args.dry_run:
            for e in result["entries"]:
                print(f"{e['id']}  {e['before_provider']} → {e['after_provider']}  模型：{e['model']}  字节变化：{e['byte_delta']:+d}")
            print(f"预览完成，{result['count']} 个会话需要修改；未写入任何数据。")
        else:
            print(json.dumps(display_json_paths(result), ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        error = {"error": str(e), "changed": "请检查 operations 中的操作状态" if args.command in ("switch", "restore") else False}
        if args.json:
            print(json.dumps(error, ensure_ascii=False))
        else:
            print("错误：" + str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
