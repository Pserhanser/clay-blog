"""Loopback-only HTTP service for private analytics and the local preview."""
import argparse
import csv
import hmac
import io
import json
import mimetypes
import os
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from server.analytics import Analytics

ROOT = Path(__file__).resolve().parents[1]
UI = Path(__file__).parent / 'ui'


def create_server(address, config, database, static_root=None):
    store = Analytics(database, config)
    origin = config['origin'].rstrip('/')
    secure = origin.startswith('https://')

    class Handler(BaseHTTPRequestHandler):
        server_version = 'HanserAnalytics'

        def log_message(self, format, *args):
            # Log status only; credentials, request bodies and query strings are excluded.
            print(f'{self.command} {urlsplit(self.path).path} {args[1] if len(args) > 1 else ""}', flush=True)

        def cookie(self, name):
            parsed = SimpleCookie()
            try:
                parsed.load(self.headers.get('Cookie', ''))
                return parsed[name].value if name in parsed else ''
            except Exception:
                return ''

        def make_cookie(self, name, value, age=43200):
            return f'{name}={value}; Path=/; Max-Age={age}; HttpOnly; SameSite=Strict' + ('; Secure' if secure else '')

        def send(self, status, content=b'', content_type='application/json; charset=utf-8', cookies=(), extra=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'same-origin')
            if self.path.startswith('/admin'):
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            for cookie in cookies:
                self.send_header('Set-Cookie', cookie)
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(content)

        def json(self, status, data, **kwargs):
            self.send(status, json.dumps(data, ensure_ascii=False).encode(), **kwargs)

        def error(self, status, message):
            self.json(status, {'error': message})

        def auth(self):
            return store.session(self.cookie('hanser_admin'))

        def send_file(self, path):
            if not path.is_file():
                self.error(404, '页面不存在')
                return
            mime = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
            self.send(200, path.read_bytes(), mime + ('; charset=utf-8' if mime.startswith('text/') or mime.endswith('javascript') else ''))

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            if path.startswith('/admin-assets/'):
                filename = path.removeprefix('/admin-assets/')
                if filename not in {'admin.css', 'dashboard.js', 'login.js', 'auth-return.mjs'}:
                    self.error(404, '页面不存在')
                    return
                self.send_file(UI / filename)
                return
            if path in {'/admin/login', '/admin/login/'}:
                if self.auth():
                    self.send(302, extra={'Location': '/admin/'})
                else:
                    self.send_file(UI / 'login.html')
                return
            if path == '/admin' or path.startswith('/admin/'):
                if not self.auth():
                    self.send(302, extra={'Location': '/admin/login/'})
                elif path in {'/admin', '/admin/', '/admin/index.html', '/admin/analytics/'}:
                    self.send_file(UI / 'dashboard.html')
                else:
                    self.error(404, '页面不存在')
                return
            if path.startswith('/api/'):
                if path == '/api/health':
                    self.json(200, {'ok': True})
                    return
                session = self.auth()
                if not session:
                    self.error(401, '请先登录')
                    return
                if path == '/api/auth/session':
                    self.json(200, {'username': config['username'], 'csrf': session['csrf']})
                    return
                if path in {'/api/analytics/summary', '/api/analytics/export'}:
                    query = parse_qs(parsed.query)
                    try:
                        summary = store.summary(query.get('from', [None])[0], query.get('to', [None])[0])
                    except (ValueError, TypeError):
                        self.error(400, '日期范围无效，请选择不超过 366 天的有效区间')
                        return
                    if path.endswith('/summary'):
                        self.json(200, summary)
                    else:
                        output = io.StringIO()
                        writer = csv.writer(output)
                        writer.writerow(['页面', '标题', '访问量(PV)', '访客数(UV)'])
                        for row in summary['pages']:
                            def cell(value):
                                value = str(value)
                                return "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
                            writer.writerow([cell(row['path']), cell(row['title']), row['pv'], row['uv']])
                        self.send(200, ('\ufeff' + output.getvalue()).encode(), 'text/csv; charset=utf-8',
                                  extra={'Content-Disposition': 'attachment; filename="blog-traffic.csv"'})
                    return
                self.error(404, '接口不存在')
                return
            if static_root:
                target = (Path(static_root) / path.lstrip('/')).resolve()
                if not target.is_relative_to(Path(static_root).resolve()):
                    self.error(404, '页面不存在')
                    return
                if target.is_dir():
                    target = target / 'index.html'
                self.send_file(target)
            else:
                self.error(404, '页面不存在')

        def do_POST(self):
            path = urlsplit(self.path).path
            if self.headers.get('Origin') != origin:
                self.error(403, '请求来源无效')
                return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.error(415, '请使用 JSON 请求')
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 2 or length > 8192:
                    raise ValueError()
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError()
            except (ValueError, TypeError, json.JSONDecodeError):
                self.error(400, '请求格式无效')
                return
            if path == '/api/auth/login':
                username, password = payload.get('username', ''), payload.get('password', '')
                if not isinstance(username, str) or not isinstance(password, str) or len(username) > 100 or len(password) > 256:
                    self.error(400, '账号或密码格式无效')
                    return
                address = self.headers.get('X-Real-IP', self.client_address[0]) if config.get('trust_proxy') else self.client_address[0]
                token, error = store.login(username, password, address)
                if error:
                    self.error(429 if error == 'limited' else 401, '尝试次数过多，请 15 分钟后重试' if error == 'limited' else '账号或密码错误')
                else:
                    self.json(200, {'ok': True}, cookies=[self.make_cookie('hanser_admin', token)])
                return
            if path in {'/api/analytics/visit', '/api/analytics/click'}:
                visitor, new_cookie = store.visitor(self.cookie('hanser_visitor'))
                try:
                    record = store.click if path.endswith('/click') else store.record
                    recorded = record(visitor, payload, self.headers.get('User-Agent', ''))
                except ValueError:
                    self.error(400, '页面路径无效')
                    return
                cookies = [self.make_cookie('hanser_visitor', new_cookie, 31536000)] if new_cookie else []
                self.json(200, {'recorded': recorded}, cookies=cookies)
                return
            if path == '/api/auth/logout':
                session = self.auth()
                if not session:
                    self.error(401, '请先登录')
                elif not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
                    self.error(403, '登录校验失效，请刷新页面')
                else:
                    store.logout(self.cookie('hanser_admin'))
                    self.json(200, {'ok': True}, cookies=[self.make_cookie('hanser_admin', '', 0)])
                return
            self.error(404, '接口不存在')

    server = ThreadingHTTPServer(address, Handler)
    server.analytics = store
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=4322)
    parser.add_argument('--config', type=Path, default=ROOT / '.private/analytics/config.json')
    parser.add_argument('--database', type=Path, default=ROOT / '.private/analytics/traffic.sqlite3')
    parser.add_argument('--static-root', type=Path, default=ROOT / 'dist')
    parser.add_argument('--api-only', action='store_true')
    args = parser.parse_args()
    if not args.config.is_file():
        parser.error('尚未配置管理员。先运行 python3 -m server.manage init-admin')
    config = json.loads(args.config.read_text())
    if not {'username', 'password_hash', 'secret', 'origin'} <= config.keys():
        parser.error('管理员配置不完整')
    configured_origin = urlsplit(config['origin'])
    if configured_origin.scheme != 'https' and not (configured_origin.scheme == 'http' and configured_origin.hostname in {'127.0.0.1', 'localhost'}):
        parser.error('正式站管理后台必须使用 HTTPS；HTTP 仅用于本机预览')
    try:
        if len(bytes.fromhex(config['secret'])) != 32:
            raise ValueError()
    except (ValueError, TypeError):
        parser.error('会话密钥格式无效')
    if args.config.stat().st_mode & 0o077:
        parser.error('管理员配置权限过宽，请设置为 600')
    os.umask(0o077)
    server = create_server(('127.0.0.1', args.port), config, args.database, None if args.api_only else args.static_root)
    print(f'管理后台：http://127.0.0.1:{args.port}/admin/ （仅监听本机）', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
