"""Token-authenticated JSON integration API; independent from MCP transport."""
from flask import Blueprint, g, jsonify, request
from app.services.agent_service import AgentToolError, TOOLS, authenticate_token, execute_tool

bp = Blueprint("agent_api", __name__, url_prefix="/api/agent/v1")


def agent_required():
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.startswith("Bearer ") else None
    try:
        agent = authenticate_token(token)
    except AgentToolError as exc:
        return None, (jsonify({"ok": False, "error": {"code": exc.code, "message": str(exc)}}), 429)
    if not agent:
        return None, (jsonify({"ok": False, "error": {"code": "unauthorized", "message": "اعتبارنامه معتبر، فعال و منقضی‌نشده لازم است."}}), 401)
    g.agent = agent
    return agent, None


@bp.before_request
def authenticate():
    if request.content_length and request.content_length > 65536:
        return jsonify({"ok": False, "error": {"code": "payload_too_large", "message": "حداکثر درخواست ۶۴KB است."}}), 413
    agent, error = agent_required()
    if error:
        return error
    return None


@bp.get("/tools")
def tools():
    allowed = set(g.agent.permissions or [])
    return jsonify({"ok": True, "tools": [{"name": name, "description": tool.description,
        "permission": tool.permission, "operation": tool.operation,
        "requires_approval": tool.sensitive and g.agent.require_approval_for_sensitive,
        "input_schema": tool.schema} for name, tool in TOOLS.items() if tool.permission in allowed]})


@bp.get("/overview")
def overview():
    if "reports.read" not in (g.agent.permissions or []):
        return jsonify({"ok": False, "error": {"code": "permission_denied", "message": "مجوز reports.read لازم است."}}), 403
    return jsonify(execute_tool(g.agent, "get_site_overview", {}))


@bp.post("/call/<tool_name>")
def call(tool_name):
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"ok": False, "error": {"code": "invalid_json", "message": "JSON معتبر ارسال کنید."}}), 400
    try:
        result = execute_tool(g.agent, tool_name, payload)
        return jsonify(result)
    except AgentToolError as exc:
        status = {"permission_denied": 403, "not_found": 404, "rate_limited": 429}.get(exc.code, 400)
        return jsonify({"ok": False, "error": {"code": exc.code, "message": str(exc)}}), status
