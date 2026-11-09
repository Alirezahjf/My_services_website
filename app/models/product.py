from app.extensions import db
from .base import TimestampMixin

product_category_links = db.Table(
    "product_category_links",
    db.Column("product_id", db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    db.Column("category_id", db.Integer, db.ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)


product_tags = db.Table(
    "product_tags",
    db.Column("product_id", db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(TimestampMixin, db.Model):
    __tablename__ = "tags"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)


class Product(TimestampMixin, db.Model):
    __tablename__ = "products"
    STATUSES = ("draft", "review", "development", "ready", "published", "archived")
    PRODUCT_TYPES = ("software", "ai", "automation", "library", "infrastructure", "service")

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    repository_name = db.Column(db.String(160))
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)
    tagline = db.Column(db.String(240))
    short_description = db.Column(db.Text, nullable=False)
    medium_description = db.Column(db.Text)
    full_description = db.Column(db.Text)
    value_proposition = db.Column(db.Text)
    problem_statement = db.Column(db.Text)
    use_cases = db.Column(db.JSON, default=list)
    target_audience = db.Column(db.JSON, default=list)
    prerequisites = db.Column(db.JSON, default=list)
    limitations = db.Column(db.JSON, default=list)
    technologies = db.Column(db.JSON, default=list)
    product_type = db.Column(db.String(40), default="software", nullable=False, index=True)
    status = db.Column(db.String(30), default="draft", nullable=False, index=True)
    development_status = db.Column(db.String(120), default="نیازمند بررسی")
    confidence = db.Column(db.String(20), default="low")
    is_featured = db.Column(db.Boolean, default=False, nullable=False, index=True)
    show_on_home = db.Column(db.Boolean, default=False, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    logo_path = db.Column(db.String(255))
    cover_path = db.Column(db.String(255))
    accent_color = db.Column(db.String(20), default="#6d5dfc")
    github_url = db.Column(db.String(255))
    origin_type = db.Column(db.String(40), index=True)  # github, independent, custom, hybrid
    commercial_status = db.Column(db.String(50), index=True)
    repository_enabled = db.Column(db.Boolean, default=False, nullable=False)
    repository_url = db.Column(db.String(255))
    platforms = db.Column(db.JSON, default=list)
    integration_status = db.Column(db.String(50), default="not_applicable")
    ai_enabled = db.Column(db.Boolean, default=False, nullable=False)
    automation_enabled = db.Column(db.Boolean, default=False, nullable=False)
    demo_available = db.Column(db.Boolean, default=False, nullable=False)
    pricing_visibility = db.Column(db.String(40), default="on_request")
    product_version = db.Column(db.String(40))
    release_date = db.Column(db.Date)
    seo_title = db.Column(db.String(180))
    seo_description = db.Column(db.String(320))
    price = db.Column(db.Numeric(14, 2))
    compare_price = db.Column(db.Numeric(14, 2))
    currency = db.Column(db.String(3), default="USD")
    demo_url = db.Column(db.String(500))
    docs_url = db.Column(db.String(500))
    is_black_friday = db.Column(db.Boolean, default=False, nullable=False)
    black_friday_discount_percent = db.Column(db.Integer)
    view_count = db.Column(db.Integer, default=0, nullable=False)
    updated_by_agent_id = db.Column(db.Integer, db.ForeignKey("agent_connections.id", ondelete="SET NULL"), index=True)

    category = db.relationship("Category", back_populates="products", foreign_keys=[category_id])
    additional_categories = db.relationship("Category", secondary=product_category_links, backref="additional_products", lazy="selectin")
    features = db.relationship("ProductFeature", back_populates="product", cascade="all, delete-orphan", order_by="ProductFeature.position")
    media = db.relationship("ProductMedia", back_populates="product", cascade="all, delete-orphan", order_by="ProductMedia.position")
    faqs = db.relationship("FAQ", back_populates="product", cascade="all, delete-orphan", order_by="FAQ.position")
    tags = db.relationship("Tag", secondary=product_tags, backref="products", lazy="selectin")
    repository = db.relationship("ProductRepository", back_populates="product", uselist=False, cascade="all, delete-orphan")
    analysis = db.relationship("RepositoryAnalysis", back_populates="product", uselist=False, cascade="all, delete-orphan")
    portfolio_links = db.relationship("ProductPortfolio", back_populates="product", cascade="all, delete-orphan")
    connectors = db.relationship("PlatformConnector", back_populates="product", cascade="all, delete-orphan", order_by="PlatformConnector.position")
    modules = db.relationship("ProductModule", back_populates="product", cascade="all, delete-orphan", order_by="ProductModule.position")
    repository_memberships = db.relationship("ProductRepositoryMembership", back_populates="product", cascade="all, delete-orphan")

    @property
    def all_categories(self):
        rows = ([self.category] if self.category else []) + list(self.additional_categories)
        return list({row.id: row for row in rows}.values())

    @property
    def public_repository_url(self):
        return self.repository_url or self.github_url

    @property
    def is_public(self):
        return self.status == "published"


class ProductFeature(TimestampMixin, db.Model):
    __tablename__ = "product_features"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(80), default="check")
    image_path = db.Column(db.String(255))
    example = db.Column(db.Text)
    verification_status = db.Column(db.String(30), default="verified")
    is_published = db.Column(db.Boolean, default=True, nullable=False)
    position = db.Column(db.Integer, default=0)
    product = db.relationship("Product", back_populates="features")


class ProductMedia(TimestampMixin, db.Model):
    __tablename__ = "product_media"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    alt_text = db.Column(db.String(240))
    media_type = db.Column(db.String(20), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    thumbnail_path = db.Column(db.String(255))
    external_url = db.Column(db.String(500))
    mime_type = db.Column(db.String(100))
    file_size = db.Column(db.BigInteger)
    position = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True, nullable=False)
    is_mockup = db.Column(db.Boolean, default=False, nullable=False)
    role = db.Column(db.String(20), default="gallery", nullable=False, index=True)
    variants = db.Column(db.JSON, default=dict)
    deleted_at = db.Column(db.DateTime, index=True)
    product = db.relationship("Product", back_populates="media")
