import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { App } from './App';

describe('engineering preview scope', () => {
  for (const page of ['Projects', '设置']) {
    it(`${page} shows only the unconnected preview and cannot write`, () => {
      const fetch = vi.spyOn(globalThis, 'fetch');
      try {
        render(<App />);
        fireEvent.click(within(screen.getByRole('navigation')).getByRole('button', { name: page }));
        expect(screen.getByRole('heading', { name: page })).toBeVisible();
        expect(screen.getByText('当前为工程骨架预览，未连接业务数据。')).toBeVisible();
        expect(screen.getByRole('heading', { name: page === 'Projects' ? '项目功能尚未接入' : '账号与配置功能尚未接入' })).toBeVisible();
        const main = screen.getByRole('main');
        const action = within(main).getByRole('button', { name: page === 'Projects' ? '创建 Project（尚未实现）' : '保存设置（尚未实现）' });
        expect(action).toBeDisabled();
        fireEvent.click(action);
        expect(fetch).not.toHaveBeenCalled();
        // No account/project controls or fabricated business records are exposed.
        expect(screen.getAllByRole('button')).toHaveLength(3);
        expect(within(screen.getByRole('navigation')).getAllByRole('button').map(b => b.textContent)).toEqual(['Projects', '设置']);
        expect(within(main).queryAllByRole('link')).toHaveLength(0);
        for (const role of ['textbox', 'table', 'list', 'listitem', 'img']) {
          expect(screen.queryAllByRole(role)).toHaveLength(0);
        }
        expect(screen.queryByText(/Admin|管理员|已登录|当前用户|当前项目|知识版本/)).not.toBeInTheDocument();
        expect(screen.getAllByRole('main')).toHaveLength(1);
      } finally { fetch.mockRestore(); }
    });
  }
  it('returns to Projects using local navigation', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: '设置' }));
    fireEvent.click(screen.getByRole('button', { name: 'Projects' }));
    expect(screen.getByRole('heading', { name: 'Projects' })).toBeVisible();
  });
});
