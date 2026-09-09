# Security Policy

## Supported versions

当前仅维护最新发布版本。

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| Older versions | No |

## Reporting a vulnerability

请优先使用 GitHub 仓库 **Security → Report a vulnerability** 私下报告安全问题。

报告中可以包含受影响版本、复现步骤和使用合成数据得到的最小示例，但请勿提交以下内容：

- API Key、Token、Cookie 或认证文件；
- 真实会话 JSONL、SQLite 数据库或备份；
- 未脱敏的聊天内容、Provider URL 或个人路径。

如果仓库尚未启用私密漏洞报告，请只创建一个不含漏洞细节和敏感数据的 Issue，请求维护者建立私密沟通渠道。

普通功能缺陷可以直接提交公开 Issue，但应使用 `tools/create_demo.py` 生成的合成数据复现。
