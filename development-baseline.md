# 智能旅行决策系统开发基线

版本：1.7 · 更新日期：2026-09-09 · 状态：接入 HelloAgents 角色、DeepSeek 与高德协作规划、真实任务进度、校验和 MySQL 行程历史；互动地图、PDF 等完整 P0 尚未通过验收。实现边界见 [规划说明](docs/planning.md)。

本文将已确认的 MySQL、本地部署、Vite 和多 Agent 展示要求落实为开发约定。产品需求见 [PRD](smart-travel-decision-system-v1.0-prd.md)，详细设计见 [改进版方案](第十三章%20智能旅行助手（改进版系统设计与实现方案）.docx)。原始教学文档用于参考，不代表本项目已具备对应功能。后续变更应同步本文、PRD、调研报告和改进版方案。

## 1. 已确认的技术与交付选择

| 项目 | 开发约定 |
| --- | --- |
| 前端 | Vue 3 + TypeScript；Vite 负责开发服务器与构建；Vue Router、Pinia 按页面和状态管理需要使用 |
| 后端 | Python 3.11–3.13、FastAPI、Pydantic 2；本机虚拟环境使用 Python 3.12.14；接口与 Agent 编排分层 |
| Agent | HelloAgents；景点、住宿、天气、营业状态四个专业 Agent 与 Planner；P1 增加 Critic |
| 数据库 | 本地 MySQL 8.4，InnoDB、utf8mb4；SQLAlchemy 2 + asyncmy，Alembic 管理迁移 |
| 部署 | 同一台电脑本地运行；前端 127.0.0.1:5173、后端 127.0.0.1:8000、MySQL 127.0.0.1:3306 |
| 演示对象 | 单个操作者操作 Web 页面；支持填写同行人数，不做账号、远程共享和多人同时编辑 |
| 首版范围 | 中国大陆单个目的地城市、连续 1–7 天、1–10 名出行人；日期按 Asia/Shanghai 校验 |
| 外部能力 | DeepSeek deepseek-v4-flash（用户指定）；高德 Web 服务 POI/步行/天气；均已完成最小真实调用，营业状态和价格仍须逐项验证 |

上述天数和人数上限是首版控制复杂度的默认开发约定，可通过后续需求变更调整。Vite 不替代 Vue。当前已建立前后端源码、依赖清单、四张 P0 表的模型和迁移脚本；本机 MySQL 8.0.42 的 smart_travel 已应用初始迁移并通过真实读写与约束测试。DeepSeek 和高德服务已接入规划与本地保存流程，当前结果保留未知与降级说明。初始迁移兼容 8.0.16+，保留 8.4 作为设计目标。

后端依赖已安装到 `backend/.venv`，并固定在 `backend/requirements-lock.txt`；依赖检查和 241 项后端测试全部通过。asyncmy 已通过真实连接与在线迁移版本检查，实际启动 FastAPI 后数据库就绪接口返回 `ready`。

前端已安装并通过 `frontend/package-lock.json` 锁定依赖，使用 Vite 8.2.2 与兼容的 Vue 插件。`npm ci` 安装、类型检查、15 项客户端及轮询测试和生产构建已通过。本轮成功启动本地前后端，浏览器已验证有效提交、修改字段后重新确认、8 天行程错误提示；后端直连和 Vite 代理的数据库就绪接口均返回 `ready`，浏览器控制台无错误或警告。本轮还验证了真实五 Agent 生成、每日切换、历史恢复和窄屏布局。服务保持运行供本机浏览，`npm run preview` 尚未验证；完整验证边界见 [README](README.md)。

## 2. 分期交付清单

| 阶段 | 功能与完成边界 |
| --- | --- |
| P0 | F001 需求结构化；F002 行程生成；F003 地图路线校验；F004 天气营业校验；F012 PDF 导出；F013 多 Agent 实际执行展示 |
| P0 基础能力 | MySQL 保存确认后的需求、任务、Agent 执行摘要、结果快照；本地历史查看；结构化预算上限输入与候选筛选 |
| P1 | F005 确定性预算和超支建议；F006 Critic；F007 单项编辑后的路线、时间、费用及冲突重算 |
| P2 | F008 多人偏好协调；F009 事件驱动重规划 |
| P3 | F010 预订服务接入评估；F011 高级决策解释与版本对比界面 |

P0 结果可查看、重新提交需求生成和导出，不提供单项编辑入口。P0 已展示数据依据和风险摘要；P1 内部版本快照用于编辑一致性；P3 才提供面向用户的完整版本对比。支付、真实预订履约、实时导航、原生移动端和公网部署不在首版范围内。

## 3. 需求与预算契约

### 3.1 输入与澄清

| 字段 | 类型与规则 | 收集方式 |
| --- | --- | --- |
| origin | 非空城市名称 | 必填；可与目的地相同 |
| destination | 单个中国大陆城市 | 必填；规划仅覆盖该城市 |
| start_date / end_date | YYYY-MM-DD；开始日期不早于当地今天；结束不早于开始；含首尾最多 7 天 | 必填；相对日期转换后让用户确认 |
| travelers | 整数 1–10 | 必填；表示全部出行人数 |
| budget_total | 正数，最多两位小数，最大 99999999.99 元；API 以十进制字符串传输 | 必填；全部出行人目的地游玩费用上限 |
| currency / budget_scope | 固定 CNY / destination_only | 确认页和结果页持续显示 |
| styles | 字符串数组 | 可选；默认空数组，表示不限 |
| hotel_preference | 不限、星级或民宿偏好 | 可选；默认不限 |
| pace | 紧凑、均衡、休闲 | 可选；默认均衡 |
| daily_window | 当日开始与结束时间，开始早于结束 | 可选；默认 09:00–18:00 |
| rooms | 整数 1–travelers；无住宿需求时为 0 | 多日默认建议 ceil(travelers/2)，必须在确认页展示；当天往返默认为 0 |

只追问缺失的必填字段；可选字段给出可修改的默认值，统一确认后开始规划。不得为凑齐字段数量编造偏好。不再使用“至少识别八项”作为验收条件。飞机舱位不进入首版模型；原始文本中的相关要求提示为首版不支持。

### 3.2 预算口径与阶段行为

预算指**全体出行人的目的地游玩总额**，包括门票、目的地住宿、餐饮、市内交通及明确列出的其他费用；**不包括出发地到目的地的往返飞机、火车等大交通费用**。页面不能简称为“全程总价”。输入“每人 2000 元、3 人”时可换算为总预算 6000 元，换算结果及费用范围必须确认。预算约束不等于实时成交报价。

P0 只负责收集预算、向候选检索与 Planner 传递预算约束、展示有来源的价格信息。结果显示“尚未完成费用精算”；不得承诺总额已在预算内，也不考核预算偏差率。

P1 采用 Decimal 和 MySQL DECIMAL(10,2) 保存金额，明细按人民币分四舍五入后汇总。门票按适用票价乘人数，住宿按每晚房价乘房间数乘晚数，餐饮按人数乘餐次，市内交通按路线段和计价单位计算，避免出租车整车费用再次乘人数。晚数为 end_date − start_date；特殊房型、儿童票、优惠价格未验证时标记估算，不当作确认价格。

无法确认的价格用 null 和 unknown 表示，记录缺失原因；只有明确免费且有来源时才记 0。已知费用小计不是完整预算。存在未知或过期费用时不得显示“预算充足”或“预算校验通过”；已知小计已超支仍应提示至少超支多少。字段包括 known_total、estimated_total、unknown_items、pricing_status 和 warnings；全部费用可比且有效时才能出具完整预算判断。

known_total 仅汇总有效已验证费用；estimated_total 为该小计加有效且明确标记的估算项，不能将未知或过期价格补为 0。pricing_status 为 not_calculated（P0 未精算）、complete（全部有效已验证）、estimated（有估算且无未知/过期）、incomplete（存在未知/过期）。estimated 只能给出估算总额及估算超支，不能称为预算校验通过；incomplete 分别显示有效已知小计、估算项及缺失项，不保证总价。预算偏差指标只接受 complete 样例。

示例：2 人、3 天 2 晚、1 间房，酒店 300×2、门票 80×2、餐饮 50×2×6、市内交通整车 120，总额为 1480 元；2000 元预算剩余 520 元。该示例为计算夹具，不是实时价格；若交通价格未知，只展示已知小计 1360 元及交通待确认。

## 4. Agent 编排与展示

P0 首先并行执行景点、住宿、天气 Agent；营业状态 Agent 在景点候选产生后查询对应 POI，可与仍在执行的其他任务并行。Planner 消费上述归一化结果生成草案，再由路线服务和营业/天气规则做确定性校验。营业查询依赖具体点位，不能为展示并行而在没有候选时制造调用。

专业 Agent 使用独立角色、输入输出协议和真实工具调用；界面名称必须与实际运行记录一致。交通适配器、路线校验器和预算计算器是服务，不包装成额外 Agent。P1 才将预算计算和 Critic 接入生成与编辑闭环。

每个 AgentRun 保存 agent_name、status、started_at、finished_at、duration_ms、attempt、summary、evidence_refs 和 error_code。状态为 queued、running、succeeded、degraded、failed、skipped；重试作为独立 attempt 记录。无需执行（例如当天往返不需要住宿）的 Agent 标为 skipped 并说明原因，缓存命中也标明来源。界面展示当前阶段、每个 Agent 的状态、耗时、工具名称、候选数量及简短结果，不展示原始思维链、完整提示词或密钥，不使用模拟百分比。

任务生命周期与阶段分开：status 为 queued、running、ready、degraded、failed；stage 为 validating、collecting、planning、checking、persisting，P1 增加 reviewing。前端每秒轮询，终态后停止；连接中断可按 task_id 恢复查询。ready 必须具备完整展示结果且必要校验已完成；有未知数据但仍可展示结果为 degraded；缺少有效候选、Planner 无法生成有效结构或数据库写入失败为 failed。

单任务总截止时间 60 秒，覆盖排队、Agent 调用、规则校验和结果持久化；重试必须消耗同一时间预算。专业数据收集建议最多 25 秒（包括依赖查询与重试），Planner 20 秒，校验及保存 10 秒，其余作为余量。最多重试一次且仅用于短暂错误。到达截止时间仍不能返回合规可展示结果时明确失败，不伪造路线或价格。P0 同时只执行一个规划任务，忙时新提交返回 409 TASK_BUSY，避免本地演示排队失控。

## 5. 本地数据存储

本地持久化属于 P0。确认规划时提示“确认后需求及结果将保存在本机”；不默认保存确认前的完整对话。不保存模型原始推理内容。用户主动删除行程时关联删除本地需求快照、结果、Agent 摘要和导出临时文件。

| 表 | 关键字段与关系 |
| --- | --- |
| trips | id、destination、start_date、end_date、travelers、budget_total DECIMAL(10,2)、currency、budget_scope、request_json、current_version、created_at |
| planning_tasks | id、trip_id、status、stage、trace_id、deadline_at、error_code、created_at、finished_at |
| agent_runs | id、task_id、agent_name、attempt、status、开始/结束时间、摘要 JSON、证据引用 JSON；唯一键 task_id + agent_name + attempt |
| trip_versions | trip_id、version、parent_version、reason、plan_json、validation_json、budget_json、created_at；唯一键 trip_id + version |
| plan_proposals（P1） | UUID id、trip_id、base_version、operation_json、candidate_json、status、expires_at；保存待确认编辑候选，P0 不建立此表 |

实体 ID 及其引用使用一致的 UUID 字符串类型；版本号使用正整数，版本引用通过 (trip_id, version) 定位。建立 task_id、trip_id 与创建时间索引，使用外键约束和事务。生成前 current_version=null，初版结果为 version=1；更新 current_version、插入结果快照和将任务标为 ready/degraded 在同一事务提交，提交成功后才向前端返回可用结果。JSON 用于有版本号的行程和证据快照，日期、状态、金额等查询字段单独建列。数据库时间存 UTC，旅行日期及活动时间携带 Asia/Shanghai 时区；API 时间戳使用 ISO 8601。

P0 使用单进程异步编排，MySQL 记录任务状态，运行中的协程句柄不持久化。进程启动将遗留 queued/running 任务及未结束的 Agent 记录标为 failed / SERVER_RESTARTED，展示重试入口；重试产生新任务，已完成结果仍可读取导出。不承诺断点续跑，不要求 Redis、Celery 或消息队列。Agent 不直接写共享行程表，由编排层持久化归一化结果。Alembic 迁移管理表结构，运行账号只授予所需应用权限。

## 6. 接口与页面边界

| 阶段 | 接口 | 行为 |
| --- | --- | --- |
| P0 | POST /api/requirements/parse | 解析用户输入，返回 draft_request、missing_required、suggested_defaults；模型不可用时切换结构化表单 |
| P0 | POST /api/trips/plan | 接收已确认字段、费用范围和 defaults_confirmed；持久化需求/任务，202 返回 task_id、trip_id |
| P0 | GET /api/tasks/{task_id} | 返回状态、阶段、各 Agent 摘要、错误/降级原因、结果链接 |
| P0 | GET /api/trips | 分页列出本机历史行程 |
| P0 | GET /api/trips/{trip_id} | 返回确认后的需求和当前版本结果；未生成完成时给出任务状态 |
| P0 | DELETE /api/trips/{trip_id} | 用户确认后删除本地历史及关联数据；运行中的行程返回 409 |
| P0 | POST /api/trips/{trip_id}/export | 接收 version，返回 application/pdf；无可导出结果返回 409 |
| P1 | PATCH /api/trips/{trip_id}/versions/{version}/items/{item_id} | 提交 move/delete/replace/update_time 操作；对旧版本操作返回 409 VERSION_CONFLICT |
| P1 | POST /api/trips/{trip_id}/validate | 重算确定性校验和预算，返回当前结果及问题 |
| P2 | POST /api/trips/{trip_id}/events | 登记天气、闭馆或延误事件，触发受影响范围重规划 |

错误统一为 code、message、request_id、可选 details；非法字段用 422，资源不存在用 404，MySQL 不可用用 503，不返回成功 task_id。P1 编辑先持久化候选预览，返回 proposal_id、base_version 与 requires_confirmation；通过 POST /api/trips/{trip_id}/proposals/{proposal_id}/confirm 确认。提案状态 pending、confirmed、expired、discarded，默认保留待确认状态 30 分钟；GET /api/trips/{trip_id}/proposals/{proposal_id} 支持刷新后恢复预览。确认时锁定行程，检查未过期且父版本仍为 current_version，再分配 current_version+1 并事务提交，同时废弃同父版本其他待确认提案。父版本变化或过期返回 409，重复确认同一已提交提案返回其已生成版本。不能在“尚需确认”时先替换当前版本。

P0 页面为需求输入及确认、规划进度、行程结果、本地历史。结果页显示日期日程、地图路线、天气营业风险、预算范围、数据来源和 PDF 操作。PDF 使用后端中文字体排版和静态地图快照；地图无法导出时保留文字路线并说明缺图，保留版本、生成时间、未验证事项和预算阶段标记。

## 7. 外部数据与本地配置

本地部署仍需联网调用地图、天气及模型，不等于离线运行。开发先建立真实 API 冒烟验证记录，再接入业务。地图/天气优先高德，营业窗口可用 POI 或官方信息，但临时闭馆不能仅凭常规营业时间推断；出行日期超出天气预报窗口时显示“预报尚不可用”。酒店和票价没有可用来源时明确标估算或未知。

Evidence 至少包括 source、fetched_at、expires_at、status（verified/estimated/stale/unknown）、可选 source_url。有来源不代表永久准确，结果始终是基于当前数据的预测。建议缓存 TTL：天气 30 分钟、路线 30 分钟、POI 24 小时、营业窗口 6 小时、价格 1 小时；以供应商约束和实际查询时间为准，过期缓存不能计入已验证到达率或完整预算通过。

后端 .env 保存 DATABASE_URL、LLM_API_KEY、LLM_BASE_URL、LLM_MODEL、AMAP_WEB_SERVICE_KEY；仓库只保留 .env.example 占位符。前端仅有 VITE_API_BASE_URL 和域名受限的公开地图 JS 标识 VITE_AMAP_JS_KEY；VITE_ 前缀变量会进入浏览器产物，不存模型密钥、数据库口令或地图服务端密钥。地图 SDK 安全配置需代理时放在后端。日志仅记录请求标识和脱敏摘要。

确认页说明联网规划会按需将必要的位置、日期或偏好发送给对应模型和数据服务；本地保存不代表所有数据处理都在本机完成。各适配器仅发送完成查询所需字段，不向供应商发送数据库记录、完整历史或无关个人信息。

服务绑定回环地址，CORS 仅允许明确的本地前端来源；无登录的本地方案不开放到局域网或公网。开发服务器、FastAPI 与 MySQL 分别启动即可，无需 Docker 或云服务。前端使用 Vite 代理 /api 到后端；本地生产演示可使用构建产物配合后端静态文件服务，Vite preview 仅用于本机预览。

## 8. 工程目录与命令计划

以下结构已建立；模型与高德适配器、Agent 编排、规则校验和业务持久化服务已实现，导出等能力待后续补齐：

```text
frontend/                 Vue 页面、组件、状态及 API 客户端
backend/app/api/          HTTP 契约
backend/app/agents/       专业 Agent 与 Planner、后续 Critic
backend/app/services/     编排、路线规则、预算、导出
backend/app/providers/    模型、地图、天气及营业数据适配器
backend/app/models/       SQLAlchemy 表模型
backend/app/schemas/      Pydantic 请求与响应
backend/migrations/       Alembic 迁移
backend/tests/            契约、规则、编排、持久化测试
tests/e2e/                浏览器完整流程
tests/fixtures/           固定样例及来源说明
```

启动和验证步骤见 [README](README.md)。后端已使用 pytest；前端初始 API 客户端测试使用 Node 内置测试运行器，组件测试后续采用 Vitest，完整流程后续采用 Playwright。当前新增 POST /api/requirements/validate 作为工程阶段的无状态字段校验入口，不保存需求、不代替后续自然语言解析或规划接口。GET /api/health 检查 API 存活，GET /api/health/ready 检查 MySQL 连接及迁移版本。

## 9. 验收口径与样例

所有指标均为待验收目标。固定夹具用于可重复回归，不能替代真实 API 性能和价格准确性证据。测试记录保留输入、参考时间、数据版本、模型版本、运行硬件和错误/降级数量。

| 指标 | 统计与通过条件 |
| --- | --- |
| P0 首次规划耗时 | 本地并发 1，20 次有效输入的真实调用；从确认请求被后端接收到 ready/degraded 结果已持久化为止，最近秩法 p95（排序第 19 个）<60 秒。记录失败、超时、冷/热缓存，失败/超时样本视为未达标，按正无穷计入分位数且不从分母移除；60 秒总截止失败不能算完成 |
| P0 按时段到达率 | 分母为样本所有应校验的相邻活动路线段；分子为来源有效、预计到达不晚于下个活动开始、游览区间位于营业窗口且活动起止均在确认的 daily_window 内的段数。未知、过期、不可达和冲突均留在分母且不计分子；合计≥90%，展示未验证数量 |
| P0 降级行为 | 对地图、天气、营业、模型分别注入超时、缺字段、陈旧数据；100% 返回结构化降级或失败原因且在截止时间内结束，不保证全部生成行程；数据库失败单独断言503/失败状态 |
| P1 预算偏差 | 至少10个来源可追溯、费用完整、同币种/人数/日期/计价单位的参考样例；abs(计算总额−参考总额)/参考总额，每例<15%，参考总额>0；含未知费用的样例单独报告数量和原因，不宣称达到精度目标 |

回归数据至少包含：必填缺失及默认确认、同城旅行、过去日期、7天边界、跨城误排、通勤超时、暴雨与超预报期、营业未知、Agent 单独失败、所有候选缺失、PDF 地图失败、本地重启后查询历史。P1 增加人数/房间/晚数/计价单位、免费与未知、超支、编辑版本冲突；P2 增加延误冻结已完成活动。日期由固定参考时钟生成未来日期，避免夹具自然过期。

到达时间按上个活动结束时间加通勤和显式缓冲计算，不能让 Planner 自填的到达时间通过自检；活动起止必须同时满足营业窗口及确认的每日活动时段。路线和营业校验属于对数据支持程度的判断，不承诺真实出行绝不延误。

## 10. 实施顺序与待核实资源

1. 建立前后端脚手架和 MySQL 迁移，验证模型、地图与天气最小真实调用；记录套餐限制及费用。
2. 固定 TravelRequest、任务状态和 Agent 输出契约，用夹具跑通前端确认、状态轮询与本地保存。
3. 接入真实专业 Agent 和 Planner，完成路线/天气/营业规则以及 PDF，按 P0 样例验收。
4. 加入 P1 预算、Critic 和编辑一致性；P0 通过前不扩展到多人协作和自动重规划。

模型已确定为 DeepSeek deepseek-v4-flash，高德账号的 POI/步行/天气最小调用通过；账号剩余额度、套餐计费、营业和价格来源仍待按实际场景核实。采用适配器与显式降级继续推进，不把夹具展示成真实查询。课程截止日期和人员分工未提供，本基线按依赖顺序安排，不虚构完成日期。

## 11. 本次变更记录

- 2026-09-09：确认 Vue 3 + TypeScript + Vite、FastAPI、HelloAgents、MySQL 和本地部署；明确 Vite 的开发构建职责。
- 增加预算总额、币种、费用范围及默认值确认规则；将预算精算和偏差指标统一到 P1。
- 为 PDF 与多 Agent 展示分配 F012/F013；P0 纳入真实进度与本地持久化。
- 补齐状态机、API、MySQL 表、重启行为、数据降级和可复现实验口径，作为后续开发依据。
- 同日 v1.1：建立前后端工程骨架、字段校验和初始迁移；更新实际目录与启动入口，完整 P0 验收仍待后续开发。
- 同日 v1.2：完成 smart_travel 建库、0001_initial 迁移和 3 项真实 MySQL 集成测试，配置本地连接；异步驱动与应用就绪检查仍待完成。
- 同日 v1.5：完成后端虚拟环境与依赖锁定、asyncmy 真实连接和在线迁移检查；完成前端依赖锁定与生产构建。获准启动服务后，通过浏览器需求表单联调及 Vite 代理数据库就绪检查。
- 同日 v1.6：接入 DeepSeek 连接检测与高德 POI/步行/天气适配器，新增不联网的服务配置状态接口、页面卡片及显式检测命令。
- 同日 v1.7：优先接入真实多 Agent 生成，新增规划提交、状态轮询、行程读取与历史接口。模型选择真实 POI 并生成草案，确定性服务核验城市、日期、时段和步行衔接；结果、预算未知状态与执行摘要事务保存。加入忙时拒绝、共享截止时间、取消和重启恢复；互动地图与 PDF 后置，不将本轮等同完整 P0 验收。
