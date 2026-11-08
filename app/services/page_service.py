"""Shared custom-page business rules used by admin, API and MCP."""
import re
import unicodedata
from urllib.parse import unquote
import bleach
from app.extensions import db
from app.models import CustomPage, PageRedirect
from app.services.utils import slugify

ALLOWED_TAGS = ["p", "br", "strong", "b", "em", "i", "ul", "ol", "li", "h2", "h3", "h4", "blockquote", "a", "code", "pre", "img", "figure", "figcaption", "table", "thead", "tbody", "tr", "th", "td", "hr", "section", "div", "span"]
ALLOWED_ATTRIBUTES = {"a": ["href", "title", "rel"], "img": ["src", "alt", "title", "loading"], "*": ["class"]}
RESERVED_PREFIXES = {"admin", "api", "static", "products", "product", "services", "portfolio", "about", "contact", "consultation", "custom-solution", "legal", "sitemap.xml", "robots.txt", "media", "uploads"}


class PageValidationError(ValueError):
    pass


def sanitize_page_html(value):
    return bleach.clean(value or "", tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, protocols=["http", "https", "mailto"], strip=True)


def normalize_page_path(value):
    value = unicodedata.normalize("NFKC", unquote((value or "").strip()))
    if any(char in value for char in ("\\", "?", "#", "\x00")) or ".." in value:
        raise PageValidationError("آدرس صفحه شامل نویسه یا مسیر غیرمجاز است.")
    parts = [slugify(part) for part in value.strip("/").split("/") if part.strip()]
    if not parts or any(not part for part in parts):
        raise PageValidationError("آدرس معتبر صفحه را وارد کنید.")
    if len(parts) > 5 or any(len(part) > 170 for part in parts):
        raise PageValidationError("عمق یا طول آدرس بیش از حد مجاز است.")
    path = "/".join(parts)
    if parts[0].lower() in RESERVED_PREFIXES:
        raise PageValidationError("این مسیر برای عملیات اصلی سایت رزرو شده است.")
    if not re.fullmatch(r"[\w\-\u0600-\u06FF/]+", path, re.UNICODE):
        raise PageValidationError("آدرس صفحه معتبر نیست.")
    return path[:500]


def page_dict(page):
    return {"id": page.id, "slug": page.slug, "url": "/" + page.slug, "title": page.title,
            "heading": page.heading, "subtitle": page.subtitle, "summary": page.summary,
            "html_content": page.html_content, "status": page.status,
            "published_at": page.published_at.isoformat() if page.published_at else None,
            "seo_title": page.seo_title, "seo_description": page.seo_description,
            "show_in_main": page.show_in_main, "show_in_hamburger": page.show_in_hamburger,
            "show_in_footer": page.show_in_footer, "menu_title": page.menu_title,
            "menu_order": page.menu_order, "menu_links_enabled": page.menu_links_enabled,
            "open_in_new_tab": page.open_in_new_tab,
            "created_at": page.created_at.isoformat(), "updated_at": page.updated_at.isoformat()}


def apply_page_data(page, data):
    new_slug = normalize_page_path(data.get("slug", page.slug))
    duplicate = CustomPage.query.filter(CustomPage.slug == new_slug, CustomPage.id != (page.id or 0)).first()
    if duplicate:
        raise PageValidationError("این آدرس قبلاً برای صفحه دیگری استفاده شده است.")
    redirect_collision = PageRedirect.query.filter_by(old_path=new_slug).first()
    if redirect_collision and redirect_collision.page_id != page.id:
        raise PageValidationError("این آدرس به مسیر دیگری Redirect می‌شود.")
    if page.id and page.slug != new_slug:
        # Reclaiming a former slug must remove its stale redirect, avoiding redirect loops.
        PageRedirect.query.filter_by(old_path=new_slug, page_id=page.id).delete(synchronize_session=False)
        old_redirect = PageRedirect.query.filter_by(old_path=page.slug).first()
        if not old_redirect:
            db.session.add(PageRedirect(old_path=page.slug, page=page))
    page.slug = new_slug
    for field in ("title", "heading", "subtitle", "summary", "seo_title", "seo_description", "menu_title"):
        if field in data:
            setattr(page, field, (data.get(field) or "").strip() or None)
    if not page.title or not page.heading:
        raise PageValidationError("عنوان و عنوان اصلی صفحه الزامی است.")
    if "html_content" in data:
        page.html_content = sanitize_page_html(data.get("html_content"))
    for field in ("show_in_main", "show_in_hamburger", "show_in_footer", "menu_links_enabled", "open_in_new_tab"):
        if field in data:
            setattr(page, field, bool(data.get(field)))
    if "menu_order" in data:
        try:
            page.menu_order = max(0, min(10000, int(data.get("menu_order") or 0)))
        except (TypeError, ValueError) as exc:
            raise PageValidationError("ترتیب منو باید عدد باشد.") from exc
    if "status" in data:
        set_page_status(page, data["status"])
    return page


def set_page_status(page, status):
    if status not in CustomPage.STATUSES:
        raise PageValidationError("وضعیت صفحه معتبر نیست.")
    if status == "published":
        page.publish()
    else:
        page.status = status
    return page
