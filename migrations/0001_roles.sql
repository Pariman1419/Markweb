-- 0001_roles — separate roles for the Mark system (DRAFT, not applied)
-- Owner decision 2026-11-04: rotating the postgres password is not required now; this migration still stops
-- application code from using the superuser.

-- UP ---------------------------------------------------------------------------------------------------------
begin;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'mark_owner')       then create role mark_owner nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'mark_app')         then create role mark_app login; end if;
  if not exists (select 1 from pg_roles where rolname = 'mark_rules_admin') then create role mark_rules_admin login; end if;
  if not exists (select 1 from pg_roles where rolname = 'mark_readonly')    then create role mark_readonly login; end if;
end $$;

-- mark_logic stays as it is; only mark_owner may change it from now on
alter schema mark_logic owner to mark_owner;
do $$ declare t text; begin
  for t in select tablename from pg_tables where schemaname = 'mark_logic' loop
    execute format('alter table mark_logic.%I owner to mark_owner', t);
  end loop;
end $$;
grant usage on schema mark_logic to mark_app, mark_rules_admin, mark_readonly;
grant select on all tables in schema mark_logic to mark_app, mark_rules_admin, mark_readonly;
revoke insert, update, delete, truncate on all tables in schema mark_logic from public, mark_app, mark_rules_admin, mark_readonly;

commit;

-- DOWN -------------------------------------------------------------------------------------------------------
-- begin;
-- alter schema mark_logic owner to postgres;
-- do $$ declare t text; begin
--   for t in select tablename from pg_tables where schemaname = 'mark_logic' loop
--     execute format('alter table mark_logic.%I owner to postgres', t);
--   end loop;
-- end $$;
-- revoke all on all tables in schema mark_logic from mark_app, mark_rules_admin, mark_readonly;
-- revoke usage on schema mark_logic from mark_app, mark_rules_admin, mark_readonly;
-- drop role if exists mark_readonly; drop role if exists mark_rules_admin; drop role if exists mark_app; drop role if exists mark_owner;
-- commit;
