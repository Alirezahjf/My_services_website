from app.extensions import db
from app.models import CustomPage, MenuItem, PageRedirect


def page_payload(**overrides):
    data = {"slug": "company/ai-consulting", "title": "مشاوره AI", "heading": "مشاوره هوش مصنوعی", "subtitle": "زیرعنوان", "summary": "خلاصه", "html_content": "<h2>عنوان</h2><script>alert(1)</script><p onclick='x()'>متن امن</p>", "status": "draft", "seo_title": "SEO", "seo_description": "شرح", "menu_title": "مشاوره", "menu_order": 2, "show_in_main": "y", "show_in_footer": "y", "menu_links_enabled": "y"}
    data.update(overrides)
    return data


def test_complete_page_lifecycle_and_sanitization(admin_client, client, app):
    response = admin_client.post("/admin/pages/new", data=page_payload(), follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        page = CustomPage.query.filter_by(slug="company/ai-consulting").one()
        page_id = page.id
        assert page.status == "draft" and "script" not in page.html_content and "onclick" not in page.html_content
    assert client.get("/company/ai-consulting").status_code == 404
    assert app.test_client().get(f"/admin/pages/{page_id}/preview").status_code == 302
    preview = admin_client.get(f"/admin/pages/{page_id}/preview")
    assert preview.status_code == 200 and "متن امن".encode() in preview.data
    admin_client.post(f"/admin/pages/{page_id}/status", data={"status": "published"})
    public = client.get("/company/ai-consulting")
    assert public.status_code == 200 and "مشاوره هوش مصنوعی".encode() in public.data
    assert b"<script>alert(1)</script>" not in public.data
    assert "مشاوره".encode() in client.get("/").data  # selected main/footer navigation
    assert "company/ai-consulting".encode() in client.get("/sitemap.xml").data
    admin_client.post(f"/admin/pages/{page_id}/status", data={"status": "unpublished"})
    assert client.get("/company/ai-consulting").status_code == 404
    admin_client.post(f"/admin/pages/{page_id}/status", data={"status": "published"})
    assert client.get("/company/ai-consulting").status_code == 200


def test_persian_slug_redirect_archive_and_delete(admin_client, client, app):
    admin_client.post("/admin/pages/new", data=page_payload(slug="مشاوره-هوشمند", status="published"))
    with app.app_context(): page_id = CustomPage.query.filter_by(slug="مشاوره-هوشمند").one().id
    assert client.get("/مشاوره-هوشمند").status_code == 200
    admin_client.post(f"/admin/pages/{page_id}/edit", data=page_payload(slug="ai/new-path", status="published"))
    response = client.get("/مشاوره-هوشمند")
    assert response.status_code == 301 and response.headers["Location"].endswith("/ai/new-path")
    with app.app_context(): assert PageRedirect.query.filter_by(old_path="مشاوره-هوشمند").count() == 1
    admin_client.post(f"/admin/pages/{page_id}/status", data={"status": "archived"})
    assert client.get("/ai/new-path").status_code == 404
    admin_client.post(f"/admin/pages/{page_id}/delete")
    assert client.get("/ai/new-path").status_code == 404


def test_reserved_slug_rejected(admin_client, app):
    response = admin_client.post("/admin/pages/new", data=page_payload(slug="admin/fake"))
    assert response.status_code == 200
    assert "رزرو شده".encode() in response.data
    with app.app_context(): assert CustomPage.query.count() == 0


def test_database_menu_crud_and_visibility(admin_client, client, app):
    admin_client.post("/admin/pages/new", data=page_payload(status="published", show_in_main=""))
    with app.app_context(): page_id = CustomPage.query.first().id
    data = {"title": "لینک تست", "location": "footer", "page_id": page_id, "internal_url": "", "external_url": "", "parent_id": 0, "position": 3, "is_enabled": "y"}
    admin_client.post("/admin/menus/new", data=data)
    assert "لینک تست".encode() in client.get("/").data
    with app.app_context(): item = MenuItem.query.first(); menu_id = item.id
    admin_client.post(f"/admin/menus/{menu_id}/edit", data={**data, "title": "لینک ویرایش‌شده", "is_enabled": ""})
    assert "لینک ویرایش‌شده".encode() not in client.get("/").data
    admin_client.post(f"/admin/menus/{menu_id}/delete")
    with app.app_context(): assert MenuItem.query.count() == 0


def test_motion_and_accessibility_fallbacks(client):
    page = client.get("/")
    assert page.status_code == 200 and b"data-scroll-progress" in page.data and b"data-page-enter" in page.data
    css = client.get("/static/css/main.css").data.decode()
    js = client.get("/static/js/main.js").data.decode()
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert "@media(max-width:820px)" in css
    assert "prefers-reduced-motion: reduce" in js
    assert b"[data-page-enter]" in page.data and b"noscript" in page.data


def test_new_admin_interfaces_render(admin_client):
    for path in ("/admin/pages", "/admin/menus", "/admin/agents", "/admin/agent-activity"):
        response = admin_client.get(path)
        assert response.status_code == 200, path


def test_linked_page_appears_in_content_admin_and_public_section(admin_client, client, app):
    from app.models import PageContent
    with app.app_context():
        content = PageContent.query.filter_by(page_key="about", section_key="main").one()
        content_id = content.id
    payload = page_payload(slug="company/linked", title="صفحه زیرمجموعه", status="published", parent_content_id=content_id)
    created = admin_client.post("/admin/pages/new", data=payload)
    with app.app_context():
        saved = CustomPage.query.filter_by(slug="company/linked").one()
        assert saved.parent_content_id == content_id, created.data.decode()
        assert db.session.get(PageContent, content_id).custom_pages.count() == 1
    public = client.get("/about")
    assert public.status_code == 200
    assert "صفحه‌های مرتبط".encode() in public.data and "مشاوره".encode() in public.data
    assert b'href="/company/linked"' in public.data
    admin_list = admin_client.get("/admin/content")
    assert "صفحه زیرمجموعه".encode() in admin_list.data and b"content-child-page" in admin_list.data
    with app.app_context(): page_id = CustomPage.query.filter_by(slug="company/linked").one().id
    admin_client.post(f"/admin/pages/{page_id}/status", data={"status": "unpublished"})
    assert b'href="/company/linked"' not in client.get("/about").data


def test_admin_only_css_javascript_and_csp_nonce(admin_client, client, app):
    payload = page_payload(
        slug="coded-page", status="published",
        css_content=".custom-page-content{--trusted-color:rgb(1, 2, 3)}",
        js_content="document.documentElement.dataset.trustedPage='yes';",
    )
    admin_client.post("/admin/pages/new", data=payload)
    response = client.get("/coded-page")
    assert response.status_code == 200
    assert b"--trusted-color:rgb(1, 2, 3)" in response.data
    assert b"dataset.trustedPage='yes'" in response.data
    csp = response.headers["Content-Security-Policy"]
    assert "nonce-" in csp
    nonce = response.data.decode().split('<script nonce="')[1].split('"')[0]
    assert f"'nonce-{nonce}'" in csp
    ordinary = client.get("/")
    assert "nonce-" not in ordinary.headers["Content-Security-Policy"]
