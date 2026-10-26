import { test, expect } from '@playwright/test';
for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
  test(`preview navigation and unavailable actions ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    const writes: string[] = [];
    const businessRequests: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (request.method() !== 'GET') writes.push(request.url());
      if (['fetch', 'xhr', 'websocket'].includes(request.resourceType())) businessRequests.push(request.url());
    });
    await page.goto('/');
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: '跳到内容' })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('main')).toBeFocused();
    for (const name of ['Projects', '设置']) {
      await page.getByRole('button', { name, exact: true }).click();
      await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
      await expect(page.getByText('当前为工程骨架预览，未连接业务数据。')).toBeVisible();
      await expect(page.getByRole('button', { name: name === 'Projects' ? '创建 Project（尚未实现）' : '保存设置（尚未实现）' })).toBeDisabled();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect(page.getByRole('main')).toHaveCount(1);
      await page.screenshot({ path: `test-results/shell-${viewport.width}-${name === 'Projects' ? 'projects' : 'settings'}.png`, fullPage: true });
    }
    await page.getByRole('button', { name: 'Projects', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Projects', exact: true })).toBeVisible();
    expect(errors).toEqual([]);
    expect(writes).toEqual([]);
    expect(businessRequests).toEqual([]);
  });
}
