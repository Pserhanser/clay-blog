export function safeReturnPath(value, fallback = '/admin/') {
  if (typeof value !== 'string' || value.length > 2048 || !value.startsWith('/') ||
      value.startsWith('//') || /[\\\x00-\x1f\x7f]/.test(value)) return fallback;
  try {
    const url = new URL(value, 'https://blog.invalid');
    const decoded = decodeURIComponent(url.pathname);
    if (url.origin !== 'https://blog.invalid' || decoded.startsWith('//') || /[\\\x00-\x1f\x7f]/.test(decoded) ||
        /^\/api(?:\/|$)/.test(decoded) || /^\/admin\/login(?:\/|$)/.test(decoded)) return fallback;
    return url.pathname + url.search + url.hash;
  } catch { return fallback; }
}

export function announceAuthChange() {
  if (typeof BroadcastChannel === 'undefined') return;
  const channel = new BroadcastChannel('hanser-blog-auth');
  channel.postMessage({ type: 'session-changed' });
  channel.close();
}
