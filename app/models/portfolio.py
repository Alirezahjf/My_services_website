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
