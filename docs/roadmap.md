# TG Support Hub 路线图

本文档跟踪项目相对于 [`tg-customer-service-plan.md`](tg-customer-service-plan.md)（内部策划）
和 [`prd.md`](prd.md)（参考线上系统的需求文档）的实现进度。每项标注**状态、依赖、预估**与
**完成判定**，以便长期跟进时不会丢线。

> **状态约定**
> - ✅ 完成（已上线 + 有测试覆盖）
> - 🚧 进行中（部分上线）
> - 🕒 未开始
> - 🧊 暂缓（依赖未就绪）

> **预估口径**：S = 半天内、M = 1-2 天、L = 3-5 天、XL = 1 周以上。
> 全部按"我对当前代码库的熟悉度 + TDD 节奏"估，没有买余量。

---

## 0. 当前快照（2026-05-15）

- **后端**：FastAPI 0.115，SQLAlchemy 2 + Alembic 骨架，Celery 5.4 worker × 3 + beat，Telethon adapter（接通真实发送 + 回复监听）；**85 个单元测试**全过。
- **前端**：Vue 3 + Vite + Element Plus + Pinia + 多页签 Layout。
- **数据库**：MariaDB 11.4 LTS；运行时也支持挂宿主机现成实例（aaPanel 方案验证过）。
- **部署**：Docker Compose 3 形态（自带 db / 宿主机 db / host 网络）；GHCR 双镜像 CI。
- **角色**：admin / supervisor / agent（**单层**，未做商务代理/商户的多层）。
- **审计**：登录、账号导入、代理绑定、群发任务、客户分配、文件操作、批量动作均落 audit_logs。

---

## 1. ✅ 已完成模块

| 模块 | 说明 | 测试 |
| --- | --- | --- |
| 鉴权 | bootstrap-admin、JWT、role、has-admin、me、密码 bcrypt | `test_auth_api.py` / `test_security.py` |
| TG 账号 | session ZIP 导入、状态/启用/分组筛选、批量上线下线归档删除 | `test_accounts_api.py` |
| 账号分组 | CRUD + 成员管理 | (覆盖在 accounts 测试) |
| 网络代理 | CRUD + TCP 检测 + 加密密码 + 分组 | `test_proxy_pool.py` |
| 代理池自动分配 | status / max_accounts / country 匹配 + 轮询 | `test_proxy_pool.py` |
| 客户管理 | 导入 + 去重 + 分配（含 import 同事务分配）+ CSV 导出 | `test_customers_api.py` / `test_assignment.py` / `test_export.py` |
| 好友 | 列表筛选、Telethon 同步任务派发 | `test_listen_worker.py` |
| 消息模板 | CRUD | (集成在 campaigns) |
| 群发任务 | 3 种 target_type（customer/friend/imported_target）+ 启停取消 + 调度（锁/额度/静默/重试/熔断） | `test_send_worker.py` / `test_imported_target.py` / `test_scheduling.py` |
| 回复监听 | 常驻 worker、回复落库 + Redis pub/sub | `test_listen_worker.py` / `test_reply_bus.py` |
| 客服中心 | 客服账号 CRUD + 账号分组权限矩阵 + 数据可见范围 | `test_permissions.py` |
| 审计日志 | 全链路 audit + 列表筛选 | (查询接口覆盖) |
| 统计 | dashboard + per-account / per-group / per-agent | UI 直接消费 |
| WebSocket | `/ws/replies` 实时推送 + 权限过滤 | (集成测试，需 Redis) |
| 文件管理 | 上传/列表/删除 + 路径穿越防护 + sanitize | `test_files_api.py` |
| 数据子模块 | 号码/文本/代理分组 + 双栏管理 UI | `test_data_management_api.py` |
| 前端框架 | 多页签、子菜单分组、状态栏、全屏、角色徽章 | — |

---

## 2. 🚧 PRD vs 当前实现的差距

PRD 描述的是一个**多租户商业系统**：总后台 → 商务代理 → 商户 → 客服。
我们当前是**单租户**：admin 直接看全量数据。差距汇总如下，按优先级排：

| 编号 | 模块 | 状态 | 依赖 | 预估 | 完成判定 |
| ---: | --- | --- | --- | --- | --- |
| **R1** | **多层角色 + 商务代理 + 商户实体** | 🕒 | — | XL | 4 类角色登录可用，merchants 表 + business_agents 表落库，所有 list API 加 tenant_id 过滤；admin 仍能跨租户查看 |
| **R2** | 端口资源 / 配额 | 🕒 | R1 | M | merchants 表带 `ports_total / ports_used / ports_expires_at / ports_reset_at`；账号上线时校验端口；过期自动锁号 |
| **R3** | 商务代理 CRUD UI | 🚧 | R1 | M | 列表 + 新增/编辑（名称、密码、昵称、平台、Logo、域名、备注、状态）；列表筛选 |
| **R4** | 商家账号 CRUD UI | 🚧 | R1 + R2 | M | 列表 + 新增/编辑 + 批量改客服权限；端口配额可视 |
| **R5** | 任务管理三件套字段全量化 | 🚧 | — | L | **数据层 ✅ 2026-05-15**：Campaign 加 task_kind/operation_target/extra_params；3 个独立任务簇 + 5 个批量操作 + 5 个修改资料类型可建可查；后端验证 + 3 个前端页 + 侧栏 3 项。**剩余 R5.execute**：批量操作 / 修改资料的真实执行 worker（需要 Telethon 调用 deleteFriend / leaveGroup / setProfile 等 RPC） |
| **R6** | 消息模板变量系统 | ✅ | — | M | 15+ 变量渲染 + 富文本 entity（UTF-16 offset 准确）+ 预览 API + 模板页双栏帮助。完成于 2026-05-15。 |
| **R7** | 任务日志页 | ✅ | — | M | audit_logs 加 `action_prefix` 过滤；前端 任务日志（基于 message-details）+ 导入导出 两页 + 日志记录 子菜单 3 项。客户端 CSV 导出。完成于 2026-05-15。 |
| **R8** | 任务统计图表 | ✅ | — | M | 后端 `/api/statistics/{timeseries,message-details}`；前端 ECharts 柱+折线图 + 5 项汇总徽章 + 时段缩略 + 状态/任务/账号/日期筛选；维度对比保留。完成于 2026-05-15。剩 R16 导出报表。 |
| **R9** | 账号管理高级筛选抽屉 | 🚧 | — | M | 头像状态/账号昵称/日期范围筛选；批量动作下拉项扩展到 10 个（修改资料、解绑客服、转移分组、转移账号、分配代理等） |
| **R10** | 客服中心扩展 | 🚧 | R1 / R3 | M | 今日接待/读取/发送/读取率/回复率实时指标；"打开客服页面"跳转 client 子域；批量新增、批量导出、批量删除 |
| **R11** | 文件管理重构 | 🚧 | — | S-M | 按类型 Tab（图片/语音/账号/代理/号码/文本）+ 左侧文件组面板；当前 `/api/files` 升级成带 file_group 的 |
| **R12** | i18n（中/英）+ 主题（亮/暗） | 🕒 | — | M-L | 全站文案抽取到 vue-i18n；切换语言/主题持久化到 localStorage；Element Plus locale + CSS variables |
| **R13** | 多 Tab 横向滚动 + Telegram Logo + 加载动画 | 🕒 | — | S | 视觉层细节，等内容稳定后做 |
| **R14** | 多端口资源化重置策略 | 🕒 | R2 | S | 后台定时任务按 `ports_reset_at` 重置 `ports_used` 计数 |
| **R15** | 商户客服权限批量修改 | 🕒 | R4 | S | `POST /api/merchants/batchUpdateClientPermission` |
| **R16** | 任务统计导出报表 | 🕒 | R8 | S | `POST /api/statistics/exportReport` |

总剩余预估：**约 30-50 个工作日**（按 TDD + 测试覆盖率口径）。

---

## 3. 推荐迭代顺序（按依赖与价值密度排）

```
Phase 1（先打地基）：R1 → R2
  原因：所有 merchant/agent/client 视角都依赖租户模型；不先做，
        R3/R4/R10/R15 都要返工。

Phase 2（解锁商业语义）：R3 → R4 → R15
  让"商务代理 + 商户"这条产品主线可演示。

Phase 3（任务核心）：R6 → R5
  R6（模板变量）先于 R5：变量是任务发出消息的最小单元，
  R5 的 UI 设计要建立在变量已有的基础上。

Phase 4（运营可见性）：R8 → R7 → R16
  统计先于日志；日志可作为统计的钻取入口。

Phase 5（操作面）：R9 → R11 → R10
  侧重提升日常运营效率。

Phase 6（产品化）：R12 → R13 → R14
  i18n / 主题 / 视觉抛光 / 配额自动化。
```

短期里程碑：

- **M1（本周）**：完成 R1 骨架 + R3 + R4 的 CRUD（不强制端口校验）→ 路线图 PRD 第 5-7 节可演示。
- **M2（下周）**：完成 R2 端口语义 + R6 模板变量 → 群发任务能用真实变量。
- **M3（第三周）**：完成 R5 任务管理三件套 + R8 统计报表 → 端到端业务闭环可上线给试用客户。

---

## 4. 跨模块技术债

| 项 | 说明 | 何时还 |
| --- | --- | --- |
| 前端 chunk 体积 1MB+ | `vite.config.js` 配 `build.rollupOptions.output.manualChunks` 把 Element Plus / ECharts 拆出 | R8 落地时一并做 |
| Alembic 没有真实增量迁移 | 第一版用 `Base.metadata.create_all`，新加字段后没有 `op.add_column` 脚本。已加 `AUTO_MIGRATE_COLUMNS` 启动时同步缺失列；仍不能处理改类型/删字段 | 等首次需要"非加列"的 schema 变更时引入完整 alembic |
| WebSocket 没有自动重连 | 前端 `Replies.vue` 简单实现，长连断了不重连 | R10 客服中心时一并加 exponential backoff |
| Celery `broker_connection_retry` 弃用警告 | 设 `broker_connection_retry_on_startup=True` | 顺手改，<5min |
| 测试用 SQLite，生产是 MariaDB | 二者 JSON 字段语义略有差异 | R1 改 schema 时加 MariaDB CI matrix |
| `Customer` 模型实际是"号码 leads" | PRD 中 customer = 商户。后续要么 rename，要么在新 merchants 落地后把现 Customer 改名为 Lead | R1 与 R4 之间 |

---

## 5. 不在范围内（明确不做）

- **多渠道接入**（WhatsApp、Line、邮件）：策划 4.2 节明确暂缓。
- **AI 自动回复**：策划 4.2 节明确暂缓。
- **复杂组织架构审批流**：策划 4.2 节明确暂缓。
- **2 个 PRD 中提到的"客户端 client 子域"**（独立客服聊天前端）：作为单独工程，路线图中只保留链接入口。
- **`group_member_notice` 任务类型**：PRD/策划都标了合规复杂度高，先留位。

---

## 6. 变更日志（人类可读）

- **2026-05-15** — 路线图建立。当前 85 个测试全过，已完成数据管理三子页 + 多页签 Layout + 文件管理。
- **2026-05-15** — R1 落地：BusinessAgent + Merchant 实体 + 端口字段 + 后台页面（92 测试）。
- **2026-05-15** — R6 落地：模板变量引擎（UTF-16 entity offset 准确） + 端到端接入 send_worker + 预览 UI（117 测试）。
- **2026-05-15** — R5 数据层落地：Campaign.task_kind/operation_target/extra_params + 3 个任务簇 + 严格枚举校验 + 前端 3 页 + 任务管理子菜单 3 项（122 测试）。R5.execute（实际执行）留下一个迭代。
- **2026-05-15** — Schema auto-migrate：启动时 `ensure_columns_present` 把模型新加列自动 ALTER TABLE ADD（129 测试）。
- **2026-05-15** — R8 任务统计图表：timeseries + message-details API + ECharts 柱+线双轴图 + 5 汇总徽章 + 维度对比（142 测试）。
- **2026-05-15** — R7 日志记录：audit_logs `action_prefix` 过滤 + 任务日志 / 导入导出 两页 + 日志记录子菜单 3 项（146 测试）。
