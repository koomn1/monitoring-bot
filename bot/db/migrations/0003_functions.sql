-- 0003_functions.sql
-- Database functions supporting the Bot's reporting/cleanup needs.
-- See: database/04-database-functions.md

-- Returns aggregate uptime percentage for a service over N days,
-- used by future performance reports (see modules/16-reports-module.md §7).
create or replace function get_uptime_percentage(p_service text, p_days integer)
returns numeric
language sql
stable
as $$
    select
        round(
            100.0 * count(*) filter (where status = 'up') / nullif(count(*), 0),
            2
        )
    from monitoring_logs
    where service = p_service
      and checked_at >= now() - (p_days || ' days')::interval;
$$;

-- Deletes audit/monitoring log rows older than the given retention
-- window. Invoked by the (planned) automatic cleanup job — see
-- modules/20-automation.md §12.
create or replace function cleanup_old_logs(p_retention_days integer default 90)
returns void
language plpgsql
as $$
begin
    delete from audit_logs where created_at < now() - (p_retention_days || ' days')::interval;
    delete from monitoring_logs where checked_at < now() - (p_retention_days || ' days')::interval;
end;
$$;
