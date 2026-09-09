# 模型服务接入与验证

## 当前选择

使用用户指定的 **DeepSeek `deepseek-v4-flash`**，服务地址为 `https://api.deepseek.com`，不自动替换模型。密钥仅放在忽略提交的 `backend/.env`，禁止写入浏览器、响应或日志。2026-09-09 已实际读取 DeepSeek 官方首页、Chat API、Thinking Mode 和 JSON Output 文档核对协议。

同日完成一次真实连接探测：约 888 毫秒，输入 9 tokens、输出 2 tokens、合计 11 tokens。此后实际页面完整生成已运行五个 Agent 并产生行程，每个执行角色都有真实模型用量记录；营业、费用及路线等未知或冲突项目仍由规则明确提示，不能据此宣称全部 P0 已通过验收。

```dotenv
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_API_KEY=填写你自己的密钥
```

## 连接探测契约

`LlmProvider.probe()` 只发送一次非流式 `POST /chat/completions`，提示词固定为 `Reply only with OK.`，不发送旅行需求或历史对话。DeepSeek 请求使用 `max_tokens: 32` 和 `thinking: {type: "disabled"}`，限制输出并关闭默认开启的思考模式。输出上限不代表零费用，实际计费以服务商为准。

成功条件为收到非空文本并通过响应结构检查；不要求回复严格等于 `OK`。只返回 `reachable`、`received_text`、UTC `fetched_at` 和服务商实际提供的整数 token 用量；缺少用量时为 `null`。不返回原始文本、推理内容、服务商错误正文或密钥。拒绝、空结果、无效 JSON 和异常用量均不报告成功。

超时、429、5xx 可由用户手动重试；不自动重试、切换模型或跟随重定向，避免重复调用。DeepSeek 402 返回 `PROVIDER_QUOTA_EXCEEDED`，提示检查账户余额；400/404/422 返回 `PROVIDER_INVALID_REQUEST`，提示检查服务地址、模型与参数。鉴权失败、连接失败和无效配置使用脱敏错误码。

## 兼容范围

URL 末尾已有 `/v1` 或自定义路径时予以保留，再追加 `/chat/completions`。外部地址要求 HTTPS；本地 `localhost`、`127.0.0.1`、`::1` 可用 HTTP。拒绝 URL 用户信息、查询参数和片段。客户端统一关闭环境代理和重定向并设置超时。

DeepSeek 特定参数仅用于 `api.deepseek.com`。其他服务走基础 Chat Completions 契约，以 `max_completion_tokens` 限制输出；兼容性须逐家验证，不失败后自动换参重发。OpenAI 官方两处文档入口当日返回 403，未完成其最新协议在线核验。当前规划按已验证的 DeepSeek 协议运行，不使用 Responses。

DeepSeek 官方 JSON 模式使用 `response_format: {type: "json_object"}`，提示词包含 `json` 和格式示例；后端还验证结构、真实候选 ID、全量日期、活动时间及住宿选择。空输出、截断、无效结构或伪造候选直接失败，不自动再请求一次。

## HelloAgents 编排

固定 `hello-agents==0.2.9`，使用官方 `Agent` 与 `Tool` 基类创建独立的异步角色和受限工具。覆写异步调用以支持取消，不借助不可取消的同步线程；不记录原始提示词、模型推理或默认会话文件。此版本导入评估模块需要 `huggingface-hub==0.36.2`，已补入基础依赖；运行不会下载数据集或其他模型。

| 角色 | 模型决策与实际工具 | 调用上限 |
| --- | --- | --- |
| 景点 | 选择游览类别关键词，以官方 `110000` 风景名胜类型查询 POI | 1 次模型、1 次检索，最多 10 个候选 |
| 住宿 | 根据偏好选择酒店关键词，以官方 `100000` 住宿类型查询 POI | 1 次模型、1 次检索，最多 3 个候选；无住宿需求时跳过 |
| 天气 | 选择城市定位关键词，从真实 POI 确认行政区码，再查预报 | 1 次模型、2 次高德调用 |
| 营业 | 在景点完成后选择真实 ID，查询对应详情 | 1 次模型、最多 10 次详情请求，最多 3 个并发 |
| Planner | 汇总专业角色结果，生成按日 JSON 草案 | 1 次模型，每天 1–3 个活动 |

前三个角色并行；营业角色依赖景点结果，可与其他角色重叠。每个专业角色最多输出 600 tokens，Planner 最多 3500 tokens，均关闭思考模式。工具名称和参数经过白名单、长度和候选范围验证；工具输出只作为不可信数据输入 Planner，不能扩大工具权限。

返回候选还必须通过六位 `typecode` 校验：景点前缀为 `11`，住宿为 `10`；行政地名、车站、机场、公司及缺少类型码的地点不能进入相应候选集。景点关键词不重复城市名，避免将城市定位结果当作游览安排。筛选后没有有效景点则失败，不偷偷增加一次搜索或编造候选。

数据阶段最多 25 秒，Planner 最多 20 秒，总任务最多 60 秒，并为后续确定性校验和保存留时间。可选数据失败时标明降级；无景点、无效 Planner 结果或持久化事件失败则整个任务失败。取消会传播到未完成模型请求和工具请求。有住宿需求且有真实酒店候选时，Planner 必须选择其中一个；无需求或无候选才允许为空。

营业详情可提供原始营业时间文本，但不能证明出行当日开放；营业角色持续显示此限制。模型不会填造票价、房价、缺失天气或路线。API 展示的 Agent 摘要仅含状态说明、工具名称、候选数量、实际 token 用量和来源引用。

## 测试与官方依据

在 `backend/` 执行 `.venv\Scripts\python -m pytest tests/test_llm_provider.py tests/test_llm_json.py tests/test_planning_agents.py`。89 项测试通过，覆盖协议错误、敏感信息隔离、真实框架实例、工具边界、地点类别、角色并发与依赖、取消、阶段超时、持久化失败及不可信 Planner 结果。夹具注明合成来源与参考日期，不消耗真实 API 配额。HelloAgents 有一项来自其依赖源码的 Pydantic 弃用警告，当前不影响测试与运行。完整真实验证状态以根目录 README 为准。

- [首次调用与服务地址](https://api-docs.deepseek.com/)
- [Chat Completions 参数](https://api-docs.deepseek.com/api/create-chat-completion/)
- [Thinking Mode 开关](https://api-docs.deepseek.com/guides/thinking_mode/)
- [JSON Output 使用限制](https://api-docs.deepseek.com/guides/json_mode/)
- [错误码与余额不足](https://api-docs.deepseek.com/quick_start/error_codes/)
- [Datawhale 教程与官方框架来源](https://github.com/datawhalechina/hello-agents)
- [HelloAgents 官方源码](https://github.com/jjyaoao/HelloAgents)
- [固定版本及依赖元数据](https://pypi.org/project/hello-agents/0.2.9/)
