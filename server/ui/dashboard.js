import { announceAuthChange } from './auth-return.mjs';

const $ = (selector) => document.querySelector(selector);
const format = (value) => Number(value || 0).toLocaleString('zh-CN');
let csrf = '';
let controller;
const dayString = (date) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
const today = dayString(new Date());
window.addEventListener('pageshow', (event) => { if (event.persisted) location.reload(); });
$('#date-from').max = today;
$('#date-to').max = today;

async function request(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  if (response.status === 401) { document.body.classList.add('session-expired'); location.replace('/admin/login/'); throw new Error('登录已失效'); }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || '数据暂时无法加载，请稍后重试');
  }
  return response;
}
function make(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function emptyRow(body, columns, message) {
  body.replaceChildren();
  const row = make('tr'); const cell = make('td', message, 'table-empty'); cell.colSpan = columns; row.append(cell); body.append(row);
}
function chart(series) {
  const root = $('#trend-chart'); root.replaceChildren();
  const width = 900, height = 230, left = 38, right = 18, top = 14, bottom = 36;
  const max = Math.max(4, ...series.map((day) => day.pv), ...series.map((day) => day.uv), ...series.map((day) => day.clicks));
  const ceiling = Math.ceil(max / 4) * 4;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const x = (i) => left + (series.length === 1 ? plotWidth / 2 : i * plotWidth / (series.length - 1));
  const y = (n) => top + plotHeight - n / ceiling * plotHeight;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('aria-hidden', 'true');
  function draw(tag, attributes, text) {
    const element = document.createElementNS(svg.namespaceURI, tag);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    if (text !== undefined) element.textContent = text;
    svg.append(element); return element;
  }
  for (let step = 0; step <= 4; step++) {
    const value = ceiling * step / 4;
    draw('line', { x1: left, y1: y(value), x2: width - right, y2: y(value), stroke: '#edf1ef', 'stroke-dasharray': '3 5' });
    draw('text', { x: left - 10, y: y(value) + 4, 'text-anchor': 'end', fill: '#b0b9bd', 'font-size': 10 }, format(value));
  }
  const labelIndices = new Set([0, series.length - 1]);
  for (let i = 0; i < series.length; i += Math.max(1, Math.ceil(series.length / 7))) labelIndices.add(i);
  for (const i of labelIndices) draw('text', { x: x(i), y: height - 11, 'text-anchor': 'middle', fill: '#a8b4b1', 'font-size': 10 }, series[i].day.slice(5).replace('-', '/'));
  for (const [key, color] of [['pv', '#55ad85'], ['uv', '#aeb4dc'], ['clicks', '#dbb37b']]) {
    const points = series.map((day, i) => `${x(i)},${y(day[key])}`).join(' ');
    if (key === 'pv') draw('polygon', { points: `${x(0)},${y(0)} ${points} ${x(series.length - 1)},${y(0)}`, fill: '#eaf6ee', opacity: '.75' });
    draw('polyline', { points, fill: 'none', stroke: color, 'stroke-width': 2.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' });
    if (series.length <= 31) series.forEach((day, i) => {
      const circle = draw('circle', { cx: x(i), cy: y(day[key]), r: 3, fill: 'white', stroke: color, 'stroke-width': 1.5 });
      const title = document.createElementNS(svg.namespaceURI, 'title'); title.textContent = `${day.day} ${key.toUpperCase()} ${day[key]}`; circle.append(title);
    });
  }
  root.append(svg);
  root.setAttribute('aria-label', series.map((day) => `${day.day}：访问量${day.pv}，访客${day.uv}`).join('；'));
  $('#empty-chart').hidden = series.some((day) => day.pv > 0);
}
function render(data) {
  document.querySelectorAll('[data-metric]').forEach((element) => { const [group, field] = element.dataset.metric.split('.'); element.textContent = format(data[group][field]); });
  $('#range-caption').textContent = `${data.from} — ${data.to} · 北京时间`;
  $('#range-pv').textContent = format(data.selected.pv); $('#range-uv').textContent = format(data.selected.uv);
  $('#range-clicks').textContent = format(data.selected.clicks);
  $('#click-rate').textContent = `${data.selected.click_rate}%`;
  chart(data.series);
  const links = $('#links-table'); links.replaceChildren();
  for (const link of data.links) {
    const row = make('tr'); const cell = make('td'); cell.append(make('strong', link.label || link.target), make('small', link.target));
    row.append(cell, make('td', format(link.count)), make('td', format(link.uv)), make('td', `${(link.count / Math.max(1, data.selected.clicks) * 100).toFixed(1)}%`)); links.append(row);
  }
  if (!data.links.length) emptyRow(links, 4, '该日期范围暂无链接点击记录');
  const pages = $('#pages-table'); pages.replaceChildren();
  for (const page of data.pages) {
    const row = make('tr'); const cell = make('td'); cell.append(make('strong', page.title || page.path), make('small', page.path));
    row.append(cell, make('td', format(page.pv)), make('td', format(page.uv))); pages.append(row);
  }
  if (!data.pages.length) emptyRow(pages, 3, '该日期范围暂无页面访问记录');
  const sources = $('#sources-list'); sources.replaceChildren();
  for (const source of data.sources) {
    const row = make('div', undefined, 'source-row'); row.append(make('span', source.name, 'source-name'), make('span', format(source.count)));
    const bar = make('div', undefined, 'source-bar'); const progress = make('span');
    // Inline style attributes are allowed by CSSOM; no user strings are inserted as CSS.
    progress.style.width = `${Math.round(source.count / Math.max(1, data.selected.pv) * 100)}%`;
    bar.append(progress); row.append(bar); sources.append(row);
  }
  if (!data.sources.length) sources.append(make('p', '暂无来源数据', 'empty-state'));
  const devices = $('#devices-list'); devices.replaceChildren();
  for (const device of data.devices) { const badge = make('div', device.name, 'device-badge'); badge.append(make('strong', format(device.count))); devices.append(badge); }
  if (!data.devices.length) devices.append(make('span', '暂无设备数据', 'muted'));
  const recent = $('#recent-table'); recent.replaceChildren();
  for (const visit of data.recent) {
    const date = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(visit.created * 1000);
    const row = make('tr'); row.append(...[date, `访客 ${visit.visitor}`, visit.path, visit.source, visit.device].map((value) => make('td', value))); recent.append(row);
  }
  if (!data.recent.length) emptyRow(recent, 5, '该日期范围暂无到访记录');
  $('#updated-at').textContent = `更新于 ${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`;
}
async function load() {
  controller?.abort(); controller = new AbortController();
  $('#dashboard-error').hidden = true; document.body.classList.add('is-loading');
  try {
    const query = new URLSearchParams({ from: $('#date-from').value, to: $('#date-to').value });
    const data = await (await request(`/api/analytics/summary?${query}`, { signal: controller.signal })).json();
    render(data); $('.live-badge').textContent = '● 数据已连接';
  } catch (error) {
    if (error.name === 'AbortError') return;
    $('#dashboard-error').textContent = error.message; $('#dashboard-error').hidden = false; $('.live-badge').textContent = '数据连接失败';
  } finally { document.body.classList.remove('is-loading'); }
}
function preset(days) {
  const end = new Date(); const start = new Date(end); start.setDate(start.getDate() - days + 1);
  $('#date-from').value = dayString(start); $('#date-to').value = dayString(end);
  document.querySelectorAll('[data-days]').forEach((button) => { const selected = Number(button.dataset.days) === days; button.classList.toggle('selected', selected); button.setAttribute('aria-pressed', String(selected)); });
}
document.querySelectorAll('[data-days]').forEach((button) => button.addEventListener('click', () => { preset(Number(button.dataset.days)); load(); }));
$('#range-form').addEventListener('submit', (event) => { event.preventDefault(); document.querySelectorAll('[data-days]').forEach((button) => { button.classList.remove('selected'); button.setAttribute('aria-pressed', 'false'); }); load(); });
document.querySelectorAll('[data-logout]').forEach((button) => button.addEventListener('click', async () => {
  try { await request('/api/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: '{}' }); announceAuthChange(); location.replace('/admin/login/'); }
  catch (error) { $('#dashboard-error').textContent = error.message; $('#dashboard-error').hidden = false; }
}));
$('#export').addEventListener('click', async () => {
  $('#export').disabled = true;
  try {
    const query = new URLSearchParams({ from: $('#date-from').value, to: $('#date-to').value });
    const response = await request(`/api/analytics/export?${query}`);
    const url = URL.createObjectURL(await response.blob()); const link = make('a'); link.href = url; link.download = 'blog-traffic.csv'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { $('#dashboard-error').textContent = error.message; $('#dashboard-error').hidden = false; }
  finally { $('#export').disabled = false; }
});
async function refreshSession() {
  try { const session = await (await request('/api/auth/session')).json(); csrf = session.csrf; $('#account-name').textContent = session.username; }
  catch {}
}
window.addEventListener('focus', refreshSession);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshSession(); });
if (typeof BroadcastChannel !== 'undefined') {
  const channel = new BroadcastChannel('hanser-blog-auth');
  channel.addEventListener('message', refreshSession);
}
(async () => {
  try { const session = await (await request('/api/auth/session')).json(); csrf = session.csrf; $('#account-name').textContent = session.username; preset(7); await load(); }
  catch (error) { $('#dashboard-error').textContent = error.message; $('#dashboard-error').hidden = false; }
})();
