# PDF 来源阅读证据

- Work Item：`HA-0001`
- 日期：2026-09-08
- 方法：Poppler 读取元数据并以 110/200 DPI 渲染全部页面；macOS Vision 使用 `zh-Hans`/`en-US` OCR；正文页人工目视复核。PDF 本身为图片型页面，`pdftotext` 无有效正文。

## 来源清单

| 文件 | 页数 | SHA-256 |
|---|---:|---|
| `01-codeact.pdf` | 7 | `334dc22ad75fbf787e9c1658b0e3249e89afdafdc171d6056d87dbef5b446d74` |
| `02-multi-agent.pdf` | 5 | `71d3ba69eeb34550fd623d6dd2aaa0c1300291322d5512975ed528f965f0334b` |
| `03-smolagents-report.pdf` | 6 | `4c070ec1d9488e73aac22323faa6293ecf0e20472edb004ffa72824a7ded3f26` |

原始文件：

- `/Users/weberzhao/.botmux/data/attachments/om_x100b6535eb24bca8b1f5659edf2ca5b/01-codeact.pdf`
- `/Users/weberzhao/.botmux/data/attachments/om_x100b6535eb24b0a8b4bf247ba0a0617/02-multi-agent.pdf`
- `/Users/weberzhao/.botmux/data/attachments/om_x100b6535eb2408a4b32ec8f2be9c34c/03-smolagents-report.pdf`

## 可复核结论

1. CodeAct 用代码组合计算、变量和条件，比大量细粒度工具更适合数据分析。
2. Smolagents 示例把自定义 Tool/MCP 注入 CodeAgent；课程截图只能作为模式说明，不能锁定当前 SDK API。
3. 多 Agent 示例用 CodeAgent 主 Agent 和联网搜索子 Agent隔离上下文，但会增加调用、状态和失败路径。
4. 模型代码执行是明确安全边界；本地执行不应作为生产隔离方案。

## 官方交叉核验

- `https://huggingface.co/docs/smolagents/reference/agents`
- `https://huggingface.co/docs/smolagents/main/tutorials/secure_code_execution`
- `https://huggingface.co/docs/smolagents/reference/python_executors`
- `https://huggingface.co/docs/smolagents/reference/tools`

## 局限

- OCR 可能误识别代码标点和小字号参数，未将 OCR 文本视为可复制 API。
- 未在本任务安装或运行 Smolagents，也未完成版本、许可、取消、检查点和远程执行探针。
- PDF 没有证明 `doubao-seed-2.1-turbo` 图片能力；该路由来自用户指定，另行探针。

