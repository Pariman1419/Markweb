import sys
from scripts import create_app_user


def test_reset_is_routed_through_authenticated_api(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, 'argv', ['create_app_user.py', 'engineer1', '--reset', '--api-url', 'http://mark.example'])
    monkeypatch.setattr(create_app_user, 'load_env', lambda: None)
    monkeypatch.setattr(create_app_user.getpass, 'getpass', lambda prompt: 'NewPassword123!' if 'admin' not in prompt.lower() else 'AdminPassword123!')
    monkeypatch.setattr('builtins.input', lambda prompt: 'admin1')
    monkeypatch.setattr(create_app_user.psycopg2, 'connect', lambda **kwargs: (_ for _ in ()).throw(AssertionError('direct DB reset is unsafe')))
    monkeypatch.setattr(create_app_user, 'reset_via_api', lambda *args: calls.append(args) or 1, raising=False)
    create_app_user.main()
    assert calls == [('http://mark.example', 'engineer1', 'NewPassword123!', 'admin1', 'AdminPassword123!')]


def test_reset_api_client_authenticates_and_sends_csrf(monkeypatch):
    import io
    import json
    from http.cookiejar import Cookie
    calls = []
    class Response:
        def __init__(self, payload): self.stream = io.BytesIO(json.dumps(payload).encode())
        def __enter__(self): return self.stream
        def __exit__(self, *args): pass
    def opener(handler):
        class Client:
            def open(self, request, timeout):
                path = request.full_url.removeprefix('http://mark.example')
                calls.append((path, request.get_header('X-csrf-token')))
                if path == '/api/auth/login':
                    handler.cookiejar.set_cookie(Cookie(0, 'mark_csrf', 'csrf-value', None, False, 'mark.example', False, False, '/', True, False, None, True, None, None, {}, False))
                    return Response({'status': 'ok'})
                if path == '/api/admin/users': return Response([{'user_id': 7, 'username': 'engineer1'}])
                return Response({'status': 'ok'})
        return Client()
    monkeypatch.setattr(create_app_user, 'build_opener', opener)
    assert create_app_user.reset_via_api('http://mark.example', 'engineer1', 'NewPassword123!', 'admin', 'AdminPassword123!') == 7
    assert calls == [('/api/auth/login', None), ('/api/admin/users', None), ('/api/admin/users/7/password', 'csrf-value'), ('/api/auth/logout', 'csrf-value')]
