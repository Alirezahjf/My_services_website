"""Database-backed custom pages, redirects, and navigation."""
from datetime import datetime, timezone
from app.extensions import db
from .base import TimestampMixin


class CustomPage(TimestampMixin, db.Model):
    __tablename__ = "custom_pages"
    STATUSES = ("draft", "published", "unpublished", "archived")
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(500), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    heading = db.Column(db.String(240), nullable=False)
    subtitle = db.Column(db.String(500))
    summary = db.Column(db.Text)
    html_content = db.Column(db.Text, default="")
    css_content = db.Column(db.Text, default="")
    js_content = db.Column(db.Text, default="")
    parent_content_id = db.Column(db.Integer, db.ForeignKey("page_contents.id", ondelete="SET NULL"), index=True)
    parent_content = db.relationship("PageContent", backref=db.backref("custom_pages", lazy="dynamic"))
    status = db.Column(db.String(30), default="draft", nullable=False, index=True)
    published_at = db.Column(db.DateTime)
    seo_title = db.Column(db.String(180))
    seo_description = db.Column(db.String(320))
    show_in_main = db.Column(db.Boolean, default=False, nullable=False)
    show_in_hamburger = db.Column(db.Boolean, default=False, nullable=False)
    show_in_footer = db.Column(db.Boolean, default=False, nullable=False)
    menu_title = db.Column(db.String(120))
    menu_order = db.Column(db.Integer, default=0)
    menu_links_enabled = db.Column(db.Boolean, default=True, nullable=False)
    open_in_new_tab = db.Column(db.Boolean, default=False, nullable=False)

    @property
    def is_public(self):
        return self.status == "published"

    def publish(self):
        self.status = "published"
        self.published_at = datetime.now(timezone.utc).replace(tzinfo=None)


class PageRedirect(TimestampMixin, db.Model):
    __tablename__ = "page_redirects"
    id = db.Column(db.Integer, primary_key=True)
    old_path = db.Column(db.String(500), unique=True, nullable=False, index=True)
    page_id = db.Column(db.Integer, db.ForeignKey("custom_pages.id", ondelete="CASCADE"), nullable=False)
    page = db.relationship("CustomPage", backref=db.backref("redirects", cascade="all, delete-orphan"))


class MenuItem(TimestampMixin, db.Model):
    __tablename__ = "menu_items"
    LOCATIONS = ("main", "hamburger", "footer")
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(30), nullable=False, index=True)
    page_id = db.Column(db.Integer, db.ForeignKey("custom_pages.id", ondelete="CASCADE"))
    internal_url = db.Column(db.String(500))
    external_url = db.Column(db.String(500))
    parent_id = db.Column(db.Integer, db.ForeignKey("menu_items.id", ondelete="CASCADE"))
    position = db.Column(db.Integer, default=0, nullable=False)
    is_enabled = db.Column(db.Boolean, default=True, nullable=False)
    open_in_new_tab = db.Column(db.Boolean, default=False, nullable=False)
    page = db.relationship("CustomPage")
    parent = db.relationship("MenuItem", remote_side=[id], backref=db.backref("children", cascade="all, delete-orphan"))

    @property
    def href(self):
        if self.page:
            return "/" + self.page.slug
        return self.internal_url or self.external_url or "#"

    @property
    def is_visible(self):
        return self.is_enabled and (not self.page or self.page.status == "published")
