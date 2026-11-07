from pathlib import Path
import re


def test_shared_ip_limits_allow_a_100_request_burst_without_weakening_login():
    text = Path('web/nginx.conf').read_text(encoding='utf-8')
    limits = {name: int(burst) for name, burst in re.findall(r'limit_req zone=(login|files|api) burst=(\d+)', text)}
    assert limits['login'] == 5
    assert limits['api'] >= 200
    assert limits['files'] >= 100
