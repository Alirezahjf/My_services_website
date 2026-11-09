"""AI-agent credentials, fine-grained access, approvals and audit events."""
from datetime import datetime
from app.extensions import db
from .base import TimestampMixin


class AgentConnection(TimestampMixin, db.Model):
    __tablename__ = "agent_connections"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text)
    token_prefix = db.Column(db.String(24), unique=True, nullable=False, index=True)
    token_hash = db.Column(db.String(255), nullable=False)
    permissions = db.Column(db.JSON, default=list, nullable=False)
    is_enabled = db.Column(db.Boolean, default=True, nullable=False)
    expires_at = db.Column(db.DateTime)
    last_used_at = db.Column(db.DateTime)
    rate_limit_per_minute = db.Column(db.Integer, default=60, nullable=False)
    require_approval_for_sensitive = db.Column(db.Boolean, default=True, nullable=False)
    revoked_at = db.Column(db.DateTime)
    activities = db.relationship("AgentActivity", back_populates="agent", cascade="all, delete-orphan")
    approvals = db.relationship("AgentApproval", back_populates="agent", cascade="all, delete-orphan")

    @property
    def is_active(self):
        return self.is_enabled and not self.revoked_at and (not self.expires_at or self.expires_at > datetime.utcnow())


class AgentApproval(TimestampMixin, db.Model):
    __tablename__ = "agent_approvals"
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agent_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = db.Column(db.String(120), nullable=False)
    payload = db.Column(db.JSON, default=dict, nullable=False)
    summary = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(30), default="pending", nullable=False, index=True)
    result = db.Column(db.JSON)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="SET NULL"))
    reviewed_at = db.Column(db.DateTime)
    agent = db.relationship("AgentConnection", back_populates="approvals")
    reviewer = db.relationship("AdminUser")


class AgentIdempotency(TimestampMixin, db.Model):
    __tablename__ = "agent_idempotency_keys"
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agent_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    key = db.Column(db.String(100), nullable=False)
    tool_name = db.Column(db.String(120), nullable=False)
    payload_hash = db.Column(db.String(64), nullable=False)
    response = db.Column(db.JSON, nullable=False)
    agent = db.relationship("AgentConnection")
    __table_args__ = (db.UniqueConstraint("agent_id", "key", name="uq_agent_idempotency"),)


class AgentRefreshToken(TimestampMixin, db.Model):
    __tablename__ = "agent_refresh_tokens"
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agent_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime)
    agent = db.relationship("AgentConnection")


class AgentActivity(TimestampMixin, db.Model):
    __tablename__ = "agent_activities"
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agent_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = db.Column(db.String(120), nullable=False)
    operation = db.Column(db.String(30), default="read", nullable=False)
    entity_type = db.Column(db.String(80))
    entity_id = db.Column(db.String(80))
    before_data = db.Column(db.JSON)
    after_data = db.Column(db.JSON)
    status = db.Column(db.String(30), nullable=False, index=True)
    result_summary = db.Column(db.Text)
    error_message = db.Column(db.String(500))
    approved_by = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="SET NULL"))
    agent = db.relationship("AgentConnection", back_populates="activities")
    reviewer = db.relationship("AdminUser")
