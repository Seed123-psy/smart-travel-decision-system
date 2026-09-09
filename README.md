# 智能旅行决策系统

基于 Vue 3、TypeScript、Vite、FastAPI、HelloAgents 和 MySQL 的本地旅行规划项目。已接入 DeepSeek 与高德支撑的多 Agent 行程生成、真实任务进度及本机历史；互动地图和 PDF 将按 [开发基线](development-baseline.md) 后续接入。执行流程与接口见 [规划说明](docs/planning.md)。

## 当前功能

- 前端录入旅行需求，确认目的地游玩总预算的包含与排除范围。
- 后端校验日期、人数、金额、房间数和默认值，返回规范化结果。
- 区分 API 存活与数据库就绪，MySQL 未配置时明确返回 503。
- 四张 P0 表的 SQLAlchemy 模型与 Alembic 初始迁移；本机 smart_travel 已完成初始化，迁移版本为 0001_initial。
- 页面显示模型和地图服务的配置状态；真实连接通过显式命令检测，刷新页面不会消耗外部 API 配额。
- 确认后并行执行景点、住宿、天气角色，依赖景点结果查询营业详情，再由 Planner 生成每日行程。
- 展示各 Agent 的实际状态、工具摘要与耗时，检查真实地点、日期时段和步行衔接，保存结果及来源。
- 支持刷新恢复上次任务和本机历史查看；单任务 60 秒期限，忙时拒绝重复提交，重启后明确标记未完成任务。

“检查需求”保持无状态；单独确认并生成才会联网并保存到 MySQL。预算尚未精算，营业、天气或路线缺少证据时明确标为待确认；完整 P0 尚未验收。

## 工程目录

```text
frontend/
  src/api/                 HTTP 客户端与错误处理
  src/components/          公共组件
  src/views/               旅行需求、任务及结果页面
  src/composables/         任务恢复与轮询
  src/types/               TypeScript 接口类型
  src/assets/              样式
  tests/                   API 客户端回归测试
backend/
  app/api/                 FastAPI 路由
  app/core/                配置、连接池
  app/schemas/             请求响应与业务约束
  app/models/              四张 P0 表
  app/agents/              HelloAgents 专业角色与 Planner
  app/providers/           DeepSeek 连接、高德地点/步行/天气适配器
  app/services/            异步编排、规则校验与事务持久化
  migrations/              Alembic 迁移
  scripts/                 MySQL 初始化 SQL
  app/scripts/             外部服务配置与真实连接检测命令
  tests/                   接口与需求契约测试
tests/fixtures/            后续固定样例与来源
tests/e2e/                 后续完整流程测试
```

## 环境要求

- Node.js 22.16+ 和 npm；升级 Vite 时同步检查 Node 要求。
- Python 3.11–3.13，使用独立虚拟环境；本次后端检查使用 Python 3.12。
- MySQL 8.0.16+ 支持初始迁移的 CHECK/JSON；设计目标为 MySQL 8.4。本机 MySQL 8.0.42 的 127.0.0.1:3306 已完成 smart_travel 初始化及真实读写测试，无需为骨架立即升级。

所有服务绑定回环地址。Vite 负责前端开发与构建；后续模型、地图和天气调用仍需联网。

## 启动后端

从项目根目录打开 PowerShell：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`requirements-lock.txt` 固定本次 Windows / Python 3.12 环境中验证过的运行与开发依赖；`requirements.txt` 和 `requirements-dev.txt` 保留依赖范围，升级时重新生成锁文件并验证。项目虚拟环境已完成安装，无需重复创建；后续命令均使用其中的 Python。

`.env` 只在首次配置时复制，已有配置不要覆盖。`DATABASE_URL` 留空也能使用 API 和字段校验，模型密钥暂时可留空。打开 [接口文档](http://127.0.0.1:8000/docs) 或 [存活检查](http://127.0.0.1:8000/api/health)。

## 模型与高德服务配置

本机已将用户提供的两个 Key 保存在忽略提交的 `backend/.env`。模型使用 `LLM_BASE_URL=https://api.deepseek.com` 和 `LLM_MODEL=deepseek-v4-flash`；密钥字段为 `LLM_API_KEY`、`AMAP_WEB_SERVICE_KEY`。高德需申请 **Web 服务** Key。修改配置后重启后端，再刷新页面状态。

在 `backend/` 执行：

```powershell
# 只检查配置，不联网、不调用模型。
.\.venv\Scripts\python.exe -m app.scripts.check_providers
# 显式发起真实探测：模型一次请求，输出最多 32 tokens，关闭思考模式。
.\.venv\Scripts\python.exe -m app.scripts.check_providers --live --provider llm
# 查询杭州 POI、首两个不同点位的步行路线及当前天气预报。
.\.venv\Scripts\python.exe -m app.scripts.check_providers --live --provider amap
```

`--output ../tmp/provider-check.json` 可保存脱敏报告。真实探测使用供应商配额，无自动重试；未配置、失败或缺少验证数据时退出码为 2。`GET /api/providers/status` 和页面卡片只检查本地字段是否填写，显示“已配置”不等于验证连通，更不表示 Agent 已运行。CLI 报告的 `providers` 同样是配置快照，`checks` 才记录本次真实检测结果。

申请步骤和已验证协议见 [高德接入说明](docs/providers-amap.md) 与 [模型接入说明](docs/providers-llm.md)。POI 不证明景点开放或实时价格，天气仅适用于返回日期。

## 启动前端

从项目根目录另开一个 PowerShell：

```powershell
cd frontend
npm ci
npm run dev
```

打开 [本地页面](http://127.0.0.1:5173)。Vite 将 `/api` 代理到 `127.0.0.1:8000`。填写并检查需求后，确认联网及本地保存，再点击生成；页面显示真实协作进度和最终行程。只启动一个后端 worker。

前端依赖已安装到 `frontend/node_modules/`，并通过 `package-lock.json` 锁定版本、官方下载地址及校验值。后续使用 `npm ci` 重装；有意升级依赖时使用 `npm install`，同步提交 `package.json` 与锁文件并重新验证。`npm run build` 生成 `frontend/dist/`；`npm run preview` 在 `127.0.0.1:4173` 预览构建产物。

## 字体与界面样式

页面使用本地提供的 Noto Sans SC 可变字体子集，统一标题、表单和 Agent 面板的字形；输入框文字为 16px，辅助说明至少 12px。字重、间距和响应式规则集中在 `frontend/src/assets/main.css`。字体约 1.81 MiB，无需外部字体服务；来源、SIL OFL 许可与更新方法见 [字体说明](frontend/src/assets/fonts/README.md)，构建产物附带 `fonts/OFL.txt`。

## 初始化专用 MySQL 数据库

本机已经完成本节的建库及初始迁移，连接配置已保存到忽略的 `backend/.env`。项目虚拟环境中的 asyncmy 已通过真实连接、在线迁移命令和 FastAPI 数据库就绪检查。以下步骤供其他机器首次配置使用。

在 `backend/` 目录使用现有管理账号登录，将 `YOUR_MYSQL_ADMIN` 替换为实际用户名，密码交互输入：

```powershell
mysql --host=127.0.0.1 --user=YOUR_MYSQL_ADMIN --password
```

在 MySQL 终端执行：

```sql
SOURCE scripts/bootstrap-mysql.sql;
```

脚本仅创建 `smart_travel` 数据库，不创建账号。为专用本地账号配置该库权限，迁移权限与数据删除顺序见 [迁移说明](backend/migrations/README.md)。在 `backend/.env` 设置：

```dotenv
DATABASE_URL=mysql+asyncmy://YOUR_USER:URL_ENCODED_PASSWORD@127.0.0.1:3306/smart_travel?charset=utf8mb4
```

密码中的特殊字符需要 URL 编码。凭据只放本地 `.env`，不要发送到聊天或提交代码。退出 MySQL 终端后，在 `backend/` 执行迁移并重启后端：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

[数据库就绪检查](http://127.0.0.1:8000/api/health/ready) 在连接和迁移正确后返回 `ready`；未配置、连接失败或迁移不匹配时返回 503。`python -m alembic upgrade head --sql` 仅生成 SQL，不连接数据库。

## 验证命令

在 `backend/`：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m alembic upgrade head --sql
```

在 `frontend/`：

```powershell
npm run typecheck
npm test
npm run build
```

当前 API 客户端测试使用 Node 内置测试运行器；组件测试和完整流程接入时再引入 Vitest / Playwright。

真实 MySQL 集成测试默认跳过。需要验证已迁移的专用测试库时，在 `backend/` 显式设置测试连接（使用 PyMySQL 驱动）：

```powershell
$env:MYSQL_INTEGRATION_URL = 'mysql+pymysql://YOUR_USER:URL_ENCODED_PASSWORD@127.0.0.1:3306/smart_travel?charset=utf8mb4'
.\.venv\Scripts\python.exe -m pytest tests/test_mysql_integration.py tests/test_planning_store_mysql.py
Remove-Item Env:MYSQL_INTEGRATION_URL
```

这 7 项测试写入带独立 UUID 的合成记录，验证中文/emoji、JSON、金额、表间约束、规划事务和重启恢复，并在外层事务结束时回滚；不修改表结构。

## 本次验证结果与限制

- 后端依赖已安装到 `backend/.venv`（Python 3.12.14），`pip check` 通过；运行与开发依赖已固定在 `backend/requirements-lock.txt`。接入 HelloAgents、规划编排、规则校验和类型筛选后完整 241 项测试通过，包含 MySQL 集成测试；存在上游依赖弃用警告，无测试失败。供应商错误与 Agent 行为测试使用夹具，不消耗配额。
- 2026-09-09 在本机 MySQL 8.0.42 创建 `smart_travel`，应用初始迁移；本轮通过 asyncmy 0.2.14 执行 `alembic current`，确认 `0001_initial (head)`，并成功执行 `alembic upgrade head`（无新增迁移）。四张业务表及 `alembic_version` 均已建立，中文、emoji、JSON、DECIMAL、CHECK、外键和级联删除验证通过，初始化测试写入已回滚；规划生成后业务表保存真实本机历史。
- 使用项目虚拟环境实际启动 Uvicorn，HTTP 存活检查、数据库就绪检查和需求校验均返回 200；后端直连与 Vite `/api` 代理的就绪响应均为 `ready`，迁移版本为 `0001_initial`。本轮后端和 Vite 保持运行，供本机浏览；结束开发时在各服务终端按 Ctrl+C 停止。
- 前端已使用 npm 正常安装并生成完整锁文件，最终 `npm ci` 重装通过；本次 npm 审计报告 0 项已知漏洞。锁文件包含 69 个包条目（含跨平台可选依赖），本机安装 45 个包，均使用官方 npm 下载地址和 SHA-512 校验值。
- 当前版本为 Vue 3.5.42、Vite 8.2.2、`@vitejs/plugin-vue` 6.0.8、TypeScript 5.9.3 和 `vue-tsc` 3.3.11；在 Node.js 22.16.0 / npm 10.9.2 下验证。最终依赖的类型检查、6 项客户端测试和生产构建全部通过，产物位于 `frontend/dist/`。
- 获准后已成功启动 Vite，并完成真实浏览器表单与后端代理联调：上海至杭州、2030-10-01 至 2030-10-03、3 人、总预算 6000.01 元，返回 2 间房及 `¥6,000.01`；修改预算会清空旧结果、取消确认并禁用提交；8 天行程显示业务错误与请求标识，改回 3 天并重新确认后可成功提交。
- 已将整体校验错误的字段标签改为“旅行需求”，经浏览器复验显示中文；修复后 `npm run build`（含类型检查）通过。默认桌面视口宽 1280 像素，页头、表单和结果卡片目视检查无横向溢出；浏览器控制台无错误或警告。
- 字体与排版升级后，检查了默认桌面、390px 和 320px 浏览器视口；页面无横向溢出，窄屏的偏好设置、错误提示和成功结果可正常显示，需求提交仍通过真实后端校验。
- 2026-09-09：DeepSeek `deepseek-v4-flash` 单次真实连接通过，约 888ms，9 个输入 token、2 个输出 token；高德返回 20 个 POI，样例步行路线 12,832 米/10,266 秒，以及 4 天预报。已修复真实步行响应 `info="ok"` 的大小写差异。报告位于忽略提交的 `tmp/deepseek-verification.json` 和 `tmp/amap-verification.json`，不含 Key；费用及剩余额度以供应商账单为准。
- 服务配置卡片的失败重试、刷新和两项“已配置”状态经浏览器验证，接入规划前前端 6 项测试及生产构建通过。真实移动设备、多浏览器兼容及 `npm run preview` 尚未验证；地图展示和 PDF 仍待接入，完整 P0 未验收。

## 多 Agent 规划验证

本轮真实规划已跑通：修正 POI 类别后，三亚 2026-09-17 至 09-19、2 人、目的地总预算 8000 元，约 8 秒生成六个景点及 1 间 / 2 晚的住宿建议。五个 Agent 均有真实 DeepSeek 调用记录，模型用量合计 3681 tokens；天气超出预报窗口、营业和价格未核实，因此结果为 `degraded`。来源和结果已存 MySQL，脱敏复验报告位于 `tmp/planning-live-category-verification.json`。此前杭州场景验证了真实路线冲突与可选住宿数据失败的降级；一次或少量生成不等同于 20 次 p95 性能验收。

前端 15 项测试通过，最终类型检查及生产构建通过；浏览器验证了需求确认、实际协作记录、每日切换、历史读取、服务重启后页面恢复，以及 390px / 320px 的无横向溢出。当前服务仍保持本地运行。来源展示有效期，历史为生成时快照，不会自动重新调用供应商。

## 下一步

来源链接已修复：高德接口标识不再直接打开，页面改为公开的地点、天气或路线服务说明；已有历史行程自动适用。相关回归包含链接映射、旧记录参数隔离和未知链接处理，前端共 18 项测试通过。

1. 接入每日行程与互动地图联动、PDF、自然语言需求解析及本机行程删除，补齐 P0 验收。
2. 扩大真实城市、日期、供应商失败及性能样本；预算精算、Critic 和编辑联动安排在 P1。
