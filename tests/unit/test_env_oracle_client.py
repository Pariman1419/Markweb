import pytest


def test_env_preserves_backslashes_and_existing_values(tmp_path, monkeypatch):
    from mark_engine.adapters.env import load_env

    path = tmp_path / '.env'
    path.write_text('NAS_ROOT=\\\\server\\share\nX=a@b=c\n', encoding='utf-8')
    monkeypatch.setenv('X', 'existing')
    values = load_env(path)
    assert values['NAS_ROOT'] == r'\\server\share'
    assert values['X'] == 'a@b=c'
    import os
    assert os.environ['X'] == 'existing'


def test_select_guards_writes_and_returns_uppercase_columns():
    from mark_engine.adapters.oracle_client import select

    class Cursor:
        description = [('mark_id',), ('mark_data',)]
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params): pass
        def fetchall(self): return [(1, '^')]
    class Connection:
        def cursor(self): return Cursor()
    with pytest.raises(PermissionError):
        select(Connection(), 'DELETE FROM x')
    assert select(Connection(), 'SELECT mark_id, mark_data FROM x') == [{'MARK_ID': 1, 'MARK_DATA': '^'}]
