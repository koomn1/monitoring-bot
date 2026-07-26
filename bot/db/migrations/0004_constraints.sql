-- 0004_constraints.sql
-- Additive data-integrity constraints. Deliberately does NOT add a
-- foreign key from audit_logs.user_id -> bot_users.telegram_user_id:
-- a user's first-ever command can be anything (not just /start), and
-- only /start currently upserts bot_users (see modules/01-authentication-module.md),
-- so an FK there would reject legitimate audit rows for env-only admins
-- who never sent /start. Revisit if authenticate() is called on every
-- command instead of just /start.

-- Constrain monitoring status to the values every monitor module
-- actually produces (see modules/03 through modules/07).
alter table monitoring_logs
    add constraint monitoring_logs_status_check
    check (status in ('up', 'down', 'degraded', 'unknown'));

alter table monitoring_logs
    add constraint monitoring_logs_service_check
    check (service in ('website', 'api', 'database', 'storage', 'realtime'));

-- Constrain report_type to the categories defined in
-- modules/16-reports-module.md §7.
alter table reports
    add constraint reports_type_check
    check (report_type in (
        'daily', 'weekly', 'monthly', 'performance', 'database',
        'infrastructure', 'deployment', 'analytics', 'security'
    ));

-- Constrain bot_users.role to the only values bot/core/permissions.py
-- ever assigns (see permissions.py's _DB_GRANTABLE_ROLES + the
-- audit-only "OWNER"/"UNAUTHORIZED" values written by
-- modules/auth/service.py).
alter table bot_users
    add constraint bot_users_role_check
    check (role in ('OWNER', 'ADMIN', 'VIEWER', 'UNAUTHORIZED'));

-- incidents.service should match the same set monitoring_logs uses.
alter table incidents
    add constraint incidents_service_check
    check (service in ('website', 'api', 'database', 'storage', 'realtime'));

-- A resolved incident must resolve after it opened — catches any
-- future bug in incidents_repo.py that could otherwise write bad data.
alter table incidents
    add constraint incidents_resolved_after_opened_check
    check (resolved_at is null or resolved_at >= opened_at);

-- Index used by permissions.py's DB-backed role lookup (get_bot_user is
-- called on every single command now — see bot/core/permissions.py) —
-- telegram_user_id is already the primary key so this is implicit, but
-- documented here for clarity since it's now a hot path, not just an
-- audit-trail table.
-- (No additional index needed: primary key lookups are already O(1).)
