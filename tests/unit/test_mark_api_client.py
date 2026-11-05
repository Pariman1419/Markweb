from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import sys
import threading
from urllib.error import URLError
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'airflow' / 'dags' / 'mark'))
from mark_api_client import (MarkApiAuthError, MarkApiBusy, MarkApiError,
                             call_mark_api, summarize)


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.server.request_data = (self.path, self.headers.get('Authorization'),
                                        json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(self.server.status)
            self.end_headers()
            self.wfile.write(json.dumps({'scan_id': 12, 'counts': {'found': 3}}).encode())

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    httpd.status = 200
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, f'http://127.0.0.1:{httpd.server_port}'
    httpd.shutdown()
    thread.join()
    httpd.server_close()


def test_posts_json_with_bearer_and_returns_body(server):
    httpd, url = server
    assert call_mark_api(url, 'secret', '/api/scans', {'source': 'airflow'})['scan_id'] == 12
    assert httpd.request_data == ('/api/scans', 'Bearer secret', {'source': 'airflow'})


def test_409_raises_busy(server):
    httpd, url = server
    httpd.status = 409
    with pytest.raises(MarkApiBusy):
        call_mark_api(url, 'secret', '/api/scans', {})


@pytest.mark.parametrize('status', [401, 403])
def test_401_and_403_raise_auth_error(server, status):
    httpd, url = server
    httpd.status = status
    with pytest.raises(MarkApiAuthError, match='mark_api token rejected') as exc:
        call_mark_api(url, 'secret', '/api/scans', {})
    assert 'secret' not in str(exc.value)


def test_500_raises_api_error_with_url_not_token(server):
    httpd, url = server
    httpd.status = 500
    with pytest.raises(MarkApiError) as exc:
        call_mark_api(url, 'secret', '/api/scans', {})
    assert url in str(exc.value) and 'secret' not in str(exc.value)


def test_connection_refused_raises_api_error():
    with patch('urllib.request.urlopen', side_effect=URLError('refused')):
        with pytest.raises(MarkApiError) as exc:
            call_mark_api('http://127.0.0.1:1', 'secret', '/api/scans', {})
    assert 'http://127.0.0.1:1/api/scans' in str(exc.value) and 'secret' not in str(exc.value)


def test_summarize_counts_line():
    assert summarize({'scan_id': 42, 'counts': {'found': 10, 'queued': 4, 'unchanged': 3, 'skipped': 2}}) == (
        'scan_id=42 found=10 queued=4 unchanged=3 skipped=2')


def test_summarize_rejects_customer_data():
    with pytest.raises(ValueError, match='invalid scan summary'):
        summarize({'scan_id': 'customer-data', 'counts': {'found': 1}})


def test_task_maps_busy_and_auth_without_leaking_token(monkeypatch):
    import importlib.util
    import types

    root = Path(__file__).resolve().parents[2] / 'airflow' / 'dags'
    monkeypatch.syspath_prepend(str(root))
    from mark import mark_tasks
    class Skip(Exception):
        pass
    class Fail(Exception):
        pass
    class Hook:
        @staticmethod
        def get_connection(name):
            assert name == 'mark_api'
            return types.SimpleNamespace(schema='http', host='example.internal', port=1234, password='secret')
    modules = {
        'airflow': types.ModuleType('airflow'),
        'airflow.exceptions': types.SimpleNamespace(AirflowSkipException=Skip, AirflowFailException=Fail),
        'airflow.hooks': types.ModuleType('airflow.hooks'),
        'airflow.hooks.base': types.SimpleNamespace(BaseHook=Hook),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    for error, expected in [(mark_tasks.MarkApiBusy('private'), Skip),
                            (mark_tasks.MarkApiAuthError('private'), Fail)]:
        def reject(*args):
            assert args[:3] == ('http://example.internal:1234', 'secret', '/api/scans')
            raise error
        monkeypatch.setattr(mark_tasks, 'call_mark_api', reject)
        with pytest.raises(expected) as exc:
            mark_tasks.run_scan('/api/scans', {'source': 'airflow'})
        assert 'secret' not in str(exc.value) and 'private' not in str(exc.value)


@pytest.mark.parametrize(('filename', 'schedule', 'path', 'body', 'retries'), [
    ('mark_elr_polling', '*/15 * * * *', '/api/scans', {'source': 'airflow'}, 2),
    ('mark_pending_job_retry', '*/10 * * * *', '/api/scans/retry', {}, 2),
    ('mark_initial_load', None, '/api/scans', {'source': 'initial'}, 0),
])
def test_dag_configuration_without_airflow_or_network(monkeypatch, filename, schedule, path, body, retries):
    import runpy
    import types
    root = Path(__file__).resolve().parents[2] / 'airflow' / 'dags'
    monkeypatch.syspath_prepend(str(root))
    captured = {}
    class DAG:
        def __init__(self, **kwargs):
            captured['dag'] = kwargs
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    class PythonOperator:
        def __init__(self, **kwargs):
            captured['task'] = kwargs
    for name, module in {
        'airflow': types.SimpleNamespace(DAG=DAG),
        'airflow.operators': types.ModuleType('airflow.operators'),
        'airflow.operators.python': types.SimpleNamespace(PythonOperator=PythonOperator),
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    with patch('urllib.request.urlopen', side_effect=AssertionError('network on import')):
        runpy.run_path(str(root / 'mark' / f'{filename}.py'))
    dag, task = captured['dag'], captured['task']
    assert dag['dag_id'] == filename and dag['schedule_interval'] == schedule
    assert dag['is_paused_upon_creation'] and not dag['catchup']
    assert dag['max_active_runs'] == dag['max_active_tasks'] == 1
    assert dag['default_args']['retries'] == retries
    assert task['op_kwargs'] == {'path': path, 'body': body}
    assert task['do_xcom_push'] is False
