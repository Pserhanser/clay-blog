import { test } from 'node:test';
import assert from 'node:assert/strict';
import { getDailyVisitorStats } from '../src/lib/visitor-stats.mjs';

function setup() {
  const records = new Map();
  const storage = {
    getItem: (key) => records.get(key) ?? null,
    setItem: (key, value) => records.set(key, value),
    removeItem: (key) => records.delete(key),
  };
  let calls = 0;
  const request = async () => ({ busuanzi_site_pv: ++calls, busuanzi_site_uv: 1, busuanzi_page_pv: 1 });
  return { storage, request, calls: () => calls };
}

test('refreshing and returning to the same page count only once per day', async () => {
  const fixture = setup();
  const options = { ...fixture, day: '2026-10-25', path: '/archive/' };
  const first = await getDailyVisitorStats(options);
  for (let i = 0; i < 5; i++) assert.deepEqual(await getDailyVisitorStats(options), first);
  await getDailyVisitorStats({ ...options, path: '/archive' });
  assert.equal(fixture.calls(), 1);
});

test('another page counts once and cached pages retain the newest site totals', async () => {
  const fixture = setup();
  const options = { ...fixture, day: '2026-10-25', path: '/' };
  await getDailyVisitorStats(options);
  await getDailyVisitorStats({ ...options, path: '/archive/' });
  const home = await getDailyVisitorStats(options);
  assert.equal(fixture.calls(), 2);
  assert.equal(home.busuanzi_site_pv, 2);
  assert.equal(home.busuanzi_page_pv, 1);
});

test('a new day allows one new visit', async () => {
  const fixture = setup();
  const options = { ...fixture, day: '2026-10-25', path: '/' };
  await getDailyVisitorStats(options);
  await getDailyVisitorStats({ ...options, day: '2026-10-26' });
  await getDailyVisitorStats({ ...options, day: '2026-10-26' });
  assert.equal(fixture.calls(), 2);
});

test('blocked browser storage does not repeatedly increment the provider', async () => {
  const fixture = setup();
  const storage = { ...fixture.storage, setItem() { throw new Error('storage blocked'); } };
  await assert.rejects(getDailyVisitorStats({ ...fixture, storage, day: '2026-10-25', path: '/' }));
  assert.equal(fixture.calls(), 0);
});
