from app.extensions import db
from .base import TimestampMixin


class ContactMessage(TimestampMixin, db.Model):
    __tablename__ = "contact_messages"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(40), nullable=False, index=True)
    email = db.Column(db.String(180))
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(40), default="new", nullable=False, index=True)
    admin_note = db.Column(db.Text)
    ip_hash = db.Column(db.String(64))


class Lead(TimestampMixin, db.Model):
    __tablename__ = "leads"
    STATUSES = ("new", "reviewing", "call_needed", "negotiation", "completed", "archived")
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    organization = db.Column(db.String(180))
    phone = db.Column(db.String(40), nullable=False, index=True)
    email = db.Column(db.String(180))
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"), index=True)
    request_type = db.Column(db.String(100), default="consultation", index=True)
    subject = db.Column(db.String(200))
    industry = db.Column(db.String(160))
    need_type = db.Column(db.String(160))
    message = db.Column(db.Text)
    budget = db.Column(db.String(100))
    attachment_path = db.Column(db.String(255))
    status = db.Column(db.String(40), default="new", nullable=False, index=True)
    admin_note = db.Column(db.Text)
    ip_hash = db.Column(db.String(64))
    product = db.relationship("Product")
