# Changelog

本项目的重要变更记录在此文件中。版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-09-09

### 新增

- Windows 图形界面：按项目浏览、搜索和批量选择 Codex 会话。
- 从本地配置读取 Provider，并支持预览后批量切换。
- 命令行工具：查询、检查、切换、查看操作及恢复。
- 会话文件与 SQLite 一致性备份、自动回滚和中断恢复。
- 对会话文件、任务 ID、Provider 和历史索引的完整校验。
- 中文、长路径、扩展盘符路径和 UNC 路径显示支持。
- 原创酒红色应用图标和桌面快捷方式安装脚本。
- 56 项自动化测试及 Windows GitHub Actions 工作流。

### 安全说明

- 仅修改选中会话的 Provider，不修改模型、聊天正文、项目归属或全局默认配置。
- 应用变更和恢复前必须完全退出 Codex、CLI 及相关编辑器后端。
- 本项目是独立社区工具，不是 OpenAI 或 Codex 官方产品。

[0.1.0]: https://github.com/EwwwzhI/codex-provider-switcher/releases/tag/v0.1.0
