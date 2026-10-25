"""SQLite analytics and authentication; independent of the public static build."""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')
FIELDS = ('path', 'pv', 'uv')


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, maxmem=64 * 1024 * 1024)
    return f'scrypt${salt.hex()}${digest.hex()}'


def verify_password(password, stored):
    try:
        algorithm, salt, expected = stored.split('$')
        if algorithm != 'scrypt':
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


class Analytics:
    def __init__(self, database, config):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.config = config
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS visits (
                    id INTEGER PRIMARY KEY, visitor TEXT NOT NULL, day TEXT NOT NULL,
                    path TEXT NOT NULL, title TEXT NOT NULL, source TEXT NOT NULL,
                    device TEXT NOT NULL, created INTEGER NOT NULL,
                    UNIQUE(visitor, day, path)
                );
                CREATE INDEX IF NOT EXISTS visits_day ON visits(day);
                CREATE TABLE IF NOT EXISTS clicks (
                    id INTEGER PRIMARY KEY, visitor TEXT NOT NULL, day TEXT NOT NULL,
                    path TEXT NOT NULL, target TEXT NOT NULL, label TEXT NOT NULL,
                    created INTEGER NOT NULL, UNIQUE(visitor,day,path,target)
                );
                CREATE INDEX IF NOT EXISTS clicks_day ON clicks(day);
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_attempts (
                    identity TEXT NOT NULL, created INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS login_attempts_identity ON login_attempts(identity, created);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def digest(self, value):
        return hmac.new(bytes.fromhex(self.config['secret']), value.encode(), hashlib.sha256).hexdigest()

    def visitor(self, cookie):
        try:
            value, signature = cookie.split('.')
            if re.fullmatch(r'[0-9a-f]{48}', value) and hmac.compare_digest(self.digest('cookie:' + value), signature):
                return self.digest('visitor:' + value), None
        except (AttributeError, ValueError):
            pass
        value = secrets.token_hex(24)
        return self.digest('visitor:' + value), value + '.' + self.digest('cookie:' + value)

    def login(self, username, password, address):
        now = int(time.time())
        identity = self.digest('login:' + address)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_attempts WHERE created < ?', (now - 900,))
            if db.execute('SELECT count(*) FROM login_attempts WHERE identity=?', (identity,)).fetchone()[0] >= 5:
                return None, 'limited'
            valid_password = verify_password(password, self.config['password_hash'])
            valid_user = hmac.compare_digest(username.encode(), self.config['username'].encode())
            if not (valid_password and valid_user):
                db.execute('INSERT INTO login_attempts VALUES (?,?)', (identity, now))
                return None, 'invalid'
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
            db.execute('DELETE FROM sessions WHERE expires < ?', (now,))
            db.execute('DELETE FROM login_attempts WHERE identity=?', (identity,))
            db.execute('INSERT INTO sessions VALUES (?,?,?)', (self.digest('session:' + token), csrf, now + 43200))
            return token, None

    def session(self, token):
        if not token or len(token) > 100:
            return None
        with self.connect() as db:
            return db.execute('SELECT csrf,expires FROM sessions WHERE token=? AND expires>?',
                              (self.digest('session:' + token), int(time.time()))).fetchone()

    def logout(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (self.digest('session:' + token),))

    def record(self, visitor, payload, agent, now=None):
        if re.search(r'bot|spider|crawler|slurp|headless', agent, re.I):
            return False
        path = urlsplit(str(payload.get('path', ''))).path
        if not path.startswith('/') or path.startswith('//') or len(path) > 500:
            raise ValueError('Invalid page path')
        if re.match(r'^/(admin|api|_astro|icons|avatars|videos)(/|$)', path):
            return False
        if re.search(r'\.[a-zA-Z0-9]{1,6}$', path) and not path.endswith('.html'):
            return False
        path = (path[:-11] if path.endswith('/index.html') else path).rstrip('/') or '/'
        title = re.sub(r'[\x00-\x1f]', '', str(payload.get('title', '')))[:160]
        source_url = urlsplit(str(payload.get('referrer', ''))[:1500])
        source = source_url.hostname or '直接访问'
        if source == urlsplit(self.config['origin']).hostname:
            source = '站内访问'
        device = '平板' if re.search(r'iPad|Tablet', agent, re.I) else '手机' if re.search(r'Mobile|Android|iPhone', agent, re.I) else '电脑'
        current = datetime.fromtimestamp(now or time.time(), TZ)
        with self.connect() as db:
            cursor = db.execute('INSERT OR IGNORE INTO visits(visitor,day,path,title,source,device,created) VALUES (?,?,?,?,?,?,?)',
                                (visitor, current.date().isoformat(), path, title, source[:255], device, int(current.timestamp())))
            return cursor.rowcount == 1

    def click(self, visitor, payload, agent):
        if re.search(r'bot|spider|crawler|slurp|headless', agent, re.I):
            return False
        path = urlsplit(str(payload.get('path', ''))).path
        target = urlsplit(str(payload.get('target', ''))[:2000])
        if not path.startswith('/') or path.startswith('//') or path.startswith(('/admin', '/api/')):
            raise ValueError('Invalid page path')
        if target.scheme not in {'http', 'https'} or not target.hostname or target.username or target.password:
            raise ValueError('Invalid link target')
        destination = target.scheme + '://' + target.netloc + target.path
        label = re.sub(r'[\x00-\x1f]', '', str(payload.get('label', '')))[:120]
        current = datetime.now(TZ)
        path = path.rstrip('/') or '/'
        self.record(visitor, payload, agent)
        with self.connect() as db:
            result = db.execute('INSERT OR IGNORE INTO clicks(visitor,day,path,target,label,created) VALUES (?,?,?,?,?,?)',
                                (visitor, current.date().isoformat(), path, destination, label, int(current.timestamp())))
            return result.rowcount == 1

    @staticmethod
    def date_range(start=None, end=None):
        today = datetime.now(TZ).date()
        end_date = datetime.strptime(end, '%Y-%m-%d').date() if end else today
        start_date = datetime.strptime(start, '%Y-%m-%d').date() if start else end_date - timedelta(days=6)
        if start_date > end_date or (end_date - start_date).days > 365 or end_date > today:
            raise ValueError('日期范围应在过去 366 天内，开始日期不能晚于结束日期')
        return start_date, end_date

    def summary(self, start=None, end=None):
        first, last = self.date_range(start, end)
        args = (first.isoformat(), last.isoformat())
        where = 'day BETWEEN ? AND ?'
        today = datetime.now(TZ).date().isoformat()
        with self.connect() as db:
            def counts(condition='', values=()):
                row = db.execute('SELECT count(*) pv,count(DISTINCT visitor) uv FROM visits ' + condition, values).fetchone()
                return dict(row)
            totals = counts()
            selected = counts('WHERE ' + where, args)
            daily = counts('WHERE day=?', (today,))
            yesterday = counts('WHERE day=?', ((datetime.now(TZ).date() - timedelta(days=1)).isoformat(),))
            total_clicks = db.execute('SELECT count(*) FROM clicks').fetchone()[0]
            click_count = db.execute(f'SELECT count(*) FROM clicks WHERE {where}', args).fetchone()[0]
            clicked_visitors = db.execute(f'SELECT count(DISTINCT visitor) FROM clicks WHERE {where}', args).fetchone()[0]
            links = [dict(row) for row in db.execute(f'SELECT target,max(label) label,count(*) count,count(DISTINCT visitor) uv FROM clicks WHERE {where} GROUP BY target ORDER BY count DESC,target LIMIT 20', args)]
            click_days = {row['day']: row['count'] for row in db.execute(f'SELECT day,count(*) count FROM clicks WHERE {where} GROUP BY day', args)}
            rows = db.execute(f'SELECT day,count(*) pv,count(DISTINCT visitor) uv FROM visits WHERE {where} GROUP BY day ORDER BY day', args).fetchall()
            by_day = {row['day']: dict(row) for row in rows}
            series = [by_day.get((first + timedelta(days=i)).isoformat(), {'day': (first + timedelta(days=i)).isoformat(), 'pv': 0, 'uv': 0})
                      for i in range((last - first).days + 1)]
            for row in series:
                row['clicks'] = click_days.get(row['day'], 0)
            pages = [dict(row) for row in db.execute(f'SELECT path,max(title) title,count(*) pv,count(DISTINCT visitor) uv FROM visits WHERE {where} GROUP BY path ORDER BY pv DESC,path LIMIT 20', args)]
            sources = [dict(row) for row in db.execute(f'SELECT source name,count(*) count FROM visits WHERE {where} GROUP BY source ORDER BY count DESC LIMIT 12', args)]
            devices = [dict(row) for row in db.execute(f'SELECT device name,count(*) count FROM visits WHERE {where} GROUP BY device ORDER BY count DESC', args)]
            recent = [dict(row) for row in db.execute(f'SELECT substr(visitor,1,8) visitor,path,source,device,created FROM visits WHERE {where} ORDER BY created DESC,id DESC LIMIT 20', args)]
        return {'from': args[0], 'to': args[1], 'today': daily, 'yesterday': yesterday,
                'total': {**totals, 'clicks': total_clicks},
                'selected': {**selected, 'clicks': click_count, 'click_rate': round(clicked_visitors / selected['uv'] * 100, 1) if selected['uv'] else 0},
                'series': series, 'pages': pages, 'links': links, 'sources': sources, 'devices': devices, 'recent': recent}
