from app.extensions import db
from app.models import Category, PlatformConnector, Product, ProductModule, ProductRepository, ProductRepositoryMembership
from scripts.seed_concepts import PRODUCTS, seed_concepts


def test_exactly_six_safe_concept_products(app):
    with app.app_context():
        products = Product.query.filter_by(commercial_status="concept").all()
        assert {p.slug for p in products} == {p["slug"] for p in PRODUCTS}
        assert len(products) == 6
        for product in products:
            assert product.status == "published"
            assert product.origin_type == "independent"
            assert not product.ai_enabled and not product.automation_enabled
            assert not product.demo_available and not product.repository_enabled
            assert product.github_url is None
            assert product.connectors and product.modules and product.faqs and product.media
            assert all(m.is_mockup for m in product.media)
            assert all(c.connection_status == "not_connected" and not c.is_enabled for c in product.connectors)
            assert all(f.verification_status != "verified" for f in product.features)


def test_new_categories_and_secondary_category_filter(client, app):
    with app.app_context():
        slugs = {c.slug for c in Category.query.all()}
        assert {"smart-social-management", "marketing-audience-growth", "business-market-analysis", "messenger-management", "communication-automation", "crm-lead-management", "ai-assistant-products"} <= slugs
    response = client.get("/products?category=ai-assistant-products")
    assert response.status_code == 200
    for name in (b"InstaPilot AI", b"AudienceFlow AI", b"LeadRadar AI", b"MarketMind AI"):
        assert name in response.data


def test_concept_pages_expose_disclosures_and_connector_states(client):
    for data in PRODUCTS:
        response = client.get(f"/products/{data['slug']}")
        assert response.status_code == 200
        assert "معرفی اولیه".encode() in response.data
        assert "تصویر نمایشی / Mockup".encode() in response.data
        assert "متصل نیست".encode() in response.data
        assert data["name"].encode() in response.data


def test_concept_seed_is_idempotent(app):
    with app.app_context():
        before = (Product.query.count(), PlatformConnector.query.count(), ProductModule.query.count())
        seed_concepts()
        after = (Product.query.count(), PlatformConnector.query.count(), ProductModule.query.count())
        assert before == after == (22, 11, 13)


def test_hybrid_repository_membership_preserves_product_copy(app):
    with app.app_context():
        product = Product.query.filter_by(slug="instapilot-ai").one()
        repository = ProductRepository.query.first()
        original = product.full_description
        membership = ProductRepositoryMembership(product=product, repository=repository, role="future_connector")
        product.origin_type = "hybrid"
        db.session.add(membership)
        db.session.commit()
        assert product.full_description == original
        assert product.repository_memberships[0].role == "future_connector"
        assert product.github_url is None  # Primary curated content remains independent.


def test_admin_integrations_page_and_connector_form(admin_client, app):
    with app.app_context():
        product = Product.query.filter_by(slug="instapilot-ai").one()
        product_id = product.id
    assert admin_client.get("/admin/integrations").status_code == 200
    response = admin_client.get(f"/admin/connectors/new?product={product_id}")
    assert response.status_code == 200
    assert "وضعیت اتصال".encode() in response.data


def test_admin_connector_and_module_crud(admin_client, app):
    with app.app_context():
        product_id = Product.query.filter_by(slug="instapilot-ai").one().id
    connector_data = {"product_id": product_id, "platform": "future-api", "display_name": "Future API", "connection_status": "not_connected", "capability_status": "planned", "position": 9, "supported_features_text": "", "limitations_text": "هیچ اتصال فعالی نیست"}
    response = admin_client.post("/admin/connectors/new", data=connector_data, follow_redirects=True)
    assert response.status_code == 200
    module_data = {"product_id": product_id, "name": "Audit Log", "description": "ثبت رویدادهای آینده", "status": "planned", "position": 9}
    response = admin_client.post("/admin/modules/new", data=module_data, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        connector = PlatformConnector.query.filter_by(product_id=product_id, platform="future-api").one()
        module = ProductModule.query.filter_by(product_id=product_id, name="Audit Log").one()
        assert connector.connection_status == "not_connected" and not connector.is_enabled
        admin_client.post(f"/admin/connectors/{connector.id}/delete")
        admin_client.post(f"/admin/modules/{module.id}/delete")
        assert db.session.get(PlatformConnector, connector.id) is None
        assert db.session.get(ProductModule, module.id) is None


def test_no_unsupported_marketing_claims_in_concept_copy(app):
    forbidden = ["تضمین رشد", "افزایش فروش تضمینی", "پشتیبانی کامل تمام پلتفرم", "اتصال رسمی فعال"]
    with app.app_context():
        for product in Product.query.filter_by(commercial_status="concept"):
            copy = " ".join([product.short_description, product.medium_description, product.full_description])
            assert not any(term in copy for term in forbidden)
