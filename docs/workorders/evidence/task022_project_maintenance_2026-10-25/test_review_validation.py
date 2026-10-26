from conftest import db as db, storage as storage
from test_browser_business import browser_app as browser_app, register_ui, login_ui
from playwright.sync_api import expect


def test_review_validation_rejection_locks_corrected_draft(browser_app):
    browser, base, _, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    login_ui(page)
    page.get_by_label('项目名称', exact=True).fill('Original')
    page.get_by_role('button', name='创建 Project', exact=True).click()
    expect(page.get_by_role('heading', name='Original', exact=True)).to_be_visible()
    page.get_by_role('button', name='编辑信息', exact=True).click()
    page.get_by_label('项目名称', exact=True).fill('   ')
    page.get_by_label('描述', exact=True).fill('Valuable unsaved description')
    with page.expect_response(lambda r: r.request.method == 'PATCH') as response:
        page.get_by_role('button', name='保存修改', exact=True).click()
    assert response.value.status == 422
    expect(page.get_by_role('alert')).to_contain_text('提交结果尚未确认')
    page.get_by_label('项目名称', exact=True).fill('Corrected')
    expect(page.get_by_role('button', name='保存修改', exact=True)).to_be_disabled()
    expect(page.get_by_label('描述', exact=True)).to_have_value('Valuable unsaved description')
    page.close()
