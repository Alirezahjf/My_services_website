from app.extensions import db
from app.models import AgentActivity, AgentApproval, AgentConnection, CustomPage
from app.services.agent_service import authenticate_token, issue_token


def make_agent(permissions, approval=True):
    agent = AgentConnection(name="Test Agent", permissions=permissions, require_approval_for_sensitive=approval, rate_limit_per_minute=100)
    token = issue_token(agent)
    db.session.add(agent)
    db.session.commit()
    return agent, token


def auth(token): return {"Authorization": f"Bearer {token}"}


def test_token_hash_api_tools_and_permissions(client, app):
    with app.app_context():
        agent, token = make_agent(["products.read"])
        assert token not in agent.token_hash
    assert client.get("/api/agent/v1/tools").status_code == 401
    tools = client.get("/api/agent/v1/tools", headers=auth(token))
    assert tools.status_code == 200
    names = {item["name"] for item in tools.json["tools"]}
    assert "list_products" in names and "create_page" not in names
    denied = client.post("/api/agent/v1/call/create_page", headers=auth(token), json={"slug": "x", "title": "X", "heading": "X"})
    assert denied.status_code == 403 and denied.json["error"]["code"] == "permission_denied"
    with app.app_context(): assert AgentActivity.query.filter_by(status="denied").count() == 1


def test_agent_draft_publish_approval_audit_and_revoke(client, admin_client, app):
    with app.app_context(): agent, token = make_agent(["pages.read", "pages.create", "pages.update", "pages.publish", "reports.read", "logs.read"])
    created = client.post("/api/agent/v1/call/create_page", headers=auth(token), json={"slug": "agent/page", "title": "Agent", "heading": "Draft by agent", "html_content": "<p>safe</p><script>x</script>"})
    assert created.status_code == 200
    result = created.json["result"]
    assert result["status"] == "draft" and "script" not in result["html_content"]
    assert client.get("/agent/page").status_code == 404
    pending = client.post("/api/agent/v1/call/publish_page", headers=auth(token), json={"page_id": result["id"]})
    assert pending.json["pending_approval"] is True
    assert client.get("/agent/page").status_code == 404
    with app.app_context(): approval_id = pending.json["approval_id"]; assert AgentApproval.query.get(approval_id).status == "pending"
    admin_client.post(f"/admin/approvals/{approval_id}/approve")
    assert client.get("/agent/page").status_code == 200
    logs = client.post("/api/agent/v1/call/get_agent_activity_logs", headers=auth(token), json={})
    assert logs.status_code == 200 and len(logs.json["result"]) >= 3
    with app.app_context():
        agent = AgentConnection.query.first()
        agent.is_enabled = False
        db.session.commit()
    assert client.get("/api/agent/v1/tools", headers=auth(token)).status_code == 401


def test_strict_schema_and_no_arbitrary_execution(client, app):
    with app.app_context(): agent, token = make_agent(["pages.create"])
    response = client.post("/api/agent/v1/call/create_page", headers=auth(token), json={"slug": "safe", "title": "Safe", "heading": "Safe", "command": "rm -rf /"})
    assert response.status_code == 400 and response.json["error"]["code"] == "invalid_input"
    assert client.post("/api/agent/v1/call/not_a_tool", headers=auth(token), json={}).status_code == 404
    with app.app_context(): assert CustomPage.query.count() == 0


def test_rate_limit_and_token_rotation(client, admin_client, app):
    with app.app_context(): agent, token = make_agent(["products.read"]); agent.rate_limit_per_minute = 1; db.session.commit(); agent_id = agent.id
    assert client.get("/api/agent/v1/tools", headers=auth(token)).status_code == 200
    assert client.get("/api/agent/v1/tools", headers=auth(token)).status_code == 429
    admin_client.post(f"/admin/agents/{agent_id}/rotate")
    with app.app_context(): agent = db.session.get(AgentConnection, agent_id); new_token = issue_token(agent); db.session.commit()
    with app.app_context():
        assert authenticate_token(token) is None


def test_agent_admin_crud_shows_token_only_once(admin_client, app):
    response = admin_client.post("/admin/agents/new", data={"name": "UI Agent", "description": "Test", "permissions": ["pages.read", "pages.create"], "rate_limit_per_minute": 20, "is_enabled": "y", "require_approval_for_sensitive": "y"})
    assert response.status_code == 200 and b"hjf_" in response.data
    listing = admin_client.get("/admin/agents")
    assert b"hjf_" in listing.data and "••••••".encode() in listing.data
    with app.app_context(): assert AgentConnection.query.filter_by(name="UI Agent").count() == 1


def test_sensitive_delete_rejection_keeps_product(client, admin_client, app):
    with app.app_context():
        from app.models import Product
        product_id = Product.query.first().id
        agent, token = make_agent(["products.delete", "products.update"])
    publish = client.post("/api/agent/v1/call/update_product", headers=auth(token), json={"product_id": product_id, "status": "published"})
    assert publish.json["pending_approval"] is True
    admin_client.post(f"/admin/approvals/{publish.json['approval_id']}/reject")
    pending = client.post("/api/agent/v1/call/delete_product", headers=auth(token), json={"product_id": product_id})
    assert pending.status_code == 200 and pending.json["pending_approval"] is True
    admin_client.post(f"/admin/approvals/{pending.json['approval_id']}/reject")
    with app.app_context():
        assert db.session.get(Product, product_id) is not None
        assert AgentApproval.query.first().status == "rejected"
