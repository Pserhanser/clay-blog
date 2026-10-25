import { safeReturnPath, announceAuthChange } from './auth-return.mjs';

const form = document.querySelector('#login-form');
const error = document.querySelector('#login-error');
const submit = document.querySelector('#login-submit');
document.querySelector('#toggle-password').addEventListener('click', () => {
  const password = document.querySelector('#password');
  const visible = password.type === 'password';
  password.type = visible ? 'text' : 'password';
  document.querySelector('#toggle-password').textContent = visible ? '隐藏' : '显示';
  document.querySelector('#toggle-password').setAttribute('aria-label', visible ? '隐藏密码' : '显示密码');
});
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  error.hidden = true;
  submit.disabled = true;
  submit.textContent = '正在登录…';
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
      body: JSON.stringify({ username: form.username.value, password: form.password.value }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '登录失败，请重试');
    form.password.value = '';
    announceAuthChange();
    location.replace(safeReturnPath(new URLSearchParams(location.search).get('next')));
  } catch (failure) {
    error.textContent = failure.message || '网络连接失败，请稍后重试';
    error.hidden = false;
  } finally {
    submit.disabled = false;
    submit.textContent = '登录管理中心 ↗';
  }
});
