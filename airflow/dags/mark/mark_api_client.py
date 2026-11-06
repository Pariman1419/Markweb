"""Minimal HTTP client for the Mark scan API; no Airflow dependency."""
import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit


class MarkApiError(Exception):
    def __init__(self, status, url):
        self.status = status
        self.url = url
        super().__init__(f'Mark API request failed ({status}): {url}')


class MarkApiBusy(Exception):
    pass


class MarkApiAuthError(Exception):
    pass


def call_mark_api(base_url: str, token: str, path: str, body: dict, timeout: float = 120.0) -> dict:
    url = base_url.rstrip('/') + path
    parsed = urlsplit(url)
    safe_url = urlunsplit((parsed.scheme, parsed.netloc.rsplit('@', 1)[-1], parsed.path, '', ''))
    request = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), method='POST',
                                     headers={'Content-Type': 'application/json',
                                              'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            try:
                return json.load(response)
            except (ValueError, UnicodeError, OSError):
                return {}
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            raise MarkApiBusy('Mark API scan already running') from None
        if exc.code in (401, 403):
            raise MarkApiAuthError('mark_api token rejected') from None
        raise MarkApiError(exc.code, safe_url) from None
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
        raise MarkApiError('unavailable', safe_url) from None


def summarize(resp: dict) -> str:
    if not isinstance(resp, dict) or not isinstance(resp.get('counts'), dict):
        return 'summary unavailable'
    counts = resp['counts']
    scan_id = resp.get('scan_id')
    values = [counts.get(key, 0) for key in ('found', 'queued', 'unchanged', 'skipped')]
    if type(scan_id) is not int or any(type(value) is not int for value in values):
        return 'summary unavailable'
    return ' '.join([f'scan_id={scan_id}'] +
                    [f'{key}={value}' for key, value in zip(('found', 'queued', 'unchanged', 'skipped'), values)])
