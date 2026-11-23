from app.models import AdminUser, Category, Product


def test_admin_requires_authentication(client):
    response = client.get("/admin/")
    assert response.status_code == 302
    assert "/admin/login" in response.location


def test_login_logout_and_invalid_password(client):
    response = client.post("/admin/login", data={"username": "admin", "password": "wrong"})
    assert "نادرست".encode() in response.data
    response = client.post("/admin/login", data={"username": "admin", "password": "a-very-secure-test-password"}, follow_redirects=True)
    assert "داشبورد".encode() in response.data
    response = client.post("/admin/logout", follow_redirects=True)
    assert "خارج شدید".encode() in response.data


def test_all_main_admin_pages(admin_client):
    urls = ["/admin/", "/admin/products", "/admin/products/new", "/admin/categories", "/admin/categories/new", "/admin/features", "/admin/portfolios", "/admin/media", "/admin/media/new", "/admin/content", "/admin/services", "/admin/services/new", "/admin/faqs", "/admin/settings", "/admin/workflow", "/admin/leads", "/admin/leads?kind=message", "/admin/repositories", "/admin/activity", "/admin/password"]
    for url in urls:
        response = admin_client.get(url)
        assert response.status_code == 200, url


def test_create_and_publish_product(admin_client, app):
    with app.app_context():
        category = Category.query.first()
    data = {"name": "محصول آزمون", "repository_name": "test-repo", "category_id": category.id, "product_type": "software", "status": "draft", "confidence": "high", "short_description": "شرح واقعی محصول آزمون", "position": 1, "accent_color": "#6758e8", "use_cases_text": "کاربرد یک", "target_audience_text": "مخاطب یک", "prerequisites_text": "Python", "limitations_text": "محدودیت آزمون", "technologies_text": "Flask", "tags_text": "تست، نرم‌افزار"}
    response = admin_client.post("/admin/products/new", data=data, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        product = Product.query.filter_by(name="محصول آزمون").one()
        assert product.status == "draft"
        assert len(product.tags) == 2
        product_id = product.id
    admin_client.post(f"/admin/products/{product_id}/status", data={"status": "published"})
    assert admin_client.get("/products/محصول-آزمون").status_code == 200


def test_category_delete_is_protected(admin_client, app):
    with app.app_context():
        category = Category.query.filter_by(slug="ai-assistants").one()
        category_id = category.id
    response = admin_client.post(f"/admin/categories/{category_id}/delete", follow_redirects=True)
    assert "دارای محصول".encode() in response.data
    with app.app_context():
        assert Category.query.get(category_id) is not None


def test_password_hash_and_change(admin_client, app):
    with app.app_context():
        admin = AdminUser.query.filter_by(username="admin").one()
        assert admin.password_hash != "a-very-secure-test-password"
    response = admin_client.post("/admin/password", data={"current_password": "a-very-secure-test-password", "new_password": "new-secure-password-123", "confirm_password": "new-secure-password-123"}, follow_redirects=True)
    assert "رمز عبور تغییر کرد".encode() in response.data
    with app.app_context():
        assert AdminUser.query.filter_by(username="admin").one().check_password("new-secure-password-123")
