# skill-check

检查 coding agent 的 `SKILL.md`：frontmatter、触发说明、断链与危险模式提示。零依赖 Python 3 CLI。

Validate agent skill folders (SKILL.md frontmatter, trigger cues, broken links, secret-like patterns). Zero-dependency Python 3 CLI.

## 做什么

Agent skill / plugin 通常用带 YAML frontmatter 的 `SKILL.md` 描述名称与触发场景。本工具扫描单个 skill、skill 目录，或装有多个 skill 的父目录，并输出 ERROR / WARN / INFO。

| 级别 | 检查项 |
|------|--------|
| ERROR | 缺少 frontmatter；缺少或空的 `name` / `description` |
| WARN | 描述未标明何时使用；描述过短；正文过短；相对 Markdown 链接断链；正文疑似含凭证模式 |
| INFO | 名称、描述长度、正文行数 |

退出码：有 ERROR 为 `1`，仅 WARN/INFO 为 `0`。

## 安装 / 用法

需要 Python 3.8+。无第三方依赖，克隆后直接运行：

```bash
git clone https://github.com/temptation2017/skill-check.git
cd skill-check
python3 skill_check.py examples/
python3 skill_check.py examples/good-skill
python3 skill_check.py path/to/SKILL.md --json
```

## 示例输出

```text
== .../examples/good-skill/SKILL.md ==
  name: csv-summary
  [INFO] summary: name=csv-summary description_len=... body_lines=...

== .../examples/missing-desc/SKILL.md ==
  name: stub-helper
  [ERROR] missing_description: missing or empty `description`
  ...

Checked 3 skill(s): 1 ERROR, ... WARN
```

## 限制

- Frontmatter 解析器只支持简单的 `key: value` 与引号字符串，不是完整 YAML。
- 「何时使用」用中英文关键词启发式判断，可能误报或漏报。
- 凭证检测只匹配较明确的模式（如 `api_key=`、`BEGIN PRIVATE KEY`），单独出现 `token` 不会报警。

## 后续可改进

- 支持 frontmatter 多行描述（`|` / `>`）
- 与常见 agent skill 目录规范对齐的 schema 校验
- 可选 JSON Schema / 插件清单联动

## License

MIT © 2026 temptation2017
