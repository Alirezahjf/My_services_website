"""OpenAPI generated from the same authoritative tool registry used by REST and MCP."""
from flask import request, url_for
from app.services.agent_service import TOOLS


def example_for(name, schema):
    examples = {
        "create_product": {"name": "محصول نمونه", "short_description": "توضیح کوتاه"},
        "create_page": {"slug": "company/example", "title": "صفحه نمونه", "heading": "عنوان صفحه"},
        "update_page": {"page_id": 1, "html_content": "<div id=\"timer\"></div>", "custom_css": "#timer{color:red}", "custom_js": "document.getElementById('timer').textContent='TEST'"},
        "add_menu_item": {"title": "مستندات", "location": "main", "url": "https://example.com/docs"},
        "set_product_logo": {"product_id": 1, "media_id": 1},
    }
    if name in examples:
        return examples[name]
    payload = {}
    for key in schema.get("required", []):
        payload[key] = 1 if schema["properties"][key]["type"] == "integer" else "string"
    return payload


def document():
    paths = {
        "/api/agent/v1/tools": {"get": {"summary": "List authorized tools and JSON Schemas", "responses": {"200": {"description": "Authorized tools"}, "401": {"$ref": "#/components/responses/Error"}}}},
        "/api/agent/v1/media/upload": {"post": {"summary": "Upload a validated image", "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}, "product_id": {"type": "integer"}, "kind": {"type": "string", "enum": ["logo", "cover", "gallery", "mockup"]}, "alt_text": {"type": "string", "maxLength": 150}}}}}}, "responses": {"201": {"description": "Media created"}, "400": {"$ref": "#/components/responses/Error"}}}},
    }
    for collection, name in {"products": "list_products", "pages": "list_pages", "portfolio": "list_portfolio_items", "media": "list_media", "content": "list_content_sections", "activity": "get_agent_activity_logs"}.items():
        tool = TOOLS[name]
        paths[f"/api/agent/v1/{collection}"] = {"get": {"summary": tool.description, "parameters": [{"name": key, "in": "query", "schema": rule} for key, rule in tool.schema["properties"].items()], "responses": {"200": {"description": "Paginated result; unpaginated legacy calls include a Deprecation header"}, "400": {"$ref": "#/components/responses/Error"}, "401": {"$ref": "#/components/responses/Error"}}}}
    for endpoint, summary in (("token", "Issue a 15-minute access token and rotating refresh token"), ("rotate", "Rotate the long-lived agent credential"), ("revoke", "Revoke this agent connection")):
        paths[f"/api/agent/v1/auth/{endpoint}"] = {"post": {"summary": summary, "responses": {"200": {"description": "Authentication result"}, "401": {"$ref": "#/components/responses/Error"}}}}
    paths["/api/agent/v1/auth/refresh"] = {"post": {"summary": "Rotate a refresh token and issue a new access token", "security": [], "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": {"refresh_token": {"type": "string"}}, "required": ["refresh_token"]}}}}, "responses": {"200": {"description": "Rotated tokens"}, "401": {"$ref": "#/components/responses/Error"}}}}
    paths["/api/agent/v1/auth/me"] = {"get": {"summary": "Return active scopes and agent metadata", "responses": {"200": {"description": "Current agent"}, "401": {"$ref": "#/components/responses/Error"}}}}
    for name, tool in TOOLS.items():
        paths[f"/api/agent/v1/call/{name}"] = {"post": {"summary": tool.description, "description": f"Permission: `{tool.permission}`. Sensitive operations may require human approval.", "requestBody": {"required": True, "content": {"application/json": {"schema": tool.schema, "example": example_for(name, tool.schema)}}}, "responses": {"200": {"description": "Tool result or pending approval"}, "400": {"$ref": "#/components/responses/Error"}, "401": {"$ref": "#/components/responses/Error"}, "403": {"$ref": "#/components/responses/Error"}, "404": {"$ref": "#/components/responses/Error"}, "429": {"$ref": "#/components/responses/Error"}}}}
    return {"openapi": "3.1.0", "info": {"title": "HJF Website Manager Agent API", "version": "1.1.0", "description": "Secure website management through scoped bearer tokens. Sensitive changes can remain pending for administrator approval."}, "servers": [{"url": request.url_root.rstrip("/")}], "components": {"securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "hjf_..."}}, "responses": {"Error": {"description": "Structured error", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}}}, "schemas": {"Error": {"type": "object", "properties": {"ok": {"type": "boolean", "const": False}, "error": {"type": "object", "properties": {"code": {"type": "string"}, "message": {"type": "string"}, "message_en": {"type": "string"}, "details": {"type": "object"}, "request_id": {"type": "string"}}}}}}}, "security": [{"BearerAuth": []}], "paths": paths}
