"""Interactive local setup; never accepts plaintext passwords as CLI arguments."""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets

from server.analytics import password_hash

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['init-admin'])
    parser.add_argument('--config', type=Path, default=ROOT / '.private/analytics/config.json')
    parser.add_argument('--origin', default='http://127.0.0.1:4322')
    args = parser.parse_args()
    if args.config.exists():
        parser.error('配置已存在；为避免意外替换管理员凭据，本命令不会覆盖已有文件')
    username = input('管理员账号：').strip()
    password = getpass.getpass('管理员密码（至少 8 位）：')
    if not username or len(username) > 100 or len(password) < 8 or len(password) > 256:
        parser.error('账号或密码长度不符合要求')
    if password != getpass.getpass('再次输入密码：'):
        parser.error('两次密码不一致')
    config = {'username': username, 'password_hash': password_hash(password), 'secret': secrets.token_hex(32), 'origin': args.origin.rstrip('/')}
    os.umask(0o077)
    args.config.parent.mkdir(parents=True, exist_ok=True)
    with args.config.open('x') as output:
        json.dump(config, output, indent=2)
    args.config.chmod(0o600)
    print('管理员配置已创建，密码仅以 scrypt 哈希保存；配置文件不进入 Git。')


if __name__ == '__main__':
    main()
