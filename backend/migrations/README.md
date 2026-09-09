# MySQL 迁移

目标为 MySQL 8.4 / InnoDB / utf8mb4；初始迁移使用 MySQL 8.0.16+ 支持的类型与 CHECK 约束。使用当前机器的 MySQL 8.0 只能进行兼容性验证，不代表已完成 8.4 验收。

在 `backend/` 中使用已安装项目依赖的虚拟环境执行：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head --sql  # 只生成 SQL，不连接或修改数据库
.\.venv\Scripts\python.exe -m alembic upgrade head        # 使用 .env 的 DATABASE_URL 执行迁移
.\.venv\Scripts\python.exe -m alembic current             # 查询当前版本
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "describe change"
```

离线 SQL 生成只使用 MySQL 方言，不要求配置 `DATABASE_URL`。在线命令需要有效的本地连接配置；初始迁移版本为 `0001_initial`。

开发者必须审查自动生成的迁移。已应用的版本保持不变，结构变更新增迁移；不要用 `create_all()` 代替应用迁移。数据库创建脚本在 `../scripts/bootstrap-mysql.sql`；账号创建和权限授权由本机管理员完成。

初始版本包含 `trips`、`planning_tasks`、`agent_runs` 和 `trip_versions`，不含 P1 提案。UUID 保存为 36 字符字符串；时间戳由应用生成 UTC 时间后存入无时区 DATETIME，API 层负责还原时区标记。金额采用 DECIMAL(10,2)，快照使用 JSON；JSON 内部变更需重新赋值才能由 ORM 检测。

版本通过 `(trip_id, version)` 复合主键定位。CHECK 约束要求父版本为正且较旧；仓储写入层还需验证该父版本已存在且属于同一行程，初始版本的父版本为空。为保留行程删除的直接级联行为，父版本不建立自引用外键。`trips.current_version` 使用复合外键保证指向本行程的现存快照；建表后单独添加此约束以消除建表循环。生成结果时，先插入快照并 flush，再更新当前版本与任务终态，在同一事务提交。删除行程时，先将 `current_version` 置空并 flush，再删除行程；快照、任务及 Agent 记录随外键级联删除。禁止禁用外键检查绕过这些顺序。

2026-09-09 已在本机 MySQL 8.0.42 的专用 `smart_travel` 库应用由 Alembic 生成的初始 SQL，版本为 `0001_initial`。项目虚拟环境（Python 3.12.14）安装完成后，使用 asyncmy 0.2.14 执行 `alembic current` 确认 `0001_initial (head)`，`alembic upgrade head` 成功结束且无新增迁移；实际启动 FastAPI 后，数据库就绪接口返回 HTTP 200 / `ready`。

真实集成测试通过 PyMySQL 覆盖中文/emoji、JSON、金额、CHECK、外键与清空当前版本后的级联删除；测试事务全部回滚，四张业务表保持为空。尚未通过 asyncmy 在空库重放初始迁移或验证降级迁移。离线 SQL 输出、真实数据库验证和应用异步连接验证应分别记录。
