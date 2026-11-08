"""Fine-grained agent tool registry shared by REST and the official MCP server.
No raw SQL, shell, arbitrary file access or arbitrary code execution is exposed.
"""
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash, generate_password_hash
from app.extensions import db
from app.models import (AgentActivity, AgentApproval, AgentConnection, Category, CustomPage, FAQ,
                        Lead, MenuItem, PageContent, Portfolio, Product, ProductMedia, SiteSetting)
from app.services.page_service import PageValidationError, apply_page_data, normalize_page_path, page_dict, sanitize_page_html, set_page_status

PERMISSIONS = {
    "products.read": "مشاهده محصولات", "products.create": "ایجاد محصول", "products.update": "ویرایش/بایگانی محصول",
    "products.delete": "حذف محصول", "categories.manage": "مدیریت دسته‌بندی‌ها",
    "pages.read": "مشاهده صفحات", "pages.create": "ایجاد پیش‌نویس صفحه", "pages.update": "ویرایش/بایگانی صفحه",
    "pages.publish": "انتشار و لغو انتشار صفحه", "menus.read": "مشاهده منوها", "menus.manage": "مدیریت منوها",
    "portfolio.read": "مشاهده نمونه‌کارها", "portfolio.create": "ایجاد نمونه‌کار", "portfolio.update": "ویرایش/بایگانی نمونه‌کار",
    "content.read": "مشاهده محتوای سایت", "content.manage": "ویرایش محتوای سایت",
    "media.read": "مشاهده رسانه‌ها", "media.delete": "حذف رسانه", "settings.read": "مشاهده تنظیمات عمومی",
    "reports.read": "گزارش و آمار", "logs.read": "مشاهده رخدادهای خود ایجنت",
}

@dataclass(frozen=True)
class Tool:
    permission: str
    operation: str
    description: str
    schema: dict
    sensitive: bool = False


def schema(properties=None, required=None):
    return {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False}

S = {"type": "string"}; I = {"type": "integer"}; B = {"type": "boolean"}
TOOLS = {
    "list_products": Tool("products.read", "read", "List products with status and category.", schema({"status": S, "search": S})),
    "get_product": Tool("products.read", "read", "Get one product by numeric ID.", schema({"product_id": I}, ["product_id"])),
    "create_product": Tool("products.create", "create", "Create a draft product; publishing is never implied.", schema({"name": S, "short_description": S, "slug": S, "tagline": S, "medium_description": S, "full_description": S}, ["name", "short_description"])),
    "update_product": Tool("products.update", "update", "Update product copy or publication state under the approval policy.", schema({"product_id": I, "name": S, "short_description": S, "tagline": S, "medium_description": S, "full_description": S, "status": S}, ["product_id"]), sensitive=True),
    "archive_product": Tool("products.update", "update", "Archive a product without deleting it.", schema({"product_id": I}, ["product_id"]), sensitive=True),
    "delete_product": Tool("products.delete", "delete", "Permanently delete a product after required human approval.", schema({"product_id": I}, ["product_id"]), sensitive=True),
    "get_product_categories": Tool("products.read", "read", "List product categories.", schema()),
    "create_product_category": Tool("categories.manage", "create", "Create a product category.", schema({"name": S, "slug": S, "description": S}, ["name"])),
    "update_product_category": Tool("categories.manage", "update", "Update a product category.", schema({"category_id": I, "name": S, "description": S, "is_visible": B}, ["category_id"])),
    "list_pages": Tool("pages.read", "read", "List custom pages and publication state.", schema({"status": S})),
    "get_page": Tool("pages.read", "read", "Get a custom page.", schema({"page_id": I}, ["page_id"])),
    "create_page": Tool("pages.create", "create", "Create and sanitize a draft custom page.", schema({"slug": S, "title": S, "heading": S, "subtitle": S, "summary": S, "html_content": S, "seo_title": S, "seo_description": S, "show_in_main": B, "show_in_hamburger": B, "show_in_footer": B, "menu_title": S, "menu_order": I}, ["slug", "title", "heading"])),
    "update_page": Tool("pages.update", "update", "Update and sanitize a custom page; old slug receives a 301 redirect.", schema({"page_id": I, "slug": S, "title": S, "heading": S, "subtitle": S, "summary": S, "html_content": S, "seo_title": S, "seo_description": S, "show_in_main": B, "show_in_hamburger": B, "show_in_footer": B, "menu_title": S, "menu_order": I}, ["page_id"])),
    "preview_page": Tool("pages.read", "read", "Return the private admin preview path for a page.", schema({"page_id": I}, ["page_id"])),
    "publish_page": Tool("pages.publish", "publish", "Publish a page publicly; may require administrator approval.", schema({"page_id": I}, ["page_id"]), True),
    "unpublish_page": Tool("pages.publish", "publish", "Remove a page from public access under the approval policy.", schema({"page_id": I}, ["page_id"]), True),
    "archive_page": Tool("pages.update", "update", "Archive a custom page under the approval policy.", schema({"page_id": I}, ["page_id"]), True),
    "get_page_public_url": Tool("pages.read", "read", "Return the canonical public path of a page.", schema({"page_id": I}, ["page_id"])),
    "list_menus": Tool("menus.read", "read", "List navigation items.", schema({"location": S})),
    "get_menu": Tool("menus.read", "read", "Get one menu item.", schema({"menu_id": I}, ["menu_id"])),
    "add_menu_item": Tool("menus.manage", "create", "Add an internal, page or HTTPS external navigation link.", schema({"title": S, "location": S, "page_id": I, "internal_url": S, "external_url": S, "parent_id": I, "position": I, "open_in_new_tab": B}, ["title", "location"])),
    "update_menu_item": Tool("menus.manage", "update", "Update a navigation item.", schema({"menu_id": I, "title": S, "position": I, "is_enabled": B, "open_in_new_tab": B}, ["menu_id"])),
    "remove_menu_item": Tool("menus.manage", "delete", "Remove a navigation item and its children.", schema({"menu_id": I}, ["menu_id"]), True),
    "reorder_menu_items": Tool("menus.manage", "update", "Set the position of a menu item.", schema({"menu_id": I, "position": I}, ["menu_id", "position"])),
    "list_portfolio_items": Tool("portfolio.read", "read", "List portfolio records.", schema()),
    "get_portfolio_item": Tool("portfolio.read", "read", "Get a portfolio record.", schema({"portfolio_id": I}, ["portfolio_id"])),
    "create_portfolio_item": Tool("portfolio.create", "create", "Create an unpublished portfolio record without fabricated media.", schema({"title": S, "summary": S, "description": S}, ["title"])),
    "update_portfolio_item": Tool("portfolio.update", "update", "Update portfolio copy or publication state under the approval policy.", schema({"portfolio_id": I, "title": S, "summary": S, "description": S, "is_published": B}, ["portfolio_id"]), True),
    "archive_portfolio_item": Tool("portfolio.update", "update", "Remove a portfolio item from public lists under the approval policy.", schema({"portfolio_id": I}, ["portfolio_id"]), True),
    "get_site_content": Tool("content.read", "read", "Get one editable content section.", schema({"content_id": I}, ["content_id"])),
    "list_content_sections": Tool("content.read", "read", "List editable fixed-page content sections.", schema({"page_key": S})),
    "update_site_content": Tool("content.manage", "update", "Alias for update_content_section.", schema({"content_id": I, "title": S, "subtitle": S, "body": S}, ["content_id"])),
    "update_content_section": Tool("content.manage", "update", "Update sanitized HTML for a fixed-page content section.", schema({"content_id": I, "title": S, "subtitle": S, "body": S}, ["content_id"])),
    "list_media": Tool("media.read", "read", "List product media metadata, never server file contents.", schema()),
    "get_media_details": Tool("media.read", "read", "Get media metadata.", schema({"media_id": I}, ["media_id"])),
    "delete_media": Tool("media.delete", "delete", "Delete a media record and its managed upload after approval policy.", schema({"media_id": I}, ["media_id"]), True),
    "get_site_overview": Tool("reports.read", "read", "Get public branding and safe site overview.", schema()),
    "get_site_statistics": Tool("reports.read", "read", "Get record counts without private contact contents.", schema()),
    "get_published_pages": Tool("pages.read", "read", "List only published custom pages.", schema()),
    "get_draft_pages": Tool("pages.read", "read", "List draft custom pages.", schema()),
    "get_product_statistics": Tool("reports.read", "read", "Get product counts grouped by status.", schema()),
    "get_recent_changes": Tool("logs.read", "read", "Get this agent's recent activity.", schema({"limit": I})),
    "get_agent_activity_logs": Tool("logs.read", "read", "Get this agent's audit events.", schema({"limit": I, "status": S})),
}

class AgentToolError(ValueError):
    def __init__(self, message, code="tool_error"):
        super().__init__(message)
        self.code = code


def issue_token(agent):
    prefix = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    agent.token_prefix = prefix
    agent.token_hash = generate_password_hash(secret)
    return f"hjf_{prefix}.{secret}"


def authenticate_token(token):
    if not token or not token.startswith("hjf_") or "." not in token:
        return None
    prefix, secret = token[4:].split(".", 1)
    agent = AgentConnection.query.filter_by(token_prefix=prefix).first()
    if not agent or not agent.is_active or not check_password_hash(agent.token_hash, secret):
        return None
    since = datetime.utcnow() - timedelta(minutes=1)
    recent = AgentActivity.query.filter(AgentActivity.agent_id == agent.id, AgentActivity.created_at >= since).count()
    if recent >= agent.rate_limit_per_minute:
        raise AgentToolError("سقف درخواست این ایجنت در یک دقیقه تکمیل شده است.", "rate_limited")
    agent.last_used_at = datetime.utcnow()
    db.session.add(AgentActivity(agent=agent, tool_name="http.request", operation="read", status="received", result_summary="Authenticated transport request"))
    db.session.commit()
    return agent


def _validate(tool, payload):
    if not isinstance(payload, dict):
        raise AgentToolError("ورودی ابزار باید Object باشد.", "invalid_input")
    properties = tool.schema["properties"]
    unknown = set(payload) - set(properties)
    if unknown:
        raise AgentToolError("پارامترهای ناشناخته: " + ", ".join(sorted(unknown)), "invalid_input")
    missing = [key for key in tool.schema["required"] if key not in payload]
    if missing:
        raise AgentToolError("پارامترهای الزامی: " + ", ".join(missing), "invalid_input")
    for key, value in payload.items():
        expected = properties[key]["type"]
        if expected == "integer" and (type(value) is not int):
            raise AgentToolError(f"{key} باید عدد صحیح باشد.", "invalid_input")
        if expected == "string" and not isinstance(value, str):
            raise AgentToolError(f"{key} باید متن باشد.", "invalid_input")
        if expected == "boolean" and type(value) is not bool:
            raise AgentToolError(f"{key} باید Boolean باشد.", "invalid_input")
        if isinstance(value, str) and len(value) > 50000:
            raise AgentToolError(f"طول {key} بیش از حد مجاز است.", "invalid_input")
    return payload


def product_dict(item):
    return {"id": item.id, "name": item.name, "slug": item.slug, "status": item.status,
            "tagline": item.tagline, "short_description": item.short_description,
            "medium_description": item.medium_description, "full_description": item.full_description,
            "category_id": item.category_id, "commercial_status": item.commercial_status}


def portfolio_dict(item):
    return {"id": item.id, "title": item.title, "slug": item.slug, "summary": item.summary,
            "description": item.description, "is_published": item.is_published}


def menu_dict(item):
    return {"id": item.id, "title": item.title, "location": item.location, "href": item.href,
            "page_id": item.page_id, "parent_id": item.parent_id, "position": item.position,
            "is_enabled": item.is_enabled, "open_in_new_tab": item.open_in_new_tab}


def media_dict(item):
    return {"id": item.id, "product_id": item.product_id, "title": item.title, "media_type": item.media_type,
            "url": "/" + item.file_path if not item.file_path.startswith("static/") else "/" + item.file_path,
            "description": item.description, "is_mockup": item.is_mockup, "is_published": item.is_published}


def _get(model, key, payload):
    item = db.session.get(model, payload[key])
    if not item:
        raise AgentToolError("رکورد موردنظر پیدا نشد.", "not_found")
    return item


def _apply_menu(item, payload):
    for field in ("title", "location", "internal_url", "external_url", "open_in_new_tab", "is_enabled"):
        if field in payload:
            setattr(item, field, payload[field])
    if "page_id" in payload:
        item.page = _get(CustomPage, "page_id", payload) if payload["page_id"] else None
    if "parent_id" in payload:
        item.parent = _get(MenuItem, "parent_id", payload) if payload["parent_id"] else None
    if "position" in payload:
        item.position = max(0, min(10000, payload["position"]))
    if not item.title or item.location not in MenuItem.LOCATIONS:
        raise AgentToolError("عنوان یا محل منو معتبر نیست.", "invalid_input")
    if not (item.page or item.internal_url or item.external_url):
        raise AgentToolError("یک صفحه، لینک داخلی یا لینک خارجی لازم است.", "invalid_input")
    if item.parent and item.parent.location != item.location:
        raise AgentToolError("والد و زیرمنو باید در یک محل نمایش باشند.", "invalid_input")
    if item.external_url and not item.external_url.startswith(("https://", "http://")):
        raise AgentToolError("لینک خارجی باید HTTP یا HTTPS باشد.", "invalid_input")
    if item.internal_url and (not item.internal_url.startswith("/") or item.internal_url.startswith("//")):
        raise AgentToolError("لینک داخلی باید با / شروع شود.", "invalid_input")
    ancestor = item.parent
    visited = set()
    while ancestor:
        if ancestor.id == item.id or ancestor.id in visited:
            raise AgentToolError("ارتباط والد و زیرمنو نباید چرخه ایجاد کند.", "invalid_input")
        if ancestor.id:
            visited.add(ancestor.id)
        ancestor = ancestor.parent


apply_menu_data = _apply_menu


def perform(name, p):
    if name == "list_products":
        query = Product.query
        if p.get("status"): query = query.filter_by(status=p["status"])
        if p.get("search"): query = query.filter(Product.name.ilike("%" + p["search"][:120] + "%"))
        return [product_dict(x) for x in query.order_by(Product.position).limit(200).all()]
    if name == "get_product": return product_dict(_get(Product, "product_id", p))
    if name == "delete_product":
        item = _get(Product, "product_id", p)
        result = {"deleted": True, "product_id": item.id}
        db.session.delete(item)
        return result
    if name == "create_product":
        from app.services.utils import slugify
        item = Product(name=p["name"].strip(), short_description=p["short_description"].strip(), slug=slugify(p.get("slug") or p["name"]), status="draft", origin_type="independent", commercial_status="development")
        if not item.slug or Product.query.filter_by(slug=item.slug).first(): raise AgentToolError("نامک محصول خالی یا تکراری است.", "invalid_input")
        for field in ("tagline", "medium_description", "full_description"):
            if field in p: setattr(item, field, p[field])
        db.session.add(item); db.session.flush(); return product_dict(item)
    if name in ("update_product", "archive_product"):
        item = _get(Product, "product_id", p); before = product_dict(item)
        if name == "archive_product": item.status = "archived"
        else:
            for field in ("name", "short_description", "tagline", "medium_description", "full_description"):
                if field in p: setattr(item, field, p[field])
            if p.get("status"):
                if p["status"] not in Product.STATUSES: raise AgentToolError("وضعیت محصول معتبر نیست.", "invalid_input")
                item.status = p["status"]
        result = product_dict(item); result["_before"] = before; return result
    if name in ("get_product_categories",):
        return [{"id": x.id, "name": x.name, "slug": x.slug, "description": x.description, "is_visible": x.is_visible} for x in Category.query.order_by(Category.position).all()]
    if name == "create_product_category":
        from app.services.utils import slugify
        slug = slugify(p.get("slug") or p["name"])
        if not slug or Category.query.filter_by(slug=slug).first(): raise AgentToolError("نامک دسته خالی یا تکراری است.", "invalid_input")
        item = Category(name=p["name"].strip(), slug=slug, description=p.get("description")); db.session.add(item); db.session.flush()
        return {"id": item.id, "name": item.name, "slug": item.slug}
    if name == "update_product_category":
        item = _get(Category, "category_id", p)
        for field in ("name", "description", "is_visible"):
            if field in p: setattr(item, field, p[field])
        return {"id": item.id, "name": item.name, "description": item.description, "is_visible": item.is_visible}
    if name in ("list_pages", "get_published_pages", "get_draft_pages"):
        status = "published" if name == "get_published_pages" else "draft" if name == "get_draft_pages" else p.get("status")
        query = CustomPage.query
        if status: query = query.filter_by(status=status)
        return [page_dict(x) for x in query.order_by(CustomPage.updated_at.desc()).limit(200).all()]
    if name in ("get_page", "preview_page", "get_page_public_url"):
        item = _get(CustomPage, "page_id", p)
        if name == "preview_page": return {"page_id": item.id, "private_preview_path": f"/admin/pages/{item.id}/preview", "authentication": "administrator session required"}
        if name == "get_page_public_url": return {"page_id": item.id, "path": "/" + item.slug, "public": item.is_public}
        return page_dict(item)
    if name == "create_page":
        item = CustomPage(status="draft"); apply_page_data(item, p); item.status = "draft"; db.session.add(item); db.session.flush(); return page_dict(item)
    if name in ("update_page", "publish_page", "unpublish_page", "archive_page"):
        item = _get(CustomPage, "page_id", p); before = page_dict(item)
        if name == "update_page": apply_page_data(item, p)
        elif name == "publish_page": set_page_status(item, "published")
        elif name == "unpublish_page": set_page_status(item, "unpublished")
        else: set_page_status(item, "archived")
        result = page_dict(item); result["_before"] = before; return result
    if name == "list_menus":
        query = MenuItem.query
        if p.get("location"): query = query.filter_by(location=p["location"])
        return [menu_dict(x) for x in query.order_by(MenuItem.location, MenuItem.position).all()]
    if name == "get_menu": return menu_dict(_get(MenuItem, "menu_id", p))
    if name == "add_menu_item":
        item = MenuItem(); _apply_menu(item, p); db.session.add(item); db.session.flush(); return menu_dict(item)
    if name in ("update_menu_item", "reorder_menu_items"):
        item = _get(MenuItem, "menu_id", p); _apply_menu(item, p); return menu_dict(item)
    if name == "remove_menu_item":
        item = _get(MenuItem, "menu_id", p); db.session.delete(item); return {"deleted": True, "menu_id": p["menu_id"]}
    if name == "list_portfolio_items": return [portfolio_dict(x) for x in Portfolio.query.order_by(Portfolio.position).limit(200).all()]
    if name == "get_portfolio_item": return portfolio_dict(_get(Portfolio, "portfolio_id", p))
    if name == "create_portfolio_item":
        from app.services.utils import slugify
        slug = slugify(p["title"])
        if Portfolio.query.filter_by(slug=slug).first(): raise AgentToolError("عنوان نمونه‌کار تکراری است.", "invalid_input")
        item = Portfolio(title=p["title"].strip(), slug=slug, summary=p.get("summary"), description=p.get("description"), is_published=False); db.session.add(item); db.session.flush(); return portfolio_dict(item)
    if name in ("update_portfolio_item", "archive_portfolio_item"):
        item = _get(Portfolio, "portfolio_id", p)
        if name == "archive_portfolio_item": item.is_published = False; item.show_in_gallery = False
        else:
            for field in ("title", "summary", "description", "is_published"):
                if field in p: setattr(item, field, p[field])
        return portfolio_dict(item)
    if name == "list_content_sections":
        query = PageContent.query
        if p.get("page_key"): query = query.filter_by(page_key=p["page_key"])
        return [{"id": x.id, "page_key": x.page_key, "section_key": x.section_key, "title": x.title, "subtitle": x.subtitle, "body": x.body, "is_published": x.is_published} for x in query.order_by(PageContent.page_key, PageContent.position).all()]
    if name in ("get_site_content", "update_site_content", "update_content_section"):
        item = _get(PageContent, "content_id", p)
        if name == "get_site_content": return {"id": item.id, "title": item.title, "subtitle": item.subtitle, "body": item.body}
        before = {"title": item.title, "subtitle": item.subtitle, "body": item.body}
        for field in ("title", "subtitle", "body"):
            if field in p: setattr(item, field, sanitize_page_html(p[field]) if field == "body" else p[field])
        return {"id": item.id, "title": item.title, "subtitle": item.subtitle, "body": item.body, "_before": before}
    if name == "list_media": return [media_dict(x) for x in ProductMedia.query.order_by(ProductMedia.created_at.desc()).limit(200).all()]
    if name == "get_media_details": return media_dict(_get(ProductMedia, "media_id", p))
    if name == "delete_media":
        item = _get(ProductMedia, "media_id", p); media_id = item.id
        from app.services.media_service import delete_upload
        delete_upload(item.file_path); delete_upload(item.thumbnail_path); db.session.delete(item); return {"deleted": True, "media_id": media_id}
    if name == "get_site_overview":
        return {"brand": {x.key: x.value for x in SiteSetting.query.filter(SiteSetting.key.in_(["brand_name", "brand_tagline", "brand_description", "website_url"])).all()}, "published_products": Product.query.filter_by(status="published").count(), "published_pages": CustomPage.query.filter_by(status="published").count()}
    if name in ("get_site_statistics", "get_product_statistics"):
        data = {"products": Product.query.count(), "pages": CustomPage.query.count(), "portfolio": Portfolio.query.count(), "media": ProductMedia.query.count()}
        if name == "get_product_statistics": return {status: Product.query.filter_by(status=status).count() for status in Product.STATUSES}
        data["new_leads_count"] = Lead.query.filter_by(status="new").count(); return data
    if name in ("get_recent_changes", "get_agent_activity_logs"):
        return []
    raise AgentToolError("ابزار پیدا نشد.", "not_found")


def execute_tool(agent, name, payload, approved_by=None, skip_approval=False):
    if not agent.is_active:
        raise AgentToolError("اتصال ایجنت غیرفعال، لغوشده یا منقضی است.", "permission_denied")
    tool = TOOLS.get(name)
    if not tool:
        raise AgentToolError("ابزار ناشناخته است.", "not_found")
    if tool.permission not in (agent.permissions or []):
        activity = AgentActivity(agent=agent, tool_name=name, operation=tool.operation, status="denied", error_message="مجوز ابزار فعال نیست")
        db.session.add(activity); db.session.commit()
        raise AgentToolError("این ایجنت مجوز استفاده از ابزار را ندارد.", "permission_denied")
    _validate(tool, payload)
    if tool.sensitive and agent.require_approval_for_sensitive and not skip_approval:
        target = ", ".join(f"{key}={payload[key]}" for key in ("page_id", "product_id", "media_id", "menu_id", "portfolio_id", "slug") if key in payload)
        approval = AgentApproval(agent=agent, tool_name=name, payload=payload, summary=f"{name} — {target or 'content operation'}")
        db.session.add(approval)
        db.session.flush()
        db.session.add(AgentActivity(agent=agent, tool_name=name, operation=tool.operation, status="pending", result_summary=f"approval_id={approval.id}"))
        db.session.commit()
        return {"pending_approval": True, "approval_id": approval.id, "status": "pending", "message": "عملیات پس از تأیید مدیر انجام می‌شود."}
    activity = AgentActivity(agent=agent, tool_name=name, operation=tool.operation, approved_by=approved_by, status="running")
    db.session.add(activity)
    try:
        result = execute_logs(agent, name, payload) if name in ("get_recent_changes", "get_agent_activity_logs") else perform(name, payload)
        before = result.pop("_before", None) if isinstance(result, dict) else None
        activity.before_data = before
        activity.after_data = result if isinstance(result, dict) else None
        activity.status = "success"
        activity.result_summary = str({key: result[key] for key in ("id", "status", "deleted", "product_id", "page_id", "media_id") if key in result})[:500] if isinstance(result, dict) else f"{len(result)} records"
        if isinstance(result, dict) and result.get("id"):
            activity.entity_type = name.split("_")[-1]
            activity.entity_id = str(result["id"])
        db.session.commit()
        return {"ok": True, "tool": name, "result": result}
    except (PageValidationError, AgentToolError) as exc:
        db.session.rollback()
        activity = AgentActivity(agent=agent, tool_name=name, operation=tool.operation, status="error", error_message=str(exc)[:500])
        db.session.add(activity); db.session.commit()
        raise AgentToolError(str(exc), getattr(exc, "code", "validation_error")) from exc
    except Exception as exc:
        db.session.rollback()
        activity = AgentActivity(agent=agent, tool_name=name, operation=tool.operation, status="error", error_message="اجرای امن ابزار ناموفق بود")
        db.session.add(activity); db.session.commit()
        raise AgentToolError("اجرای ابزار ناموفق بود.", "execution_error") from exc


def execute_logs(agent, name, payload):
    query = AgentActivity.query.filter_by(agent_id=agent.id)
    if payload.get("status"): query = query.filter_by(status=payload["status"])
    limit = min(100, max(1, payload.get("limit", 30)))
    return [{"id": x.id, "tool": x.tool_name, "operation": x.operation, "status": x.status,
             "entity_type": x.entity_type, "entity_id": x.entity_id, "result": x.result_summary,
             "error": x.error_message, "created_at": x.created_at.isoformat()} for x in query.order_by(AgentActivity.id.desc()).limit(limit).all()]
