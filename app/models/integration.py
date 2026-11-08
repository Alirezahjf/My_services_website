"""Product modules and explicit platform capability/connection state."""
from app.extensions import db
from .base import TimestampMixin


class PlatformConnector(TimestampMixin, db.Model):
    __tablename__ = "platform_connectors"
    CAPABILITY_STATUSES = ("implemented", "development", "planned", "api_required", "platform_approval", "review", "unsupported")
    CONNECTION_STATUSES = ("not_connected", "configuration_required", "connected", "error", "disabled")

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = db.Column(db.String(80), nullable=False, index=True)
    display_name = db.Column(db.String(120), nullable=False)
    adapter_key = db.Column(db.String(120))
    auth_method = db.Column(db.String(160))
    connection_status = db.Column(db.String(50), default="not_connected", nullable=False)
    capability_status = db.Column(db.String(50), default="planned", nullable=False)
    api_required = db.Column(db.Boolean, default=True, nullable=False)
    approval_required = db.Column(db.Boolean, default=False, nullable=False)
    supported_features = db.Column(db.JSON, default=list)
    limitations = db.Column(db.JSON, default=list)
    is_enabled = db.Column(db.Boolean, default=False, nullable=False)
    position = db.Column(db.Integer, default=0)
    last_checked_at = db.Column(db.DateTime)
    product = db.relationship("Product", back_populates="connectors")
    __table_args__ = (db.UniqueConstraint("product_id", "platform", name="uq_product_platform_connector"),)


class ProductModule(TimestampMixin, db.Model):
    __tablename__ = "product_modules"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(50), default="planned", nullable=False)
    position = db.Column(db.Integer, default=0)
    product = db.relationship("Product", back_populates="modules")
