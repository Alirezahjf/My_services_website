"""Central validation, output shaping and safe text handling for agent integrations."""
import base64
import json
import re
from datetime import datetime
import bleach
from flask import g

AGENT_HTML_TAGS = ["p", "br", "strong", "em", "ul", "ol", "li", "a", "h2", "h3", "blockquote"]
DANGEROUS_TEXT = re.compile(r"<\s*(?:script|style|iframe|svg)\b|javascript\s*:|\bon(?:error|load|click)\s*=", re.I)
RISKY_JS = re.compile(r"\beval\s*\(|\bnew\s+Function\b|\.innerHTML\s*=|document\.write\s*\(", re.I)
LIST_PARAMS = {
    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    "offset": {"type": "integer", "minimum": 0},
    "cursor": {"type": "string"},
    "sort": {"type": "string", "enum": ["id", "created_at", "updated_at", "name"]},
    "order": {"type": "string", "enum": ["asc", "desc"]},
}


def clean_plain(value, field="field"):
    if not isinstance(value, str):
        return value
    if DANGEROUS_TEXT.search(value):
        from app.services.agent_service import AgentToolError
        raise AgentToolError(f"محتوای خطرناک در {field} مجاز نیست.", "invalid_input")
    return bleach.clean(value, tags=[], attributes={}, strip=True).strip()


def clean_agent_html(value):
    return bleach.clean(value or "", tags=AGENT_HTML_TAGS, attributes={"a": ["href", "title", "rel"]}, protocols=["https", "mailto"], strip=True)


def validate_custom_js(value):
    if value and RISKY_JS.search(value):
        from app.services.agent_service import AgentToolError
        raise AgentToolError("JavaScript شامل الگوی پرخطر eval، Function، innerHTML یا document.write است.", "risky_js")
    return value or ""


def decode_cursor(value):
    if not value:
        return 0
    try:
        data = json.loads(base64.urlsafe_b64decode(value.encode() + b"==" ).decode())
        return max(0, int(data["offset"]))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        from app.services.agent_service import AgentToolError
        raise AgentToolError("Cursor صفحه‌بندی معتبر نیست.", "invalid_input")


def encode_cursor(offset):
    return base64.urlsafe_b64encode(json.dumps({"offset": offset}, separators=(",", ":")).encode()).decode().rstrip("=")


def paginate(query, payload, model, serializer, default_sort="id", allowed_filters=None):
    """Keep legacy list responses unless limit/cursor/offset is explicitly supplied."""
    paginated = any(key in payload for key in ("limit", "cursor", "offset"))
    sort = payload.get("sort", default_sort)
    if sort == "name" and not hasattr(model, "name"):
        sort = "title" if hasattr(model, "title") else "id"
    if sort not in {"id", "created_at", "updated_at", "name", "title"} or not hasattr(model, sort):
        from app.services.agent_service import AgentToolError
        raise AgentToolError("ستون مرتب‌سازی معتبر نیست.", "invalid_input")
    column = getattr(model, sort)
    query = query.order_by(column.asc() if payload.get("order", "desc") == "asc" else column.desc(), model.id.desc())
    if not paginated:
        g.agent_legacy_list = True
        return [serializer(item) for item in query.limit(200).all()]
    limit = payload.get("limit", 20)
    if type(limit) is not int or not 1 <= limit <= 100:
        from app.services.agent_service import AgentToolError
        raise AgentToolError("limit باید بین ۱ تا ۱۰۰ باشد.", "invalid_input")
    offset = decode_cursor(payload.get("cursor")) if payload.get("cursor") else payload.get("offset", 0)
    if type(offset) is not int or offset < 0:
        from app.services.agent_service import AgentToolError
        raise AgentToolError("offset نامعتبر است.", "invalid_input")
    total = query.order_by(None).count()
    rows = query.offset(offset).limit(limit + 1).all()
    has_more = len(rows) > limit
    return {"data": [serializer(item) for item in rows[:limit]], "pagination": {
        "total": total, "limit": limit, "offset": offset, "has_more": has_more,
        "next_cursor": encode_cursor(offset + limit) if has_more else None,
    }}


def parse_iso(value, field):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        from app.services.agent_service import AgentToolError
        raise AgentToolError(f"{field} باید ISO8601 باشد.", "invalid_input")
