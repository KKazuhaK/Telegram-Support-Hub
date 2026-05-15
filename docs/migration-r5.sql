-- One-shot schema upgrade for installs that started on the very first
-- AUTO_CREATE_TABLES=true deploy and then pulled the R1/R5/R6 images.
-- AUTO_CREATE_TABLES only creates *new* tables, never adds columns to
-- existing ones, so any column added after the initial bootstrap is
-- missing in the live DB and triggers "Unknown column" 500s.
--
-- Uses ADD COLUMN IF NOT EXISTS (MariaDB 10.0+) so re-running this
-- script is safe.
--
-- Run via phpMyAdmin or:
--   docker exec -i tg-support-hub-mariadb-1 mariadb -uroot -p"$MYSQL_ROOT_PASSWORD" tg-panel < migration-r5.sql
-- (or replace the container/db name to match your install).

-- ---- proxy_endpoints.group_id (data-management commit) ----
ALTER TABLE proxy_endpoints
  ADD COLUMN IF NOT EXISTS group_id INT NULL;
-- ADD INDEX has no IF NOT EXISTS; wrap in a stored proc-ish guard:
-- safe to ignore "Duplicate key name" if the index already exists.
ALTER TABLE proxy_endpoints
  ADD INDEX ix_proxy_endpoints_group_id (group_id);

-- ---- campaigns: task_kind / operation_target / extra_params (R5) ----
ALTER TABLE campaigns
  ADD COLUMN IF NOT EXISTS task_kind VARCHAR(32) NOT NULL DEFAULT 'broadcast';
ALTER TABLE campaigns
  ADD COLUMN IF NOT EXISTS operation_target VARCHAR(40) NOT NULL DEFAULT 'customer_broadcast';
ALTER TABLE campaigns
  ADD COLUMN IF NOT EXISTS extra_params JSON NULL;
ALTER TABLE campaigns
  ADD INDEX ix_campaigns_task_kind (task_kind);

-- ---- message_records: entities (R6) ----
ALTER TABLE message_records
  ADD COLUMN IF NOT EXISTS entities JSON NULL;

-- After applying, restart backend-api so the connection pool drops
-- cached metadata:
--   docker compose -f docker-compose.prod.host-network.yml restart backend-api
