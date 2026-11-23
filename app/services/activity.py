from flask_login import current_user
from app.extensions import db
from app.models import ActivityLog
from .utils import client_ip_hash


def log_activity(action, entity_type=None, entity_id=None, detail=""):
    entry = ActivityLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        action=action, entity_type=entity_type, entity_id=entity_id,
        detail=str(detail)[:500], ip_hash=client_ip_hash(),
    )
    db.session.add(entry)
