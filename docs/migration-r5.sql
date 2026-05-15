-- One-shot schema upgrade for installs that started on the very first
-- AUTO_CREATE_TABLES=true deploy and then pulled the R1/R5/R6 images.
-- AUTO_CREATE_TABLES only creates *new* tables, never adds columns to
-- existing ones, so any column added after the initial bootstrap is
-- missing in the live DB and triggers "Unknown column" 500s.
--
-- Run this once via phpMyAdmin or:
--   docker exec -i tg-support-hub-mariadb-1 mariadb -uroot -p"$MYSQL_ROOT_PASSWORD" tg-panel < migration-r5.sql
-- (or replace the container/db name to match your install).

-- ---- proxy_endpoints.group_id (R5 data-management) ----
ALTER TABLE proxy_endpoints
  ADD COLUMN group_id INT NULL;
ALTER TABLE proxy_endpoints
  ADD INDEX ix_proxy_endpoints_group_id (group_id);

-- ---- campaigns: task_kind / operation_target / extra_params (R5) ----
ALTER TABLE campaigns
  ADD COLUMN task_kind VARCHAR(32) NOT NULL DEFAULT 'broadcast';
ALTER TABLE campaigns
  ADD COLUMN operation_target VARCHAR(40) NOT NULL DEFAULT 'customer_broadcast';
ALTER TABLE campaigns
  ADD COLUMN extra_params JSON NULL;
ALTER TABLE campaigns
  ADD INDEX ix_campaigns_task_kind (task_kind);

-- ---- message_records: entities (R6) ----
ALTER TABLE message_records
  ADD COLUMN entities JSON NULL;

-- After applying, restart backend-api so SQLAlchemy reflects the new
-- columns:
--   docker compose -f docker-compose.prod.host-network.yml restart backend-api
