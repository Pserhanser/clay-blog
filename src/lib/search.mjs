export function resourceCategory(item) {
  if (item.tags?.includes('网盘资源')) return '网盘资源';
  if (item.owner === '游戏 Wiki' || /wiki/i.test(item.title)) return '游戏 Wiki';
  if (item.tags?.includes('攻略') || item.title.includes('攻略')) return '攻略文档';
  return '资料文档';
}

function resourceAliases(title) {
  const aliases = [];
  if (/P3R|P3reload/i.test(title)) aliases.push('女神异闻录3 Persona 3 Reload P3R P3reload');
  if (/P5R/i.test(title)) aliases.push('女神异闻录5 皇家版 Persona 5 Royal');
  if (/SMT5|真女神转生5/i.test(title)) aliases.push('真女神转生5 SMT5 复仇 Vengeance');
  if (/女神转生WIKI/i.test(title)) aliases.push('女神异闻录 Persona Wiki');
  if (/最终幻想/.test(title)) aliases.push('Final Fantasy 核心危机 Reunion FF7 重聚');
  if (/火焰纹章|火纹/.test(title)) aliases.push('火焰纹章 火纹 Fire Emblem');
  if (/异度神剑/.test(title)) aliases.push('异度之刃 Xenoblade');
  if (/八方旅人|歧路旅人/.test(title)) aliases.push('八方旅人 歧路旅人 Octopath Traveler');
  return aliases;
}

export function resourceSearchEntry(item) {
  const category = resourceCategory(item);
  const tags = [item.owner, ...(item.tags ?? [])].filter(Boolean);
  const keywords = resourceAliases(item.title);
  return {
    kind: 'resource', title: item.title, description: item.description ?? '',
    category, url: item.href, tags, keywords, date: '',
    text: [item.title, item.description, category, ...tags, ...keywords].filter(Boolean).join(' '),
  };
}

const compact = (value) => String(value ?? '').normalize('NFKC').toLowerCase().replace(/[\s·._-]+/g, '');

export function rankSearchEntries(entries, query) {
  const terms = String(query).trim().normalize('NFKC').split(/\s+/).map(compact).filter(Boolean);
  if (!terms.length) return [];
  return entries.map((entry) => {
    const fields = [
      [compact(entry.title), 10], [compact(entry.category), 4],
      [compact((entry.tags ?? []).join(' ')), 3],
      [compact((entry.keywords ?? []).join(' ')), 2],
      [compact(entry.text), 1],
    ];
    let score = 0;
    for (const term of terms) {
      const match = fields.find(([text]) => text.includes(term));
      if (!match) return null;
      score += match[1];
    }
    return { entry, score };
  }).filter(Boolean).sort((a, b) => b.score - a.score ||
    Number(b.entry.kind === 'resource') - Number(a.entry.kind === 'resource') ||
    a.entry.title.localeCompare(b.entry.title, 'zh-CN'));
}

export function safeSearchUrl(value) {
  if (typeof value !== 'string') return null;
  if (value.startsWith('/') && !value.startsWith('//') && !value.includes('\\')) return value;
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}
