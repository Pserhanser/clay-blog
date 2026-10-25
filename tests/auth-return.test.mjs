import { test } from 'node:test';
import assert from 'node:assert/strict';
import { safeReturnPath } from '../server/ui/auth-return.mjs';

test('footer login returns to a valid original blog page', () => {
  assert.equal(safeReturnPath('/'), '/');
  assert.equal(safeReturnPath('/archive/'), '/archive/');
  assert.equal(safeReturnPath('/search/?q=P3R'), '/search/?q=P3R');
  assert.equal(safeReturnPath(null), '/admin/');
});

test('login redirects cannot leave the blog or use encoded network paths', () => {
  for (const value of ['https://untrusted.example/', '//untrusted.example/', '/\\untrusted.example/', '/%2F%2Funtrusted.example/', '/%5cuntrusted.example/', '/\n/untrusted.example/', 'javascript:alert(1)']) {
    assert.equal(safeReturnPath(value), '/admin/');
  }
});

test('return targets cannot lead to API data or loop through the login page', () => {
  assert.equal(safeReturnPath('/api/analytics/summary'), '/admin/');
  assert.equal(safeReturnPath('/admin/login/?next=/'), '/admin/');
  assert.equal(safeReturnPath('/%61pi/auth/session'), '/admin/');
  assert.equal(safeReturnPath('/admin/'), '/admin/');
});
