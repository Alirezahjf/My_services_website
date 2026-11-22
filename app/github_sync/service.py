"""Synchronisation service: only records differences; never edits public content."""
from datetime import datetime
from app.extensions import db
from app.models import GitHubSyncLog
from app.models.base import utcnow
from .client import GitHubClient, GitHubError


def sync_repository(repository):
    log = GitHubSyncLog(repository=repository, status="running")
    db.session.add(log)
    try:
        snapshot = GitHubClient().repository_snapshot(repository.owner, repository.name, repository.default_branch)
        commit = snapshot["commit"]
        changes = {}
        if repository.last_commit_sha and repository.last_commit_sha != commit["sha"]:
            changes["commit"] = {"before": repository.last_commit_sha, "after": commit["sha"]}
        previous_readme = (repository.remote_metadata or {}).get("readme_sha")
        if previous_readme and previous_readme != snapshot["readme_sha"]:
            changes["readme"] = {"before": previous_readme, "after": snapshot["readme_sha"]}
        if repository.last_release != snapshot["release"]:
            changes["release"] = {"before": repository.last_release, "after": snapshot["release"]}
        metadata = dict(snapshot["metadata"])
        metadata["readme_sha"] = snapshot["readme_sha"]
        repository.remote_metadata = metadata
        repository.pending_changes = changes
        repository.last_commit_sha = commit["sha"]
        repository.last_commit_message = (commit["message"] or "")[:500]
        if commit.get("date"):
            try:
                repository.last_commit_at = datetime.fromisoformat(commit["date"].replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                pass
        repository.last_release = snapshot["release"]
        repository.default_branch = snapshot["metadata"]["default_branch"] or repository.default_branch
        repository.last_synced_at = utcnow()
        log.status = "success"
        log.changes = changes
        log.message = "تغییر جدیدی شناسایی شد و برای بررسی مدیر ثبت شد." if changes else "اطلاعات مخزن دریافت شد؛ تغییری نسبت به نسخه قبلی نبود."
        db.session.commit()
        return log
    except GitHubError as exc:
        repository.last_synced_at = utcnow()
        log.status = "error"
        log.message = str(exc)
        log.http_status = exc.status
        db.session.commit()
        return log
    except Exception:
        db.session.rollback()
        failed = GitHubSyncLog(repository_id=repository.id, status="error", message="خطای پیش‌بینی‌نشده هنگام پردازش پاسخ GitHub.")
        db.session.add(failed)
        db.session.commit()
        return failed
