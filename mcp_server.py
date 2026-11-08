"""Official MCP SDK Streamable HTTP server with per-agent Bearer authentication.
Run: uvicorn mcp_server:asgi_app --host 0.0.0.0 --port 9901
The Flask application and this ASGI service share only the audited service layer.
"""
import contextvars
import inspect
import json
import os
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from app import create_app
from app.services.agent_service import TOOLS, AgentToolError, authenticate_token, execute_tool

flask_app = create_app()
current_agent = contextvars.ContextVar("current_agent", default=None)
mcp = FastMCP("HJF Website Manager", instructions="Manage only explicitly permitted website records. Sensitive operations may remain pending for human approval.",
              streamable_http_path="/mcp", json_response=True, stateless_http=True,
              host="0.0.0.0", port=int(os.getenv("MCP_PORT", "9901")), max_request_body_size=1048576)


def _handler(name, tool):
    async def call(**kwargs):
        agent = current_agent.get()
        if not agent:
            return {"ok": False, "error": {"code": "unauthorized", "message": "Bearer token required"}}
        # Optional JSON-nulls are omitted before strict service validation.
        payload = {key: value for key, value in kwargs.items() if value is not None}
        with flask_app.app_context():
            from app.extensions import db
            agent = db.session.merge(agent)
            try:
                return execute_tool(agent, name, payload)
            except AgentToolError as exc:
                raise ToolError(json.dumps({"code": exc.code, "message": str(exc)}, ensure_ascii=False)) from exc
    parameters = []
    for key, rule in tool.schema["properties"].items():
        annotation = {"string": str, "integer": int, "boolean": bool}[rule["type"]]
        default = inspect.Parameter.empty if key in tool.schema["required"] else None
        parameters.append(inspect.Parameter(key, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=annotation))
    call.__signature__ = inspect.Signature(parameters, return_annotation=dict)
    call.__annotations__["return"] = dict
    call.__name__ = name
    call.__doc__ = tool.description
    return call


for tool_name, definition in TOOLS.items():
    mcp.tool(name=tool_name, description=definition.description, structured_output=False)(_handler(tool_name, definition))


@mcp.resource("site://overview")
def site_overview():
    """Safe branding and public record counts for the authenticated agent."""
    agent = current_agent.get()
    if not agent or "reports.read" not in (agent.permissions or []):
        return json.dumps({"ok": False, "error": "reports.read required"})
    with flask_app.app_context():
        from app.extensions import db
        return json.dumps(execute_tool(db.session.merge(agent), "get_site_overview", {}), ensure_ascii=False)


@mcp.resource("site://tools")
def available_tools():
    """Names and permissions available to this connection."""
    agent = current_agent.get()
    allowed = set(agent.permissions or []) if agent else set()
    return json.dumps({name: tool.description for name, tool in TOOLS.items() if tool.permission in allowed}, ensure_ascii=False)


@mcp.prompt()
def safe_content_manager(task: str = "Review website content"):
    """Prompt template that keeps draft/review boundaries explicit."""
    return f"Task: {task}\nUse only permitted tools. Create drafts by default. Never claim pending approval is completed. Never request source code, shell, raw SQL, tokens, passwords or private contact content."


class BearerAgentMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        content_length = int(headers.get(b"content-length", b"0") or 0)
        authorization = headers.get(b"authorization", b"").decode("latin1")
        token = authorization[7:].strip() if authorization.startswith("Bearer ") else None
        error = None
        agent = None
        if content_length > 1048576:
            error = (413, "payload_too_large", "Maximum MCP request size is 1MB")
        else:
            with flask_app.app_context():
                try:
                    agent = authenticate_token(token)
                    if not agent:
                        error = (401, "unauthorized", "Valid, active and unexpired agent token required")
                except AgentToolError as exc:
                    error = (429, exc.code, str(exc))
        if error:
            status, code, message = error
            body = json.dumps({"jsonrpc": "2.0", "error": {"code": code, "message": message}}).encode()
            await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"www-authenticate", b"Bearer")]})
            await send({"type": "http.response.body", "body": body})
            return
        reset = current_agent.set(agent)
        try:
            await self.app(scope, receive, send)
        finally:
            current_agent.reset(reset)


asgi_app = BearerAgentMiddleware(mcp.streamable_http_app())
app = asgi_app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mcp_server:asgi_app", host="0.0.0.0", port=int(os.getenv("MCP_PORT", "9901")), workers=1)
