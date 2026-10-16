// v1.0. Run with node --test; no application or third-party dependencies.
import test from 'node:test';
import assert from 'node:assert/strict';
import { formatDate, formatElapsed } from './format.mjs';

test('missing, invalid, ambiguous and impossible timestamps remain unknown', () => {
  for (const value of [null, undefined, '', 'bad', '2026-10-16', '2026-10-16T12:00:00', '2026-02-30T12:00:00Z', '2026-13-01T00:00:00Z']) {
    assert.equal(formatDate(value), '—');
  }
});
test('timezone and year are explicit across year boundaries', () => {
  assert.equal(formatDate('2025-12-31T18:30:00Z'), '2026/01/01 02:30');
  assert.equal(formatDate('2025-12-31T18:30:00Z', 'UTC'), '2025/12/31 18:30');
  assert.equal(formatDate('2026-01-01T02:30:00+08:00', 'UTC'), '2025/12/31 18:30');
  assert.match(formatDate('2024-02-29T00:00:00Z'), /^2024/);
  assert.throws(() => formatDate('2026-01-01T00:00:00Z', 'invalid-zone'), RangeError);
});
test('duration handles absent, non-finite and fractional input', () => {
  for (const value of [null, undefined, NaN, Infinity, -1, '60']) assert.equal(formatElapsed(value), '—');
  assert.equal(formatElapsed(0), '0s');
  assert.equal(formatElapsed(59.9), '59s');
  assert.equal(formatElapsed(60), '1m0s');
  assert.equal(formatElapsed(121.9), '2m1s');
});
