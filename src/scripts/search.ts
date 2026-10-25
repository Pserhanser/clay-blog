import { rankSearchEntries, safeSearchUrl } from '../lib/search.mjs';

interface SearchEntry {
  kind: 'post' | 'resource';
  title: string;
  description: string;
  url: string;
  category: string;
  date: string;
  tags: string[];
  keywords: string[];
  text: string;
}

const initialized = new WeakSet<HTMLFormElement>();
let indexPromise: Promise<SearchEntry[]> | null = null;

function loadIndex() {
  if (!indexPromise) {
    indexPromise = fetch('/search.json', { signal: AbortSignal.timeout(10000), cache: 'no-cache' })
      .then(async (response) => {
        if (!response.ok) throw new Error('Index request failed');
        const items = await response.json();
        if (!Array.isArray(items) || !items.every((item) => item && typeof item.title === 'string' &&
            typeof item.category === 'string' && Array.isArray(item.tags) && safeSearchUrl(item.url))) {
          throw new Error('Invalid search index');
        }
        return items as SearchEntry[];
      }).catch((error) => { indexPromise = null; throw error; });
  }
  return indexPromise;
}

function initializeSearch() {
  const form = document.querySelector<HTMLFormElement>('.search-box');
  const input = document.querySelector<HTMLInputElement>('#search-input');
  const status = document.querySelector<HTMLElement>('[data-search-status]');
  const results = document.querySelector<HTMLElement>('[data-search-results]');
  const retry = document.querySelector<HTMLButtonElement>('[data-search-retry]');
  if (!form || !input || !status || !results || !retry || initialized.has(form)) return;
  initialized.add(form);
  let entries: SearchEntry[] | null = null;
  let failed = false;

  function render() {
    if (!entries || !input || !status || !results) return;
    const query = input.value.trim();
    results.replaceChildren();
    if (!query) {
      const resources = entries.filter((entry) => entry.kind === 'resource').length;
      status.textContent = `已索引 ${resources} 条攻略资源、${entries.length - resources} 篇文章。`;
      return;
    }
    const matches = rankSearchEntries(entries, query);
    status.textContent = matches.length ? `找到 ${matches.length} 条相关结果。` : '没有找到匹配的资源或文章。试试游戏名、别名或资料类型。';
    for (const { entry } of matches) {
      const url = safeSearchUrl(entry.url);
      if (!url) continue;
      const article = document.createElement('article');
      article.className = 'post-row post-row--plain is-revealed';
      const link = document.createElement('a');
      link.href = url;
      if (new URL(url, location.origin).origin !== location.origin) {
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
      }
      const body = document.createElement('div'); body.className = 'post-row__main';
      const meta = document.createElement('div'); meta.className = 'post-meta';
      for (const label of [entry.kind === 'resource' ? '攻略资源' : '博客文章', entry.category, entry.date].filter(Boolean)) {
        const text = document.createElement('span'); text.textContent = label; meta.append(text);
      }
      const heading = document.createElement('h3'); heading.textContent = entry.title;
      body.append(meta, heading);
      if (entry.description) { const description = document.createElement('p'); description.textContent = entry.description; body.append(description); }
      if (entry.tags.length) {
        const tags = document.createElement('div'); tags.className = 'tag-list'; tags.setAttribute('aria-label', '标签');
        for (const tag of entry.tags.slice(0, 4)) { const badge = document.createElement('span'); badge.textContent = tag; tags.append(badge); }
        body.append(tags);
      }
      link.append(body); article.append(link); results.append(article);
    }
  }

  function search() {
    if (!input || !status) return;
    const query = input.value.trim();
    const url = new URL(location.href);
    if (query) url.searchParams.set('q', query); else url.searchParams.delete('q');
    history.replaceState(history.state, '', url);
    if (!entries && !failed) status.textContent = '正在加载索引…';
    render();
  }

  async function load() {
    if (!status || !retry) return;
    failed = false;
    retry.hidden = true;
    status.textContent = '正在加载索引…';
    try {
      entries = await loadIndex();
      if (form?.isConnected) render();
    } catch {
      if (!form?.isConnected) return;
      failed = true;
      status.textContent = '索引加载失败，请点击重新加载。';
      retry.hidden = false;
    }
  }

  form.addEventListener('submit', (event) => { event.preventDefault(); search(); });
  input.addEventListener('input', search);
  retry.addEventListener('click', load);
  input.value = new URLSearchParams(location.search).get('q') ?? '';
  load();
}

document.addEventListener('astro:page-load', initializeSearch);
initializeSearch();
