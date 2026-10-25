import http.client
from http.cookies import SimpleCookie
import json
from pathlib import Path
import secrets
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from server.analytics import Analytics, password_hash, verify_password
from server.app import create_server


class AnalyticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hash = password_hash('disposable-test-password')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = {'username': 'test-admin', 'password_hash': self.hash, 'secret': secrets.token_hex(32), 'origin': 'http://blog.test'}
        self.server = create_server(('127.0.0.1', 0), self.config, Path(self.temp.name) / 'traffic.sqlite3')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookies = {}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        values = {'Origin': 'http://blog.test', 'User-Agent': 'Mozilla/5.0 test-browser'}
        if self.cookies:
            values['Cookie'] = '; '.join(f'{key}={value}' for key, value in self.cookies.items())
        if body is not None:
            values['Content-Type'] = 'application/json'
        values.update(headers or {})
        connection.request(method, path, None if body is None else json.dumps(body), values)
        response = connection.getresponse()
        for key, value in response.getheaders():
            if key.lower() == 'set-cookie':
                parsed = SimpleCookie(); parsed.load(value)
                for cookie, morsel in parsed.items():
                    if morsel['max-age'] == '0':
                        self.cookies.pop(cookie, None)
                    else:
                        self.cookies[cookie] = morsel.value
        payload = response.read()
        result = response.status, dict(response.getheaders()), payload
        connection.close()
        return result

    def login(self):
        result = self.request('POST', '/api/auth/login', {'username': 'test-admin', 'password': 'disposable-test-password'})
        self.assertEqual(result[0], 200)
        return result

    def test_unauthenticated_html_api_and_export_are_protected(self):
        for path in ['/admin/', '/admin/index.html', '/admin/analytics/']:
            status, headers, body = self.request('GET', path)
            self.assertEqual(status, 302)
            self.assertEqual(headers['Location'], '/admin/login/')
            self.assertNotIn(b'today', body)
        for path in ['/api/auth/session', '/api/analytics/summary', '/api/analytics/export']:
            self.assertEqual(self.request('GET', path)[0], 401)

    def test_login_uses_httponly_cookie_and_no_cache(self):
        _, headers, body = self.login()
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn(b'password', body)
        self.assertEqual(self.request('GET', '/admin/')[0], 200)
        self.assertEqual(self.request('GET', '/api/analytics/summary')[0], 200)

    def test_refresh_and_repeated_clicks_are_deduplicated_on_server(self):
        visit = {'path': '/archive/', 'title': '攻略资源', 'referrer': 'https://example.com/?private=query'}
        self.assertTrue(json.loads(self.request('POST', '/api/analytics/visit', visit)[2])['recorded'])
        for _ in range(4):
            self.assertFalse(json.loads(self.request('POST', '/api/analytics/visit', visit)[2])['recorded'])
        click = {**visit, 'target': 'https://example.com/resource/?private=secret', 'label': 'Resource'}
        for _ in range(3):
            self.assertEqual(self.request('POST', '/api/analytics/click', click)[0], 200)
        self.login()
        data = json.loads(self.request('GET', '/api/analytics/summary')[2])
        self.assertEqual(data['total'], {'pv': 1, 'uv': 1, 'clicks': 1})
        self.assertEqual(data['selected']['click_rate'], 100)
        self.assertEqual(data['links'][0]['target'], 'https://example.com/resource/')
        self.assertEqual(data['sources'][0]['name'], 'example.com')
        self.assertEqual(data['pages'][0]['path'], '/archive')

    def test_different_browsers_count_as_distinct_visitors(self):
        self.request('POST', '/api/analytics/visit', {'path': '/'})
        self.cookies = {}
        self.request('POST', '/api/analytics/visit', {'path': '/'})
        self.login()
        summary = json.loads(self.request('GET', '/api/analytics/summary')[2])
        self.assertEqual(summary['total']['uv'], 2)

    def test_origin_and_csrf_checks_and_session_revocation(self):
        self.assertEqual(self.request('POST', '/api/auth/login', {}, {'Origin': 'https://untrusted.example'})[0], 403)
        self.login()
        session = json.loads(self.request('GET', '/api/auth/session')[2])
        self.assertEqual(self.request('POST', '/api/auth/logout', {})[0], 403)
        self.assertEqual(self.request('POST', '/api/auth/logout', {}, {'X-CSRF-Token': session['csrf']})[0], 200)
        self.assertEqual(self.request('GET', '/api/analytics/summary')[0], 401)

    def test_failed_login_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.request('POST', '/api/auth/login', {'username': 'test-admin', 'password': 'incorrect'})[0], 401)
        self.assertEqual(self.request('POST', '/api/auth/login', {'username': 'test-admin', 'password': 'disposable-test-password'})[0], 429)

    def test_expired_session_is_rejected(self):
        self.login()
        with self.server.analytics.connect() as db:
            db.execute('UPDATE sessions SET expires=?', (int(time.time()) - 1,))
        self.assertEqual(self.request('GET', '/api/analytics/summary')[0], 401)

    def test_empty_statistics_and_invalid_dates(self):
        self.login()
        data = json.loads(self.request('GET', '/api/analytics/summary')[2])
        self.assertEqual(data['total']['pv'], 0)
        self.assertEqual(data['pages'], [])
        self.assertEqual(len(data['series']), 7)
        self.assertEqual(self.request('GET', '/api/analytics/summary?from=2099-01-01&to=2000-01-01')[0], 400)
        self.assertEqual(self.request('GET', '/api/analytics/summary?from=not-a-date')[0], 400)

    def test_bots_and_admin_routes_are_excluded(self):
        self.assertFalse(json.loads(self.request('POST', '/api/analytics/visit', {'path': '/'}, {'User-Agent': 'Googlebot'})[2])['recorded'])
        self.assertFalse(json.loads(self.request('POST', '/api/analytics/visit', {'path': '/admin/'})[2])['recorded'])
        self.assertEqual(self.server.analytics.summary()['total']['pv'], 0)

    def test_secure_password_hash_and_signed_visitor_cookie(self):
        self.assertNotIn('disposable-test-password', self.hash)
        self.assertTrue(verify_password('disposable-test-password', self.hash))
        self.assertFalse(verify_password('wrong', self.hash))
        first, cookie = self.server.analytics.visitor('')
        same, replacement = self.server.analytics.visitor(cookie)
        self.assertEqual(first, same)
        self.assertIsNone(replacement)
        forged, replacement = self.server.analytics.visitor(cookie + 'tampered')
        self.assertNotEqual(first, forged)
        self.assertIsNotNone(replacement)

    def test_parallel_refreshes_count_once_and_next_day_counts_again(self):
        store = self.server.analytics
        visitor, _ = store.visitor('')
        now = time.time()
        def record(_):
            return store.record(visitor, {'path': '/'}, 'Mozilla/5.0', now=now)
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(record, range(12)))
        self.assertEqual(sum(results), 1)
        self.assertTrue(store.record(visitor, {'path': '/'}, 'Mozilla/5.0', now=now - 86400))
        self.assertEqual(store.summary()['total']['pv'], 2)
        self.assertEqual(store.summary()['total']['uv'], 1)

    def test_authenticated_csv_export_escapes_formulas(self):
        self.request('POST', '/api/analytics/visit', {'path': '/', 'title': '=malicious_formula'})
        self.login()
        status, headers, body = self.request('GET', '/api/analytics/export')
        self.assertEqual(status, 200)
        self.assertIn('text/csv', headers['Content-Type'])
        self.assertIn("'=malicious_formula", body.decode('utf-8-sig'))
        self.assertNotIn('password', body.decode('utf-8-sig'))


if __name__ == '__main__':
    unittest.main()
