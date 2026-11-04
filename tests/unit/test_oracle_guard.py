import pytest
from mark_engine.adapters.oracle_guard import READ_ONLY_TXN, assert_select_only


def test_guard_allows_select():
    assert_select_only("SELECT * FROM actldba.elr WHERE elr_no = 'ADI2601001'")
    assert_select_only("  select 1 from dual;  ")
    assert_select_only("-- leading comment\nSELECT col1, col2\nFROM table_name;")
    assert_select_only("/* block comment */ SELECT 1;")


def test_guard_allows_with():
    sql = """
    WITH elr_cte AS (
        SELECT elr_no, cust_bom_no FROM actldba.elr
    )
    SELECT * FROM elr_cte
    """
    assert_select_only(sql)
    assert_select_only("WITH q AS (SELECT 1 AS c FROM dual) SELECT c FROM q;")


def test_guard_allows_read_only_txn():
    assert_select_only(READ_ONLY_TXN)
    assert_select_only("SET TRANSACTION READ ONLY")
    assert_select_only("  SET TRANSACTION READ ONLY;  ")


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE actldba.elr SET x=1",
        "select 1; delete from t",
        "/*x*/ insert into t values(1)",
        "SELECT * FROM t FOR UPDATE",
        "begin null; end;",
        "MERGE INTO t USING s ON (t.id = s.id) WHEN MATCHED THEN UPDATE SET x=1",
        "DROP TABLE t",
        "ALTER TABLE t ADD col1 VARCHAR2(10)",
        "CREATE TABLE t (id NUMBER)",
        "GRANT SELECT ON t TO user2",
        "TRUNCATE TABLE t",
        "EXECUTE immediate 'drop table t'",
        "CALL my_proc()",
        "DECLARE x NUMBER; BEGIN x := 1; END;",
        "LOCK TABLE t IN EXCLUSIVE MODE",
        "COMMIT",
        "SELECT 1; SELECT 2;",
        "SELECT * FROM t; ;",
        "",
        "   ",
        "NOT A QUERY",
        "SELECT 1 FROM t FOR   UPDATE",
    ],
)
def test_guard_blocks_forbidden(sql: str):
    with pytest.raises(PermissionError):
        assert_select_only(sql)
