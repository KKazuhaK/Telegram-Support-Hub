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
| **R1** | **多层角色 + 商务代理 + 商户实体** | ✅ | — | XL | slice 1（auth）：JWT 加 `actor_kind / actor_id`，新增 `/api/auth/business-login` + `/auth/merchant-login`，CurrentUser 扩展 actor_kind；slice 2（scope）：Account/AccountGroup/Customer/Campaign 加 `merchant_id` 列，`tenant_scope.apply_merchant_scope` 服务统一过滤，accounts/customers list 走 tenant scope。admin 仍跨租户。完成于 2026-05-15。 |
| **R2** | 端口资源 / 配额 | ✅ | R1 | M | `port_quota` 服务：`recompute_merchant_ports`（按 active 数同步 ports_used）+ `check_quota_for_activation`（quota / 过期校验，0 = 不限）；accounts/batch 激活前按 merchant 分组校验，超额返回 409 中文提示。`ports_total=0` 视为不限避免锁老数据。完成于 2026-05-15（已配合 R14 的定时重置）。 |
| **R3** | 商务代理 CRUD UI | ✅ | R1 | M | 列表 + 表单（admin 视图）；登录页加 3 路 actor 选择，登录后 auth store 持久化 `actorKind / actorId`，Layout 菜单按 actor 切换显示。完成于 2026-05-15。 |
| **R4** | 商家账号 CRUD UI | ✅ | R1 + R2 | M | 列表 + 新增/编辑 + 批量权限 + `ports_used / ports_total` 列；business_agent 登录后能看到"商家账号"菜单（admin 仍可见），merchant 自己看不到（避免循环）。完成于 2026-05-15。 |
| **R5** | 任务管理三件套字段全量化 | ✅ | — | L | 数据层 + 4 个 execute slice：8 个 Telethon RPC（delete_friend / leave_other_devices / modify_nickname / signature / username / avatar / leave_group / detect_mutual / **appeal_mutual** / **modify_password**）。完成于 2026-05-15。 |
| **R6** | 消息模板变量系统 | ✅ | — | M | 15+ 变量渲染 + 富文本 entity（UTF-16 offset 准确）+ 预览 API + 模板页双栏帮助。完成于 2026-05-15。 |
| **R7** | 任务日志页 | ✅ | — | M | audit_logs 加 `action_prefix` 过滤；前端 任务日志（基于 message-details）+ 导入导出 两页 + 日志记录 子菜单 3 项。客户端 CSV 导出。完成于 2026-05-15。 |
| **R8** | 任务统计图表 | ✅ | — | M | 后端 `/api/statistics/{timeseries,message-details}`；前端 ECharts 柱+折线图 + 5 项汇总徽章 + 时段缩略 + 状态/任务/账号/日期筛选；维度对比保留。完成于 2026-05-15。剩 R16 导出报表。 |
| **R9** | 账号管理高级筛选抽屉 | ✅ | — | M | Account 加 nickname/country/remark/avatar_status 列；list 加 7 个新 filter；batch 端点加 proxy_id/clear_proxy/move_to_group_id；前端高级筛选抽屉 + 更多 dropdown（转移分组/分配代理/解绑代理/跳转修改资料/跳转批量操作）。完成于 2026-05-15。 |
| **R10** | 客服中心扩展 | ✅ | — | M | per-agent 今日接待/读取/发送/读取率/回复率（基于 agent → group → account 反查 message_records）+ KPI 汇总条 + 批量删除（拒绝删自己）+ 客户端 CSV 导出。完成于 2026-05-15。 |
| **R11** | 文件管理重构 | ✅ | — | S-M | 文本/图片/语音 3 个类型 tab + 分组面板 + 上传/下载/预览/试听；token 可走 query 让 `<img>` `<audio>` 直接渲染。账号/代理/号码 tab 已有独立模块（账号管理/代理 IP 管理/号码数据）。完成于 2026-05-15。 |
| **R12** | i18n（中/英）+ 主题（亮/暗） | ✅ | — | M-L | vue-i18n 接入 + zh-CN/en-US 双 locale + Element Plus locale 切换 + Pinia theme store + CSS variables 暗色覆盖 + topbar 语言/主题切换按钮 + localStorage 持久化。Layout 菜单全量 i18n。完成于 2026-05-15。 |
| **R13** | 多 Tab 横向滚动 + Telegram Logo + 加载动画 | ✅ | — | S | Layout 顶部 tabs 横向滚动 + 左右翻页按钮（隐藏 scrollbar 视觉对齐 PRD）+ ChatDotRound 蓝色品牌图标。完成于 2026-05-15。 |
| **R14** | 多端口资源化重置策略 | ✅ | — | S | `reset_merchant_ports` Celery 任务 + Beat 每小时第 5 分钟触发 + 首次运行初始化 reset_at（避免立刻清零）+ cycle ≤ 0 跳过。完成于 2026-05-15。 |
| **R15** | 商户客服权限批量修改 | ✅ | — | S | `POST /api/merchants/batch-permissions` 接 `(agent×group)` 矩阵 upsert + 字段白名单（173 测试）。完成于 2026-05-15。 |
| **R16** | 任务统计导出报表 | ✅ | — | S | `GET /api/statistics/timeseries.csv` 流式 CSV 导出（174 测试）。完成于 2026-05-15。 |

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
| ~~前端 chunk 体积 1MB+~~ | ✅ 2026-05-15 拆分：vendor 209k / element-plus 931k / echarts 541k / index 20k；Element Plus 与 ECharts 各自独立 chunk 让浏览器跨发布缓存 | done |
| ~~Alembic 没有真实增量迁移~~ | ✅ 2026-05-15 引入：`alembic.ini` + `backend/migrations/`（env.py 从 settings 读 URL，baseline revision 覆盖 20 张表）；容器 entrypoint 改 `python -m backend.migrate_then_serve`，自动 `upgrade head`（老库走 `stamp head` 避免重建表）；`AUTO_MIGRATE_COLUMNS` 保留为兜底；docs/alembic.md 工作流文档 | done |
| ~~WebSocket 没有自动重连~~ | ✅ 2026-05-15 Replies.vue 加指数回退（1/2/4/8/16/30s）+ 卸载时取消重连定时器 | done |
| ~~Celery `broker_connection_retry` 弃用警告~~ | ✅ 2026-05-15 设 `broker_connection_retry_on_startup = True` | done |
| ~~测试用 SQLite，生产是 MariaDB~~ | ✅ 2026-05-15 CI 加 `test-mariadb` job 起 mariadb:11.4 service container；`tests/support.py` 看 `TEST_DB_BACKEND` 切换；本地仍默认 SQLite | done |
| `Customer` 模型实际是"号码 leads" | PRD 中 customer = 商户。后续要么 rename，要么在新 merchants 落地后把现 Customer 改名为 Lead | 等真正撞到命名冲突时再 rename，避免改名连带审计/历史断链 |

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
- **2026-05-15** — R11 文件管理重构：Material 支持上传/下载，前端 3 个类型 tab + 图片预览 + 语音试听；FlexibleUserDep 支持 `?token=...` 让 img/audio 标签直接渲染（153 测试）。
- **2026-05-15** — R5.execute slice 1：execute_operation worker + 5 个 Telethon RPC（delete_friend / leave_other_devices / modify_nickname / signature / username）；campaign.start 钩入任务派发（158 测试）。
- **2026-05-15** — R9 账号高级筛选 + 批量动作扩展：4 个新字段 + 7 个新 list filter + batch endpoint 支持代理 / 分组转移（162 测试）。
- **2026-05-15** — R5.execute slice 2：modify_avatar Telethon RPC + 前端图片分组+图片选择器（接通 R11）（164 测试）。
- **2026-05-15** — R10 客服中心扩展：per-agent 今日 KPI（按 group→account 反查）+ 批量删除 + 客户端 CSV 导出（168 测试）。
- **2026-05-15** — R15 商户客服权限批量修改：`POST /api/merchants/batch-permissions`（agent × group 矩阵 upsert，权限字段白名单）（173 测试）。
- **2026-05-15** — R16 任务统计 CSV 导出：`GET /api/statistics/timeseries.csv` 流式输出（174 测试）。
- **2026-05-15** — R5.execute slice 3：leave_group / detect_mutual Telethon RPC + 测试覆盖（174 测试）。
- **2026-05-15** — R12 i18n + 主题：vue-i18n（zh-CN/en-US）+ Pinia theme store + CSS variables 暗色覆盖 + topbar 切换按钮；R13 视觉抛光：Layout tabs 横向滚动 + 翻页按钮 + Telegram 风格品牌图标。
- **2026-05-15** — R14 端口资源重置：`reset_merchant_ports` Celery beat 任务（每小时第 5 分钟）+ 4 项 TDD 覆盖（首跑初始化 / 周期到达清零 / 周期未到跳过 / 0 周期忽略）（178 测试）。
- **2026-05-15** — R1 slice 1：多 actor 登录与 JWT 形态。新增 business-login / merchant-login 路由 + JWT 加 `actor_kind / actor_id`，CurrentUser dispatch 三种 actor（184 测试）。
- **2026-05-15** — R1 slice 2：tenant scope 服务 + Account/AccountGroup/Customer/Campaign 增 `merchant_id` 列；accounts/customers list 走 `apply_merchant_scope`（merchant 仅见自己 / business_agent 见旗下所有商户 / admin 不变）（188 测试）。
- **2026-05-15** — R2 端口配额：`port_quota` 服务（recompute + check）+ accounts/batch 激活前按商户分组校验，超额返回 409 中文提示；ports_total=0 视为无限避免锁老数据（196 测试）。
- **2026-05-15** — R5.execute slice 4：appeal_mutual（AddContactRequest + add_phone_privacy_exception）+ modify_password（client.edit_2fa SRP 包装）（198 测试）。
- **2026-05-15** — R3 / R4 前端 actor-aware：登录页加身份选择（客服 / 商务代理 / 商家），auth store 持久化 actorKind+actorId，Layout 菜单按 actor 隐藏不适用项，topbar 角色徽章按 actor 切换。
- **2026-05-15** — 技术债清理：vite manualChunks 拆 element-plus / echarts / vendor（首屏 index 由 1.1MB 降到 20kB）；Replies.vue WebSocket 指数回退重连；Celery `broker_connection_retry_on_startup=True` 消除弃用警告。
- **2026-05-15** — 安全审计修复（R1 跨租户漏洞）：（1）`/api/merchants` `/api/business-agents` 加 actor scope（merchant 仅见自己 / BA 仅见旗下）；（2）`/api/campaigns` `/api/account-groups` 列表接 `apply_merchant_scope`；（3）`tenant_scope.can_access_row` helper + customers PATCH/DELETE + 群发任务 start/pause/resume/cancel 全部走 ownership 检查，跨租户返回 404 不泄露存在性；（4）`port_quota.recompute_merchant_ports` 不再在共享 session 上 `commit`，改为 `flush` 由 caller 提交；`check_quota_for_activation` 用 `SELECT FOR UPDATE` 加锁避免 TOCTOU；naive datetime 归一为 UTC；（5）`execute_operation` 全失败分支正确写 `failed` 而非 `partially_failed`；（6）Replies.vue WebSocket `watch(auth.token)` 切换登录用户时 tear down + 重连，避免跨用户事件泄露。新增 9 个跨租户安全测试（207 测试）。
- **2026-05-15** — R1 多租户真正可用化：`tenant_scope.default_merchant_id(user)` + `can_write_tenant_data(user)` helpers；customers import / PATCH / DELETE 与 campaigns create 走新 helper，商户登录后创建的客户与任务自动盖戳 `merchant_id=actor_id`；`/api/customers/friends` 对租户 actor 通过 `Account.merchant_id` JOIN 过滤（Friend 自身无需加列）；4 个新写路径 TDD 测试（211 测试）。
- **2026-05-15** — 统计端点接 tenant scope：`stats._scoped_account_ids(user, db)` helper + `_scoped_count(model, pred, *where)`；`/api/statistics/{dashboard,accounts,account-groups,timeseries,timeseries.csv,message-details}` 全部按 actor 过滤，MessageRecord/Friend 通过 `Account.merchant_id` 子查询限制；admin 视图不变。Proxies 显式只给 support_agent（共享资源池语义）。6 个新 stats scope 测试（217 测试）。
- **2026-05-15** — 提前清理剩余技术债：（1）Template / MaterialGroup / PhoneGroup 全部加 `merchant_id` + 列表 scope + create 自动盖戳；Proxy 保留 admin 共享池；旧 `unique=True` 改为 per-merchant 应用层校验。（2）审计日志 actor_kind 列 + tenant view：商户/BA 只见自己写的 audit 行，admin 不变。（3）Telethon `_classify_telethon_error`：6 类稳定 error_code（flood_wait/auth_invalid/password_invalid/network/rpc_error/unknown）替代裸 `type(exc).__name__`，便于 worker 决策重试策略。（4）N+1 修复：`/statistics/{accounts,account-groups,support-agents}` 三处原本每个 row 做 3 次 count 查询的循环，改为单批 GROUP BY 聚合到字典再 lookup —— 100 个账号从 300 query 降到 3 query。新增 11 个测试（228 测试）。
- **2026-05-15** — Alembic 引入：`alembic.ini` + `backend/migrations/env.py`（从 settings 读 URL）+ baseline revision（覆盖 20 张表 / 28 处 `merchant_id` FK / 全部索引）；4 个 docker-compose 文件的 API service `command:` 改 `python -m backend.migrate_then_serve`，自动判断 alembic_version 存在与否做 `upgrade head` 或 `stamp head`，老库无缝接管；`AUTO_MIGRATE_COLUMNS` 保留为兜底；`docs/alembic.md` 工作流文档；228 测试不变。
- **2026-05-15** — MariaDB CI matrix：`tests/support.py` 看 `TEST_DB_BACKEND` 选 backend（默认 SQLite，本地行为不变）；GitHub Actions 加 `test-mariadb` job 起 `mariadb:11.4` service container 跑同一套 228 测试，捕获 SQLite vs MariaDB 的 dialect 差异（JSON / SELECT FOR UPDATE / 大小写）；docker build job 依赖两个 test job 都过。
