# PostgreSQL 验证 Profile 初始化说明

SQLite 是默认本地开发 Profile，不需要本目录中的 Migration 或数据库服务。本目录仅服务于 Docker / 接近部署的 PostgreSQL 验证 Profile，验证多进程 Worker、行级并发与数据库角色隔离。

MVP 使用一个 PostgreSQL 实例和三个逻辑 Schema：`agent_ops`、`patient_ops`、`clinic_core`。

执行顺序：

1. 使用 Migration Role 执行 `001_create_schemas.sql`；
2. 由部署环境创建 `agent_app`、`patient_ops_app`、`clinic_core_app`，密码只从 Secret Store 或本地环境变量注入；
3. 使用 Migration Role 执行 `002_grants.sql`；
4. 分别使用三个运行角色执行各自 Schema 的 Migration；
5. 使用权限测试确认运行角色不能读取其他 Schema。

不要把数据库密码写入 SQL、仓库、日志或 `.env.example`。本地 Docker Compose 的密码也必须是开发占位值，并且不能复用于生产环境。
