# Mark Airflow DAGs

## Discovery (2026-11-06)

- The scheduler and webserver run as active systemd services on the Airflow host.
- Key-only SSH as `itadmin` worked. Airflow version, DAG folder, scheduler timezone, and CLI access remain unverified; determine them before deployment. No other DAG or service was changed.
- The Airflow host could not reach the dev API: the host probe returned HTTP `000`. Per user: `.3` to `10.151.97.18` is blocked by the network, `.3` to `10.153.90.17` works, and port 8088 on `.17` is occupied by another application. The `.17` API port remains to be determined.
- Task 3 and Task 4 are deferred until deployment to `.17`, B3 Task 5 has a green build, and migration 0007 has been applied to the real DB. Task 4 additionally requires B3 Task 6 and explicit user actions.

## Configuration and deployment (future)

The three DAGs use the Airflow Connection `mark_api` for host, port, scheme and token. No endpoint address is embedded in the DAGs. Set the Connection to the actual Mark API endpoint on `.17` once its port is decided; the password holds the `scan:write` token. Do not print the token or pass it in shell history. The user creates the token as specified in the plan.

After prerequisites are verified, copy only `airflow/dags/mark/*.py` to the `mark/` subfolder of the existing DAGs directory and check imports for `mark_*`. Files are created paused; a user must authorize initial load and unpausing. Run no deployment on the shared Airflow server until then. Use only key-based SSH; do not use sudo or change other services or DAGs.

The DAGs use `schedule_interval` for compatibility with pre-2.4 Airflow. The installed version and support for `max_active_tasks`, timezone handling, and the import path still need validation on the actual scheduler before deployment. The server-side parse check has not been run.

## Operation and rollback

The scheduled DAGs do not backfill and use the API watermark. A 409 is skipped, 401/403 fails without retry, and other failures follow the task retry policy. The manual initial load has no retries.

After user authorization, rollback consists of pausing only the two Mark scheduled DAGs, removing only the Mark DAG files/subfolder, deleting only the `mark_api` Connection, and revoking its token. Never change other teams' DAGs, services, pools or variables.
