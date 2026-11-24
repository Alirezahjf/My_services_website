"""The accounts of the visitors of the site.

The administrator of the site is one person who writes the content. A
visitor is another matter: the visitor may want to try a sample of a
product before asking for a price, and that sample is only given to a
visitor whose name is known.

The two are kept apart. The administrator signs in at ``/admin/login``
and reaches the panel; the visitor signs in at ``/account/login`` and
reaches the samples. A visitor never sees the panel, and the
administrator never blocks a visitor's account.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from .base import TimestampMixin


class Visitor(UserMixin, TimestampMixin, db.Model):
    """A person who signed up in order to try a sample of a product."""

    __tablename__ = "visitors"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(190), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    organization = db.Column(db.String(160))

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # The visitor may ask to be remembered on this device. The choice is
    # the visitor's own, and it is written down so that the panel can
    # show it.
    last_login_at = db.Column(db.DateTime)
    # The address of the visitor is not written down. Only a hash of it
    # is, the same way the leads of the site are kept.
    last_login_ip_hash = db.Column(db.String(64))
    login_count = db.Column(db.Integer, default=0, nullable=False)

    # The samples the visitor has opened. It is written down so that the
    # administrator can see which samples are used and when.
    access_log = db.relationship(
        "SampleAccess", back_populates="visitor", cascade="all, delete-orphan",
        order_by="SampleAccess.created_at.desc()",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def get_id(self) -> str:
        return str(self.id)

    @property
    def is_authenticated(self) -> bool:
        return True

    def touch_login(self, ip_hash: str | None = None) -> None:
        """Write down that the visitor signed in."""
        self.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.login_count = (self.login_count or 0) + 1
        if ip_hash:
            self.last_login_ip_hash = ip_hash[:64]


class SampleAccess(TimestampMixin, db.Model):
    """One opening of a sample by a visitor.

    The record says who opened which sample of which product, and when.
    It is the evidence that the samples are really being used, and it is
    written without anything that identifies the person beyond the
    account itself.
    """

    __tablename__ = "sample_accesses"

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.Integer, db.ForeignKey("visitors.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    live_link_id = db.Column(db.Integer, db.ForeignKey("portfolio_live_links.id", ondelete="CASCADE"),
                              nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"),
                           index=True)
    opened_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    ip_hash = db.Column(db.String(64))

    visitor = db.relationship("Visitor", back_populates="access_log")
    live_link = db.relationship("PortfolioLiveLink", back_populates="access_log")
    product = db.relationship("Product")
