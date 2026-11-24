from app.extensions import db
from .base import TimestampMixin

portfolio_categories = db.Table(
    "portfolio_categories",
    db.Column("portfolio_id", db.Integer, db.ForeignKey("portfolios.id", ondelete="CASCADE"), primary_key=True),
    db.Column("category_id", db.Integer, db.ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)


class Portfolio(TimestampMixin, db.Model):
    __tablename__ = "portfolios"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
    summary = db.Column(db.Text)
    description = db.Column(db.Text)
    cover_path = db.Column(db.String(255))
    is_published = db.Column(db.Boolean, default=False, nullable=False, index=True)
    show_on_home = db.Column(db.Boolean, default=False, nullable=False)
    show_on_product = db.Column(db.Boolean, default=True, nullable=False)
    show_in_gallery = db.Column(db.Boolean, default=True, nullable=False)
    position = db.Column(db.Integer, default=0)
    media = db.relationship("PortfolioMedia", back_populates="portfolio", cascade="all, delete-orphan", order_by="PortfolioMedia.position")
    categories = db.relationship("Category", secondary=portfolio_categories, backref="portfolios")
    product_links = db.relationship("ProductPortfolio", back_populates="portfolio", cascade="all, delete-orphan")
    live_links = db.relationship("PortfolioLiveLink", back_populates="portfolio", cascade="all, delete-orphan", order_by="PortfolioLiveLink.position")


class PortfolioMedia(TimestampMixin, db.Model):
    __tablename__ = "portfolio_media"
    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(180))
    description = db.Column(db.Text)
    alt_text = db.Column(db.String(240))
    media_type = db.Column(db.String(20), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    thumbnail_path = db.Column(db.String(255))
    mime_type = db.Column(db.String(100))
    file_size = db.Column(db.BigInteger)
    is_cover = db.Column(db.Boolean, default=False)
    position = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True)
    portfolio = db.relationship("Portfolio", back_populates="media")


class ProductPortfolio(TimestampMixin, db.Model):
    __tablename__ = "product_portfolio"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    __table_args__ = (db.UniqueConstraint("product_id", "portfolio_id", name="uq_product_portfolio_pair"),)
    product = db.relationship("Product", back_populates="portfolio_links")
    portfolio = db.relationship("Portfolio", back_populates="product_links")


class PortfolioLiveLink(TimestampMixin, db.Model):
    """A link that can be tried out, attached to a sample of work.

    The link points at a running copy of a product. The administrator
    decides how it is shown:

    * ``live`` — the sample is drawn inside the page, so that the visitor
      can use the product without leaving the site;
    * ``link`` — the sample is only a link that opens in a new tab, for
      the products that cannot be drawn inside a frame.

    A sample is only given to a visitor who has signed in, so the record
    of who opened it is written down.
    """

    __tablename__ = "portfolio_live_links"

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"),
                           index=True)

    title = db.Column(db.String(180), nullable=False)
    url = db.Column(db.String(1000), nullable=False)
    summary = db.Column(db.Text)

    # ``live`` draws the sample inside the page; ``link`` opens it in a
    # new tab. The name is written down so that the meaning stays clear.
    display_mode = db.Column(db.String(20), default="live", nullable=False, index=True)

    # Whether the sample is given only to a visitor who has signed in.
    # It is on by default: a sample is a resource that is given with
    # care.
    requires_login = db.Column(db.Boolean, default=True, nullable=False)
    is_published = db.Column(db.Boolean, default=True, nullable=False, index=True)
    # The order of the samples on the page. It is never empty, for the
    # order of the samples would then be uncertain.
    position = db.Column(db.Integer, default=0, nullable=False)

    # How often the sample was opened. It is written by the site itself.
    open_count = db.Column(db.Integer, default=0, nullable=False)

    portfolio = db.relationship("Portfolio", back_populates="live_links")
    product = db.relationship("Product")
    access_log = db.relationship(
        "SampleAccess", back_populates="live_link", cascade="all, delete-orphan",
    )

    @property
    def is_live(self) -> bool:
        """True when the sample is drawn inside the page."""
        return self.display_mode == "live"

    @property
    def host(self) -> str:
        """The host of the sample, for the badge that is shown above it."""
        from urllib.parse import urlsplit
        try:
            return urlsplit(self.url).netloc or ""
        except ValueError:
            return ""
