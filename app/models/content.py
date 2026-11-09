from app.extensions import db
from .base import TimestampMixin


class FAQ(TimestampMixin, db.Model):
    __tablename__ = "faqs"
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(300), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), index=True)
    is_published = db.Column(db.Boolean, default=True, nullable=False)
    position = db.Column(db.Integer, default=0)
    product = db.relationship("Product", back_populates="faqs")


class SiteSetting(TimestampMixin, db.Model):
    __tablename__ = "site_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    group_name = db.Column(db.String(80), default="general", index=True)
    value_type = db.Column(db.String(20), default="text")

    @staticmethod
    def get(key, default=""):
        item = db.session.execute(db.select(SiteSetting).filter_by(key=key)).scalar_one_or_none()
        return item.value if item and item.value is not None else default


class PageContent(TimestampMixin, db.Model):
    __tablename__ = "page_contents"
    id = db.Column(db.Integer, primary_key=True)
    page_key = db.Column(db.String(100), nullable=False, index=True)
    section_key = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(240))
    subtitle = db.Column(db.String(300))
    body = db.Column(db.Text)
    extra = db.Column(db.JSON, default=dict)
    is_published = db.Column(db.Boolean, default=True)
    position = db.Column(db.Integer, default=0)
    __table_args__ = (db.UniqueConstraint("page_key", "section_key", name="uq_page_section"),)


class WorkflowStep(TimestampMixin, db.Model):
    __tablename__ = "workflow_steps"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(80), default="arrow")
    position = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True)


class Service(TimestampMixin, db.Model):
    __tablename__ = "services"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(80), default="workflow")
    position = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True)


class SocialLink(TimestampMixin, db.Model):
    __tablename__ = "social_links"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    icon = db.Column(db.String(80), default="link")
    position = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True)
