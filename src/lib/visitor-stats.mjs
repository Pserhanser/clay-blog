const fields = ['busuanzi_site_pv', 'busuanzi_site_uv', 'busuanzi_page_pv'];
const prefix = 'hanser:visitor-stats:v1:';

function readRecord(storage, key) {
  try {
    const record = JSON.parse(storage.getItem(key) ?? 'null');
    return record && typeof record.day === 'string' && record.stats &&
      fields.every((field) => Number.isSafeInteger(record.stats[field]) && record.stats[field] >= 0)
      ? record : null;
  } catch {
    return null;
  }
}

// Each path has one bounded cache record, replaced on the next calendar day.
// Call inside a Web Lock in the browser to also serialize visits across tabs.
export async function getDailyVisitorStats({ storage, day, path, request }) {
  const pageKey = prefix + (path.replace(/\/+$/, '') || '/');
  const latestKey = prefix + 'latest';
  // If storage is blocked/full, do not send a request that every refresh would repeat.
  storage.setItem(prefix + 'probe', '1');
  storage.removeItem(prefix + 'probe');

  const saved = readRecord(storage, pageKey);
  if (saved?.day === day) {
    const latest = readRecord(storage, latestKey);
    return {
      ...saved.stats,
      busuanzi_site_pv: Math.max(saved.stats.busuanzi_site_pv, latest?.stats.busuanzi_site_pv ?? 0),
      busuanzi_site_uv: Math.max(saved.stats.busuanzi_site_uv, latest?.stats.busuanzi_site_uv ?? 0),
    };
  }

  const result = await request();
  const stats = Object.fromEntries(fields.map((field) => [field, Number(result[field])]));
  if (!fields.every((field) => Number.isSafeInteger(stats[field]) && stats[field] >= 0)) {
    throw new Error('Invalid statistics response');
  }
  const record = JSON.stringify({ day, stats });
  storage.setItem(pageKey, record);
  storage.setItem(latestKey, record);
  return stats;
}
