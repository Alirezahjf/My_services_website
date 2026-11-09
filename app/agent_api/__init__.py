"""Versioned, token-authenticated REST integration and discovery endpoints."""
import hashlib
import json
import os
import secrets
import threading
import time
from flask import Blueprint, current_app, g, jsonify, redirect, render_template_string, request
from app.extensions import db
from app.models import Product, ProductMedia
from app.services.agent_service import AgentToolError, TOOLS, authenticate_token, execute_tool
from app.services.agent_validation import clean_plain
from app.services.media_service import MediaValidationError, save_agent_image
from .openapi import document, example_for

bp = Blueprint("agent_api", __name__, url_prefix="/api/agent/v1")
discovery = Blueprint("agent_discovery", __name__)
_global_requests = {}
_global_lock = threading.Lock()


def error_response(code, message, status, message_en=None, details=None):
    return jsonify({"ok": False, "error": {"code": code, "message": message, "message_en": message_en or "The request could not be completed.", "details": details or {}, "request_id": g.get("request_id", "")}}), status


def agent_required():
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.startswith("Bearer ") else None
    try:
        agent = authenticate_token(token)
    except AgentToolError as exc:
        return None, error_response(exc.code, str(exc), 429)
    if not agent:
        return None, error_response("unauthorized", "اعتبارنامه معتبر، فعال و منقضی‌نشده لازم است.", 401, "Valid, active and unexpired bearer credentials are required.")
    g.agent = agent
    return agent, None


@bp.before_app_request
def prepare_request():
    g.request_id = "req_" + secrets.token_hex(10)
    if request.method == "OPTIONS" and request.path.startswith("/api/agent/"):
        return ("", 204)
    if current_app.config.get("ENFORCE_HTTPS") and not request.is_secure and request.path.startswith(("/api/", "/mcp")):
        return redirect(request.url.replace("http://", "https://", 1), code=301)
    now = int(time.time())
    with _global_lock:
        _global_requests[now] = _global_requests.get(now, 0) + 1
        recent = sum(count for timestamp, count in _global_requests.items() if timestamp > now - 60)
        for timestamp in list(_global_requests):
            if timestamp <= now - 60:
                _global_requests.pop(timestamp, None)
    g.global_rate = {"limit": 300, "remaining": max(0, 300 - recent)}
    if recent > 300:
        g.retry_after = 60
        return error_response("rate_limited", "سقف عمومی درخواست تکمیل شده است.", 429)
    if not request.path.startswith("/api/agent/v1") or request.path.endswith(("/openapi.json", "/docs", "/auth/refresh")):
        return None
    if request.content_length and request.content_length > 6 * 1024 * 1024:
        return error_response("payload_too_large", "حجم درخواست بیش از حد مجاز است.", 413)
    agent, error = agent_required()
    if error:
        return error
    return None


@bp.after_app_request
def integration_headers(response):
    response.headers["X-Request-ID"] = g.get("request_id", "")
    response.headers.setdefault("X-RateLimit-Global-Limit", "300")
    if g.get("global_rate"):
        response.headers["X-RateLimit-Global-Remaining"] = str(g.global_rate["remaining"])
    if g.get("agent_rate"):
        response.headers["X-RateLimit-Agent-Limit"] = str(g.agent_rate["limit"])
        response.headers["X-RateLimit-Agent-Remaining"] = str(g.agent_rate["remaining"])
    if g.get("retry_after"):
        response.headers["Retry-After"] = str(g.retry_after)
    if g.get("agent_legacy_list"):
        response.headers["Deprecation"] = "true"
        response.headers["Link"] = '</api/agent/v1/openapi.json>; rel="deprecation"'
    if current_app.config.get("ENFORCE_HTTPS") and request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    trusted = {item.strip() for item in os.getenv("TRUSTED_ORIGINS", "").split(",") if item.strip()}
    origin = request.headers.get("Origin")
    if origin in trusted:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Idempotency-Key, X-Request-ID"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


@bp.get("/health")
def health():
    return jsonify({"ok": True, "service": "agent-api", "version": "v1", "agent_id": g.agent.id})


@bp.get("/tools")
def tools():
    allowed = set(g.agent.permissions or [])
    return jsonify({"ok": True, "tools": [{"name": name, "description": tool.description,
        "permission": tool.permission, "operation": tool.operation,
        "requires_approval": bool(tool.sensitive and g.agent.require_approval_for_sensitive),
        "approval_policy": "published_record" if name == "update_page" else "sensitive" if tool.sensitive else "none",
        "examples": [example_for(name, tool.schema)], "input_schema": tool.schema} for name, tool in TOOLS.items() if tool.permission in allowed]})


@bp.post("/auth/token")
def auth_token():
    from datetime import datetime, timedelta
    from app.models import AgentRefreshToken
    from app.services.agent_service import issue_access_token
    refresh = secrets.token_urlsafe(48)
    db.session.add(AgentRefreshToken(agent_id=g.agent.id, token_hash=hashlib.sha256(refresh.encode()).hexdigest(), expires_at=datetime.utcnow() + timedelta(days=30)))
    db.session.commit()
    return jsonify({"ok": True, "access_token": issue_access_token(g.agent), "token_type": "Bearer", "expires_in": 900, "refresh_token": refresh, "refresh_expires_in": 2592000})


@bp.post("/auth/refresh")
def auth_refresh():
    from datetime import datetime, timedelta
    from app.models import AgentRefreshToken
    from app.services.agent_service import issue_access_token
    payload = request.get_json(silent=True) or {}
    refresh = payload.get("refresh_token", "")
    record = AgentRefreshToken.query.filter_by(token_hash=hashlib.sha256(refresh.encode()).hexdigest()).first() if refresh else None
    if not record or record.revoked_at or record.expires_at <= datetime.utcnow() or not record.agent.is_active:
        return error_response("unauthorized", "Refresh Token معتبر یا فعال نیست.", 401)
    record.revoked_at = datetime.utcnow()
    new_refresh = secrets.token_urlsafe(48)
    db.session.add(AgentRefreshToken(agent_id=record.agent_id, token_hash=hashlib.sha256(new_refresh.encode()).hexdigest(), expires_at=datetime.utcnow() + timedelta(days=30)))
    db.session.commit()
    return jsonify({"ok": True, "access_token": issue_access_token(record.agent), "token_type": "Bearer", "expires_in": 900, "refresh_token": new_refresh})


@bp.post("/auth/rotate")
def auth_rotate():
    from app.services.agent_service import issue_token
    token = issue_token(g.agent)
    g.agent.revoked_at = None
    db.session.commit()
    return jsonify({"ok": True, "token": token, "warning": "Store this one-time credential in a secret manager."})


@bp.post("/auth/revoke")
def auth_revoke():
    from datetime import datetime
    g.agent.revoked_at = datetime.utcnow()
    g.agent.is_enabled = False
    db.session.commit()
    return jsonify({"ok": True, "revoked": True})


@bp.get("/auth/me")
def auth_me():
    return jsonify({"ok": True, "agent": {"id": g.agent.id, "name": g.agent.name, "scopes": g.agent.permissions, "expires_at": g.agent.expires_at.isoformat() if g.agent.expires_at else None, "active": g.agent.is_active}})


@bp.get("/overview")
def overview():
    if "reports.read" not in (g.agent.permissions or []):
        return error_response("permission_denied", "مجوز reports.read لازم است.", 403)
    return jsonify(execute_tool(g.agent, "get_site_overview", {}))


@bp.post("/call/<tool_name>")
def call(tool_name):
    payload = request.get_json(silent=True)
    if payload is None:
        return error_response("invalid_json", "JSON معتبر ارسال کنید.", 400)
    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if tool_name.startswith("create_") and not idempotency_key:
        g.agent_legacy_list = True
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if idempotency_key:
        from app.models import AgentIdempotency
        previous = AgentIdempotency.query.filter_by(agent_id=g.agent.id, key=idempotency_key).first()
        if previous:
            if previous.tool_name != tool_name or previous.payload_hash != payload_hash:
                return error_response("conflict", "Idempotency-Key قبلاً با درخواست دیگری استفاده شده است.", 409)
            response = jsonify(previous.response)
            response.headers["Idempotent-Replay"] = "true"
            return response
    try:
        result = execute_tool(g.agent, tool_name, payload)
        if idempotency_key and result.get("ok"):
            from app.models import AgentIdempotency
            db.session.add(AgentIdempotency(agent_id=g.agent.id, key=idempotency_key[:100], tool_name=tool_name, payload_hash=payload_hash, response=result))
            db.session.commit()
        response = jsonify(result)
        if idempotency_key:
            response.headers["Idempotency-Key"] = idempotency_key
        return response
    except AgentToolError as exc:
        status = {"permission_denied": 403, "forbidden": 403, "not_found": 404, "rate_limited": 429, "conflict": 409}.get(exc.code, 400)
        if exc.code == "rate_limited":
            g.retry_after = g.get("agent_rate", {}).get("retry_after", 60)
        return error_response(exc.code, str(exc), status, exc.message_en, exc.details)


LIST_ROUTES = {
    "products": "list_products", "pages": "list_pages", "portfolio": "list_portfolio_items",
    "media": "list_media", "content": "list_content_sections", "activity": "get_agent_activity_logs",
}


def _query_payload(tool_name):
    payload = {}
    for key, value in request.args.items():
        rule = TOOLS[tool_name].schema["properties"].get(key)
        if not rule:
            return None, error_response("invalid_input", f"پارامتر ناشناخته: {key}", 400)
        try:
            if rule["type"] == "integer":
                value = int(value)
            elif rule["type"] == "boolean":
                if value.lower() not in {"true", "false", "1", "0"}:
                    raise ValueError
                value = value.lower() in {"true", "1"}
        except ValueError:
            return None, error_response("invalid_input", f"{key} نوع داده معتبر ندارد.", 400)
        payload[key] = value
    return payload, None


def _run_read(tool_name, payload):
    try:
        return jsonify(execute_tool(g.agent, tool_name, payload))
    except AgentToolError as exc:
        status = {"permission_denied": 403, "not_found": 404, "rate_limited": 429, "conflict": 409}.get(exc.code, 400)
        return error_response(exc.code, str(exc), status, exc.message_en, exc.details)


@bp.get("/call/<tool_name>")
def call_read(tool_name):
    tool = TOOLS.get(tool_name)
    if not tool or tool.operation != "read":
        return error_response("not_found", "متد خواندنی پیدا نشد.", 404)
    payload, error = _query_payload(tool_name)
    return error if error else _run_read(tool_name, payload)


@bp.get("/<any(products, pages, portfolio, media, content, activity):collection>")
def list_collection(collection):
    tool_name = LIST_ROUTES[collection]
    payload, error = _query_payload(tool_name)
    return error if error else _run_read(tool_name, payload)


@bp.post("/media/upload")
def media_upload():
    if "media.upload" not in (g.agent.permissions or []):
        return error_response("permission_denied", "مجوز media.upload لازم است.", 403)
    kind = request.form.get("kind", "gallery")
    if kind not in {"logo", "cover", "gallery", "mockup"}:
        return error_response("invalid_input", "نوع رسانه معتبر نیست.", 400)
    product = None
    if request.form.get("product_id"):
        try:
            product = db.session.get(Product, int(request.form["product_id"]))
        except ValueError:
            product = None
        if not product:
            return error_response("not_found", "محصول پیدا نشد.", 404)
    try:
        saved = save_agent_image(request.files.get("file"))
        media = ProductMedia(product=product, title=clean_plain(request.form.get("alt_text") or request.files["file"].filename, "alt_text")[:160], alt_text=clean_plain(request.form.get("alt_text", ""), "alt_text")[:150], media_type="image", file_path=saved["path"], thumbnail_path=saved["thumbnail"], variants=saved["variants"], mime_type=saved["mime_type"], file_size=saved["size"], role=kind if kind != "mockup" else "gallery", is_mockup=kind == "mockup")
        db.session.add(media)
        # Uploading creates metadata only; public logo/cover changes still require approval.
        db.session.commit()
        from app.services.agent_service import media_dict
        result = media_dict(media)
        result["kind"] = kind
        response = jsonify({"ok": True, **result})
        response.status_code = 201
        response.headers["Location"] = f"/api/agent/v1/media/{media.id}"
        return response
    except MediaValidationError as exc:
        db.session.rollback()
        return error_response(getattr(exc, "code", "invalid_media"), str(exc), 400)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Agent media upload failed request_id=%s", g.request_id)
        return error_response("execution_error", "آپلود امن رسانه انجام نشد.", 500)


@bp.get("/media/<int:media_id>")
def media_details(media_id):
    if "media.read" not in (g.agent.permissions or []):
        return error_response("permission_denied", "مجوز media.read لازم است.", 403)
    media = db.session.get(ProductMedia, media_id)
    if not media or media.deleted_at:
        return error_response("not_found", "رسانه پیدا نشد.", 404)
    from app.services.agent_service import media_dict
    return jsonify({"ok": True, "media": media_dict(media)})


@bp.get("/openapi.json")
def openapi():
    return jsonify(document())


@bp.get("/docs")
def docs():
    html = """<!doctype html><html lang='en'><head><meta charset='utf-8'><title>HJF Agent API</title><link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css'></head><body><div id='swagger-ui'></div><script src='https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js'></script><script>window.onload=()=>SwaggerUIBundle({url:'/api/agent/v1/openapi.json',dom_id:'#swagger-ui',deepLinking:true});</script></body></html>"""
    response = render_template_string(html)
    return response, 200, {"Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:"}


@discovery.get("/openapi.json")
def root_openapi():
    return jsonify(document())


@discovery.get("/docs")
def root_docs():
    return docs()


@discovery.get("/.well-known/mcp.json")
def mcp_discovery():
    from urllib.parse import urlsplit
    parts = urlsplit(request.url_root)
    endpoint = f"{parts.scheme}://{parts.hostname}:{os.getenv('MCP_PORT', '9901')}/mcp" if parts.scheme == "http" else f"{parts.scheme}://{parts.netloc}/mcp"
    return jsonify({"name": "HJF Website Manager", "protocol": "MCP", "transport": "streamable-http", "endpoint": endpoint, "authentication": {"type": "bearer", "header": "Authorization", "prefix": "Bearer "}, "capabilities": {"tools": True, "resources": True, "prompts": True}, "openapi": url_root(request) + "openapi.json"})


def url_root(req):
    return req.url_root.rstrip("/") + "/"
