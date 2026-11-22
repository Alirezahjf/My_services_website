from app.models import ContactMessage, Lead, Product


def test_public_pages_render(client, app):
    with app.app_context():
        urls = ["/", "/products", "/services", "/about", "/contact", "/consultation", "/custom-solution", "/portfolio", "/legal/privacy", "/legal/terms", "/sitemap.xml", "/robots.txt"]
        urls += [f"/products/{p.slug}" for p in Product.query.filter_by(status="published").all()]
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url
        assert b"text/html" in response.content_type.encode() or url.endswith((".xml", ".txt"))


def test_catalogue_filters_and_hides_unpublished(client):
    response = client.get("/products?q=ترند")
    assert "ترند رادار".encode() in response.data
    response = client.get("/products", query_string={"category": "infrastructure", "type": "infrastructure"})
    assert "وی‌پی‌ان سَنایی".encode() in response.data
    assert "عامل اجرایی هوشمند".encode() not in response.data
    assert client.get("/products/app-claude-code-fcc").status_code == 404
    home = client.get("/")
    assert "پروژه بدون محتوای FCC".encode() not in home.data


def test_product_pagination_and_empty_result(client):
    assert client.get("/products?page=999").status_code == 200
    response = client.get("/products?q=no-such-product-xyz")
    assert "محصولی با این مشخصات".encode() in response.data


def test_contact_submission_and_validation(client, app):
    response = client.post("/contact", data={"name": "کاربر واقعی", "phone": "09121234567", "email": "user@example.com", "subject": "مشاوره", "message": "برای بررسی یک راهکار پیام می‌دهم.", "website": ""}, follow_redirects=True)
    assert "با موفقیت ثبت شد".encode() in response.data
    with app.app_context():
        assert ContactMessage.query.count() == 1
    response = client.post("/contact", data={"name": "الف", "phone": "bad", "subject": "", "message": "کوتاه"})
    assert response.status_code == 200
    with app.app_context():
        assert ContactMessage.query.count() == 1


def test_consultation_is_linked_to_product(client, app):
    with app.app_context():
        product = Product.query.filter_by(slug="trend-radar").one()
    response = client.post("/consultation", data={"name": "درخواست‌دهنده", "phone": "+989121234567", "product_id": str(product.id), "request_type": "demo", "message": "درخواست دمو دارم", "website": ""}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        lead = Lead.query.one()
        assert lead.product_id == product.id
        assert lead.request_type == "demo"


def test_custom_solution_submission(client, app):
    response = client.post("/custom-solution", data={"organization": "شرکت آزمون", "name": "مدیر", "phone": "02122334455", "industry": "فروشگاه", "need_type": "اتوماسیون", "message": "شرح کامل نیاز پروژه برای بررسی فنی", "budget": "توافقی"}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert Lead.query.filter_by(request_type="custom").count() == 1


def test_security_headers(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert client.get("/media/../config.py").status_code in {400, 404}
