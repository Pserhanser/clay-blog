import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { rankSearchEntries, resourceCategory, resourceSearchEntry, safeSearchUrl } from '../src/lib/search.mjs';

const site = JSON.parse(readFileSync(new URL('../src/data/site.config.json', import.meta.url)));
const cloud = JSON.parse(readFileSync(new URL('../src/data/cloud-resources.json', import.meta.url)));
const entries = [...site.projectGroups[0].items, ...cloud].map(resourceSearchEntry);

test('game titles and document metadata are searchable from the shared resource data', () => {
  const results = rankSearchEntries(entries, '最终幻想');
  assert.equal(results.length, 1);
  assert.ok(results[0].entry.title.includes('核心危机'));
  assert.equal(results[0].entry.kind, 'resource');
  assert.ok(results[0].entry.url.startsWith('https://docs.qq.com/'));
  assert.ok(rankSearchEntries(entries, '腾讯文档').length > 5);
  assert.equal(rankSearchEntries(entries, '视频制作')[0].entry.title, '网盘离线资源');
});

test('aliases, full-width characters, spaces, and case are normalized', () => {
  assert.equal(rankSearchEntries(entries, '女神异闻录3').length, 2);
  assert.equal(rankSearchEntries(entries, 'ｐ３ｒ').length, 2);
  assert.equal(rankSearchEntries(entries, '最终幻想核心危机').length, 1);
  assert.ok(rankSearchEntries(entries, '火纹').length >= 3);
});

test('multiple words must all match and resource groups stay exclusive', () => {
  const results = rankSearchEntries(entries, '最终幻想 攻略');
  assert.equal(results.length, 1);
  assert.equal(rankSearchEntries(entries, '最终幻想 不存在的关键词').length, 0);
  assert.equal(resourceCategory(cloud[0]), '网盘资源');
  assert.equal(entries.find((entry) => entry.title === '火焰纹章万缕千丝 Wiki').category, '游戏 Wiki');
});

test('only safe internal or HTTP(S) result destinations are allowed', () => {
  assert.equal(safeSearchUrl('javascript:alert(1)'), null);
  assert.equal(safeSearchUrl('//untrusted.example/'), null);
  assert.equal(safeSearchUrl('/\\untrusted.example/'), null);
  assert.equal(safeSearchUrl('/archive/'), '/archive/');
  assert.equal(safeSearchUrl('https://example.com/resource/'), 'https://example.com/resource/');
});
