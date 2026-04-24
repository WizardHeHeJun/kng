# Lark Test Agent (MVP)

一个最小可运行工具：输入飞书文档 URL，自动读取内容并生成测试设计产出。
同时提供双知识库版本（基础能力库 + 项目知识库），支持多项目复用。

## 1. 前置条件

- 已安装 Python 3.10+
- 已安装 `lark-cli`
- 已完成飞书授权（建议 user 身份）：
  - `lark-cli config init --new`
  - `lark-cli auth login --scope "drive:drive:readonly docs:document:readonly wiki:wiki:readonly"`

## 2. 安装依赖

```bash
pip install -r requirements.txt
```

## 3. 运行

```bash
python tools/lark_test_agent.py --url "https://your-domain.feishu.cn/docx/xxxxxxxx"
```

可选参数：

- `--identity user|bot` (默认 `user`)
- `--output-dir test-output` (默认 `test-output`)
- `--model gpt-4.1-mini` (默认 `gpt-4.1-mini`)

## 3.1 双知识库运行（推荐）

```bash
python tools/dual_kb_test_agent.py --project-id demo-game --url "https://your-domain.feishu.cn/docx/xxxxxxxx"
```

可选参数：

- `--kb-root kb`（知识库根目录）
- `--top-k 5`（每个知识库命中条数）
- `--identity user|bot`
- `--model gpt-4.1-mini`

## 3.2 一键验证（给新人）

```bash
validate_run.bat demo-game "https://your-domain.feishu.cn/docx/xxxxxxxx"
```

如果不传 URL，脚本会提示你粘贴文档链接：

```bash
validate_run.bat demo-game
```

## 4. 输出

默认输出到 `test-output/`：

- `*-source.md`：抓取到的原始文档内容
- `*-test-design.json`：结构化测试产出
- `*-test-design.md`：可读版测试设计

## 5. AI 生成模式

- 设置了 `OPENAI_API_KEY` 时：调用 OpenAI 生成高质量测试产出
- 未设置时：自动降级为模板化 fallback，也会给出可评审初稿

## 6. 下一步建议

- 把 JSON 结果接入 TestRail/Jira
- 增加“回归建议生成”和“覆盖率缺口检查”
- 增加飞书文档回写（自动写入评审文档）

## 7. 双知识库目录

```text
kb/
  capability/                 # 通用测试能力库（跨项目复用）
  projects/
    demo-game/                # 项目知识库（按项目隔离）
schemas/
  test_design.schema.json
tools/
  lark_test_agent.py          # 单文档版本
  dual_kb_test_agent.py       # 双知识库版本
validate_run.bat              # 一键验证入口
```
