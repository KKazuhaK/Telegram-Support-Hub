# 数据库迁移 (Alembic)

从 2026-05-15 起，所有 schema 变更走 Alembic。本文档描述工作流和升级方式。

## 文件布局

```
alembic.ini                          # 配置；URL 从 backend.app.core.config 读
backend/migrations/
├── env.py                           # 连接 + Base.metadata 注入
├── script.py.mako                   # 新 revision 模板
└── versions/
    └── 2026_05_15_1830-09fde8b7adc6_baseline.py
                                     # 起点：当前 20 张表的完整 schema
```

## 部署时怎么跑

**容器化部署（推荐）**：API 容器的 `CMD` 已改成 `python -m backend.migrate_then_serve`。
启动顺序自动：

1. 检查 `alembic_version` 表是否存在
2. 不存在 + 老库（有 `accounts` 表）→ `alembic stamp head`（标记当前为 baseline，不重建表）
3. 不存在 + 空库 → `alembic upgrade head`（建全部表）
4. 存在 → `alembic upgrade head`（应用新 revision）

Celery worker / beat / listen-worker 容器不跑迁移（不需要也不应该；只有 API 跑一次）。

**手动跑**（本地 / 排查）：

```bash
# 升级到最新
alembic upgrade head

# 看当前版本
alembic current

# 看 pending revisions
alembic history --verbose

# 离线模式：把 SQL 打出来给 DBA 审核而不执行
alembic upgrade head --sql

# 一次性指定 URL（不读 .env）
alembic -x url=mysql+pymysql://root:pw@host:3306/tg_support_hub upgrade head
```

## 改 schema 的流程

1. 改 `backend/app/models/*.py`（加列、改类型、加约束、加表…）
2. **本地**生成 revision：
   ```bash
   alembic -x url=sqlite:///./.alembic_tmp.db revision --autogenerate -m "add_foo_to_bar"
   ```
   （`.alembic_tmp.db` 是临时 SQLite，避免污染开发库；用本地 MariaDB 也行）
3. **手动 review** 生成的 `versions/<timestamp>-<rev>_add_foo_to_bar.py`：
   - autogenerate 会漏的：数据迁移、JSON 默认值、`server_default` 表达式、复杂索引
   - 改类型时确认 `downgrade()` 真的能回滚
4. 本地跑一次 `alembic upgrade head` 看是否报错
5. 提交 revision 文件 + model 变更进同一个 commit
6. 部署：API 容器重启时自动跑 `upgrade head`

## 与 `AUTO_MIGRATE_COLUMNS` 的关系

`backend/app/core/schema_sync.py` 仍然存在并默认开启（`AUTO_MIGRATE_COLUMNS=true`）。
它现在是**双保险**：

- 主路径：Alembic 处理 schema
- 兜底：如果某个 revision 漏了一列，启动时的 `ensure_columns_present`
  会偷偷加上，避免线上 500

要完全停用兜底，设 `AUTO_MIGRATE_COLUMNS=false`。**强烈建议**只有在你对
Alembic 工作流完全信任后才关，否则一次漏 revision 就要紧急运维。

## 已知边界

- **不处理**：列重命名（Alembic 默认会 drop+add，丢数据）。需要手动写
  `op.alter_column(..., new_column_name=...)` 或用 batch_alter_table。
- **不处理**：MariaDB 与 SQLite 的 dialect 差异（JSON 列、`SELECT FOR UPDATE`）。
  生产用 MariaDB 时生成 revision 也应该指向 MariaDB，否则可能漏 dialect 特定 SQL。
- **不可逆**：删列、删表的 `downgrade()` 只 drop，不会恢复数据。回滚前手动备份。
