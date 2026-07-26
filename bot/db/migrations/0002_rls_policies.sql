-- 0002_rls_policies.sql
-- Enables Row Level Security on every Bot-owned table. The Bot itself
-- always connects with the Supabase service-role key (which bypasses
-- RLS by design), so these policies exist purely as defense-in-depth
-- against any other credential (e.g. anon key) ever being used against
-- these tables. See: database/03-rls-policies.md, docs/07-security.md

alter table bot_users enable row level security;
alter table audit_logs enable row level security;
alter table monitoring_logs enable row level security;
alter table incidents enable row level security;
alter table reports enable row level security;
alter table bot_config enable row level security;
alter table monitoring_heartbeat enable row level security;

-- No policies are created for the anon/authenticated roles on any of
-- these tables — by default, with RLS enabled and zero policies, ALL
-- access via non-service-role credentials is denied. This is
-- intentional: these tables are exclusively the Bot's own operational
-- data and are never meant to be queried by Quiz Space's end-user-facing
-- Supabase client.
