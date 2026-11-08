import io
from app.models import Category, PageContent, Portfolio, Product, ProductFeature, ProductMedia, FAQ


def test_feature_and_faq_crud(admin_client, app):
    with app.app_context():
        product = Product.query.first()
    response = admin_client.post("/admin/features/new", data={"product_id": product.id, "title": "قابلیت آزمون", "description": "توضیح", "verification_status": "verified", "position": 1, "is_published": "y"}, follow_redirects=True)
    assert response.status_code == 200
    response = admin_client.post("/admin/faqs/new", data={"product_id": product.id, "question": "سؤال آزمون؟", "answer": "پاسخ آزمون", "position": 0, "is_published": "y"}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert ProductFeature.query.filter_by(title="قابلیت آزمون").count() == 1
        assert FAQ.query.filter_by(question="سؤال آزمون؟").count() == 1


def test_content_html_is_sanitized(admin_client, app):
    data = {"page_key": "about", "section_key": "security-test", "title": "امن", "body": "<p>متن</p><script>alert(1)</script><a href=\"javascript:alert(1)\">لینک</a>", "position": 0, "is_published": "y"}
    admin_client.post("/admin/content/new", data=data)
    with app.app_context():
        content = PageContent.query.filter_by(section_key="security-test").one()
        assert "<script>" not in content.body
        assert "javascript:" not in content.body
        assert "<p>متن</p>" in content.body


def test_portfolio_relations(admin_client, app):
    with app.app_context():
        product = Product.query.first()
        category = Category.query.first()
    data = {"title": "نمونه آزمون", "summary": "خلاصه", "description": "شرح", "product_ids": [str(product.id)], "category_ids": [str(category.id)], "position": 0, "show_on_product": "y", "show_in_gallery": "y"}
    response = admin_client.post("/admin/portfolios/new", data=data, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        item = Portfolio.query.filter_by(title="نمونه آزمون").one()
        assert item.categories[0].id == category.id
        assert item.product_links[0].product_id == product.id


def test_upload_and_reject_disguised_image(admin_client, app, png_file):
    with app.app_context():
        product = Product.query.first()
        initial_count = ProductMedia.query.count()
    data = {"owner_type": "product", "owner_id": str(product.id), "title": "تصویر آزمون", "media_type": "image", "position": 0, "is_published": "y", "file": (png_file, "screen.png")}
    response = admin_client.post("/admin/media/new", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert "بارگذاری و متصل شد".encode() in response.data
    with app.app_context():
        assert ProductMedia.query.count() == initial_count + 1
        media = ProductMedia.query.filter_by(title="تصویر آزمون").one()
        assert ".." not in media.file_path
        assert media.thumbnail_path.endswith(".webp")
    bad = {"owner_type": "product", "owner_id": str(product.id), "title": "فایل مخرب", "media_type": "image", "position": 0, "file": (io.BytesIO(b"not an image"), "fake.png")}
    admin_client.post("/admin/media/new", data=bad, content_type="multipart/form-data")
    with app.app_context():
        assert ProductMedia.query.count() == initial_count + 1


def test_multiple_image_upload(admin_client, app, png_file):
    with app.app_context():
        product = Product.query.first()
        initial_count = ProductMedia.query.count()
    second = io.BytesIO(png_file.read())
    png_file.seek(0)
    second.seek(0)
    data = {"owner_type": "product", "owner_id": str(product.id), "title": "گالری", "media_type": "image", "position": 0, "is_published": "y", "file": [(png_file, "one.png"), (second, "two.png")]}
    response = admin_client.post("/admin/media/new", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert ProductMedia.query.count() == initial_count + 2


def test_brand_settings_and_csv(admin_client, app):
    data = {"brand_name": "برند تازه", "brand_tagline": "شعار", "brand_description": "شرح", "email": "info@example.com", "phone": "02122", "website_url": "https://example.com", "copyright_text": "کپی", "default_seo_title": "عنوان", "default_seo_description": "شرح", "social_share_image": ""}
    response = admin_client.post("/admin/settings", data=data, follow_redirects=True)
    assert "ذخیره شد".encode() in response.data
    assert "برند تازه".encode() in admin_client.get("/").data
    response = admin_client.get("/admin/leads/export.csv")
    assert response.status_code == 200
    assert response.data.startswith(b"\xef\xbb\xbf")
