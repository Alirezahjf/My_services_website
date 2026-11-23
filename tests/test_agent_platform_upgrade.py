import io
import json
import pytest
from app.extensions import db
from app.models import AgentApproval, AgentConnection, CustomPage, Product, ProductMedia
from app.services.agent_service import issue_token


def agent_token(scopes):
    agent = AgentConnection(name="Upgrade test", permissions=scopes, rate_limit_per_minute=500)
    token = issue_token(agent)
    db.session.add(agent)
    db.session.commit()
    return agent, token


def headers(token, **extra):
    return {"Authorization": f"Bearer {token}", **extra}


def test_p0_xss_nonexistent_approvals_and_no_changes(client, app):
    with app.app_context():
        agent, token = agent_token(["products.create", "products.update", "products.delete", "pages.publish", "menus.manage", "media.delete"])
    xss = client.post("/api/agent/v1/call/create_product", headers=headers(token), json={"name": "<script>alert(1)</script>", "short_description": "xss"})
    assert xss.status_code == 400 and xss.json["error"]["code"] == "invalid_input"
    for tool, payload in [
        ("update_product", {"product_id": 9999, "name": "x"}),
        ("archive_product", {"product_id": 9999}),
        ("delete_product", {"product_id": 9999}),
        ("publish_page", {"page_id": 9999}),
        ("remove_menu_item", {"menu_id": 9999}),
        ("delete_media", {"media_id": 9999}),
    ]:
        response = client.post(f"/api/agent/v1/call/{tool}", headers=headers(token), json=payload)
        assert response.status_code == 404, (tool, response.data)
        assert response.json["error"]["code"] == "not_found"
    with app.app_context():
        assert AgentApproval.query.count() == 0
        product_id = Product.query.first().id
    empty = client.post("/api/agent/v1/call/update_product", headers=headers(token), json={"product_id": product_id})
    assert empty.status_code == 400 and empty.json["error"]["code"] == "no_changes"


def test_menu_url_alias_and_real_listing(client, app):
    with app.app_context(): agent, token = agent_token(["menus.read", "menus.manage"])
    created = client.post("/api/agent/v1/call/add_menu_item", headers=headers(token), json={"title": "تست", "location": "header", "url": "https://example.com"})
    assert created.status_code == 200 and created.json["result"]["location"] == "main"
    listing = client.post("/api/agent/v1/call/list_menus", headers=headers(token), json={})
    assert any(row["id"] == created.json["result"]["id"] for row in listing.json["result"])
    unsafe = client.post("/api/agent/v1/call/add_menu_item", headers=headers(token), json={"title": "bad", "location": "main", "url": "javascript:alert(1)"})
    assert unsafe.status_code == 400
    missing = client.post("/api/agent/v1/call/add_menu_item", headers=headers(token), json={"title": "bad", "location": "main"})
    assert missing.status_code == 400 and missing.json["error"]["code"] == "missing_target"


def test_custom_code_published_approval_and_risky_js(client, admin_client, app):
    with app.app_context(): agent, token = agent_token(["pages.read", "pages.create", "pages.update"])
    created = client.post("/api/agent/v1/call/create_page", headers=headers(token), json={"slug": "agent/timer", "title": "Timer", "heading": "Timer", "custom_js": "document.getElementById('d').textContent='TEST'", "custom_css": "#d{color:red}"})
    assert created.status_code == 200 and created.json["result"]["custom_js"].endswith("'TEST'")
    with app.app_context(): page_id = created.json["result"]["id"]
    update = client.post("/api/agent/v1/call/update_page", headers=headers(token), json={"page_id": page_id, "html_content": "<div id='d'></div>"})
    assert update.status_code == 200
    admin_client.post(f"/admin/pages/{page_id}/status", data={"status": "published"})
    pending = client.post("/api/agent/v1/call/update_page", headers=headers(token), json={"page_id": page_id, "title": "Changed"})
    assert pending.json["pending_approval"] is True
    admin_client.post(f"/admin/approvals/{pending.json['approval_id']}/approve")
    live = client.get("/agent/timer")
    assert b"textContent='TEST'" in live.data and b"color:red" in live.data and b'nonce="' in live.data
    get_page = client.post("/api/agent/v1/call/get_page", headers=headers(token), json={"page_id": page_id})
    assert get_page.json["result"]["has_custom_js"] is True and get_page.json["result"]["custom_css"] == "#d{color:red}"
    risky = client.post("/api/agent/v1/call/update_page", headers=headers(token), json={"page_id": page_id, "custom_js": "eval('x')"})
    assert risky.status_code == 400 and risky.json["error"]["code"] == "risky_js"


def test_pagination_status_idempotency_discovery_and_options(client, app, monkeypatch):
    with app.app_context(): agent, token = agent_token(["products.read", "products.create"])
    response = client.post("/api/agent/v1/call/list_products?x=1", headers=headers(token), json={"limit": 2, "sort": "id", "order": "asc"})
    assert response.status_code == 200 and len(response.json["data"]) == 2
    assert response.json["pagination"]["limit"] == 2
    if response.json["pagination"]["has_more"]:
        cursor = response.json["pagination"]["next_cursor"]
        next_page = client.post("/api/agent/v1/call/list_products", headers=headers(token), json={"limit": 2, "cursor": cursor})
        assert next_page.status_code == 200
    invalid = client.post("/api/agent/v1/call/list_products", headers=headers(token), json={"status": "INVALID"})
    assert invalid.status_code == 400 and invalid.json["error"]["code"] == "invalid_status"
    key = "550e8400-e29b-41d4-a716-446655440000"
    payload = {"name": "Idempotent product", "short_description": "safe"}
    first = client.post("/api/agent/v1/call/create_product", headers=headers(token, **{"Idempotency-Key": key}), json=payload)
    second = client.post("/api/agent/v1/call/create_product", headers=headers(token, **{"Idempotency-Key": key}), json=payload)
    assert first.json["result"]["id"] == second.json["result"]["id"] and second.headers["Idempotent-Replay"] == "true"
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/api/agent/v1/openapi.json").status_code == 200
    assert client.get("/.well-known/mcp.json").status_code == 200
    monkeypatch.setenv("TRUSTED_ORIGINS", "https://trusted.app")
    options = client.options("/api/agent/v1/call/list_products", headers={"Origin": "https://trusted.app"})
    assert options.status_code == 204 and options.headers["Access-Control-Allow-Origin"] == "https://trusted.app"


def test_media_upload_logo_cover_and_invalid_mime(client, admin_client, app):
    with app.app_context():
        agent, token = agent_token(["media.upload", "media.read", "media.manage", "media.delete", "products.read"])
        product = Product.query.first()
        product_id, slug = product.id, product.slug
    upload = client.post("/api/agent/v1/media/upload", headers=headers(token), data={"file": (io.BytesIO(b"\x89PNG\r\n\x1a\ninvalid"), "logo.png"), "product_id": str(product_id), "kind": "logo"}, content_type="multipart/form-data")
    assert upload.status_code == 400 and upload.json["error"]["code"] == "invalid_mime"
    from PIL import Image
    stream = io.BytesIO(); Image.new("RGB", (700, 500), "#6758e8").save(stream, "PNG"); stream.seek(0)
    upload = client.post("/api/agent/v1/media/upload", headers=headers(token), data={"file": (stream, "logo.png"), "product_id": str(product_id), "kind": "gallery", "alt_text": "Safe logo"}, content_type="multipart/form-data")
    assert upload.status_code == 201 and upload.json["mime"] == "image/webp"
    assert set(upload.json["variants"]) == {"256", "512", "1024"}
    media_id = upload.json["id"]
    pending = client.post("/api/agent/v1/call/set_product_logo", headers=headers(token), json={"product_id": product_id, "media_id": media_id})
    assert pending.json["pending_approval"] is True
    admin_client.post(f"/admin/approvals/{pending.json['approval_id']}/approve")
    product = client.post("/api/agent/v1/call/get_product", headers=headers(token), json={"product_id": product_id})
    assert product.json["result"]["logo_url"].endswith(".webp")
    public = client.get(f"/products/{slug}")
    assert product.json["result"]["logo_url"].encode() in public.data
    conflict = client.post("/api/agent/v1/call/delete_media", headers=headers(token), json={"media_id": media_id})
    assert conflict.status_code == 409 and conflict.json["error"]["code"] == "conflict"


def test_short_lived_access_and_rotating_refresh_token(client, app):
    with app.app_context(): agent, token = agent_token(["products.read"])
    issued = client.post("/api/agent/v1/auth/token", headers=headers(token))
    assert issued.status_code == 200 and issued.json["expires_in"] == 900
    access = issued.json["access_token"]
    me = client.get("/api/agent/v1/auth/me", headers=headers(access))
    assert me.status_code == 200 and "products.read" in me.json["agent"]["scopes"]
    refreshed = client.post("/api/agent/v1/auth/refresh", json={"refresh_token": issued.json["refresh_token"]})
    assert refreshed.status_code == 200 and refreshed.json["access_token"] != access
    replay = client.post("/api/agent/v1/auth/refresh", json={"refresh_token": issued.json["refresh_token"]})
    assert replay.status_code == 401
