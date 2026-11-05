"""Airflow task callable shared by the Mark DAGs."""
import logging
from mark.mark_api_client import MarkApiAuthError, MarkApiBusy, call_mark_api, summarize


def run_scan(path, body):
    from airflow.exceptions import AirflowFailException, AirflowSkipException
    from airflow.hooks.base import BaseHook

    conn = BaseHook.get_connection('mark_api')
    base_url = f'{conn.schema or "http"}://{conn.host}:{conn.port}'
    try:
        result = call_mark_api(base_url, conn.password, path, body)
    except MarkApiBusy:
        raise AirflowSkipException('Mark API scan already running') from None
    except MarkApiAuthError:
        raise AirflowFailException('mark_api token rejected') from None
    logging.info('%s', summarize(result))
