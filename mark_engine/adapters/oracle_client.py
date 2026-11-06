import os
from typing import Any, Mapping

from mark_engine.adapters.oracle_guard import READ_ONLY_TXN, assert_select_only

_initialized = False


def connect_actl():
    import oracledb
    global _initialized
    if not _initialized:
        client_dir = os.environ.get('ORACLE_CLIENT_DIR')
        if client_dir and not os.path.exists(client_dir) and os.path.exists('/opt/oracle/instantclient_21_13'):
            client_dir = '/opt/oracle/instantclient_21_13'
        if client_dir:
            oracledb.init_oracle_client(lib_dir=client_dir)
        else:
            oracledb.init_oracle_client()
        _initialized = True
    dsn = f"{os.environ['ACTL_HOST']}:{os.environ['ACTL_PORT']}/{os.environ['ACTL_SERVICE']}"
    conn = oracledb.connect(user=os.environ['ACTL_USER'], password=os.environ['ACTL_PASSWORD'], dsn=dsn)
    try:
        with conn.cursor() as cursor:
            cursor.execute(READ_ONLY_TXN)
    except Exception:
        conn.close()
        raise
    return conn


def select(conn, sql: str, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    assert_select_only(sql)
    with conn.cursor() as cursor:
        cursor.execute(sql, params or {})
        names = [column[0].upper() for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
