-- 0001_init.sql
-- Initial schema for the Quiz Space DevOps Bot's own operational data.
-- Run against the Supabase project referenced by SUPABASE_URL.
-- See: database/01-database-schema.md, database/02-tables.md

-- Bot administrators audit registry (role source of truth is env vars;
-- this table is audit/visibility only — see docs/03-system-architecture.md §8)
create table if not exists bot_users (
    telegram_user_id bigint primary key,
    username text,
    role text not null default 'UNAUTHORIZED',
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

-- Every command execution, successful or not
create table if not exists audit_logs (
    id uuid primary key default gen_random_uuid(),
    user_id bigint not null,
    command text not null,
    args jsonb not null default '[]'::jsonb,
    duration_ms integer,
    error text,
    created_at timestamptz not null default now()
);
create index if not exists idx_audit_logs_created_at on audit_logs (created_at desc);
create index if not exists idx_audit_logs_command on audit_logs (command);

-- Every monitoring check result (website, api, database, storage, realtime, ...)
create table if not exists monitoring_logs (
    id uuid primary key default gen_random_uuid(),
    service text not null,
    status text not null,
    latency_ms integer,
    metadata jsonb not null default '{}'::jsonb,
    checked_at timestamptz not null default now()
);
create index if not exists idx_monitoring_logs_service_checked_at
    on monitoring_logs (service, checked_at desc);

-- Open/resolved incident lifecycle per monitored service
create table if not exists incidents (
    id uuid primary key default gen_random_uuid(),
    service text not null,
    details text,
    opened_at timestamptz not null default now(),
    resolved_at timestamptz
);
create index if not exists idx_incidents_open
    on incidents (service) where resolved_at is null;

-- Generated reports (daily/weekly/monthly/etc.)
create table if not exists reports (
    id uuid primary key default gen_random_uuid(),
    report_type text not null,
    content text not null,
    metadata jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now()
);
create index if not exists idx_reports_type_generated_at
    on reports (report_type, generated_at desc);

-- Runtime-editable key/value settings (see docs/05-configuration.md)
create table if not exists bot_config (
    key text primary key,
    value jsonb not null,
    updated_at timestamptz not null default now()
);

-- Minimal table used purely as a cheap connectivity probe by the
-- Database Monitor (see modules/05-database-monitor.md §7)
create table if not exists monitoring_heartbeat (
    id serial primary key,
    pinged_at timestamptz not null default now()
);
insert into monitoring_heartbeat (id) values (1) on conflict (id) do nothing;
