from app.extensions import db
from .base import TimestampMixin


class ProductRepository(TimestampMixin, db.Model):
    __tablename__ = "product_repositories"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False)
    owner = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    default_branch = db.Column(db.String(120), default="main")
    is_enabled = db.Column(db.Boolean, default=True)
    last_commit_sha = db.Column(db.String(80))
    last_commit_message = db.Column(db.String(500))
    last_commit_at = db.Column(db.DateTime)
    last_release = db.Column(db.String(100))
    last_synced_at = db.Column(db.DateTime)
    remote_metadata = db.Column(db.JSON, default=dict)
    pending_changes = db.Column(db.JSON, default=dict)
    product = db.relationship("Product", back_populates="repository")
    logs = db.relationship("GitHubSyncLog", back_populates="repository", cascade="all, delete-orphan")


class GitHubSyncLog(TimestampMixin, db.Model):
    __tablename__ = "github_sync_logs"
    id = db.Column(db.Integer, primary_key=True)
    repository_id = db.Column(db.Integer, db.ForeignKey("product_repositories.id", ondelete="CASCADE"), index=True)
    status = db.Column(db.String(30), nullable=False)
    message = db.Column(db.Text)
    changes = db.Column(db.JSON, default=dict)
    http_status = db.Column(db.Integer)
    repository = db.relationship("ProductRepository", back_populates="logs")


class RepositoryAnalysis(TimestampMixin, db.Model):
    __tablename__ = "repository_analyses"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False)
    repository_name = db.Column(db.String(160), nullable=False)
    suggested_name = db.Column(db.String(160))
    nature = db.Column(db.String(180))
    problem_solved = db.Column(db.Text)
    target_customers = db.Column(db.Text)
    verified_features = db.Column(db.JSON, default=list)
    incomplete_features = db.Column(db.JSON, default=list)
    prerequisites = db.Column(db.JSON, default=list)
    commercial_status = db.Column(db.String(100))
    category_name = db.Column(db.String(160))
    confidence = db.Column(db.String(20))
    source_commit = db.Column(db.String(80))
    files_reviewed = db.Column(db.JSON, default=list)
    security_note = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime)
    product = db.relationship("Product", back_populates="analysis")


class ActivityLog(TimestampMixin, db.Model):
    __tablename__ = "activity_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="SET NULL"), index=True)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(100))
    entity_id = db.Column(db.Integer)
    detail = db.Column(db.String(500))
    ip_hash = db.Column(db.String(64))
    user = db.relationship("AdminUser")
