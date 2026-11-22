from unittest.mock import patch
from app import create_app
from app.extensions import db
from app.github_sync.client import GitHubError
from app.github_sync.service import sync_repository
from app.models import Product, ProductRepository


def test_csrf_is_required(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "UPLOAD_FOLDER": tmp_path / "up", "RATELIMIT_ENABLED": False, "SECRET_KEY": "test"})
    with app.app_context():
        db.create_all()
    response = app.test_client().post("/contact", data={"name": "a"})
    assert response.status_code == 400
    assert "نشست فرم".encode() in response.data


def test_login_rate_limit(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "RATELIMIT_ENABLED": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "UPLOAD_FOLDER": tmp_path / "up", "SECRET_KEY": "test"})
    with app.app_context():
        db.create_all()
    client = app.test_client()
    statuses = [client.post("/admin/login", data={"username": "none", "password": "bad"}).status_code for _ in range(6)]
    assert statuses[-1] == 429
    assert "تعداد تلاش".encode() in client.post("/admin/login", data={"username": "none", "password": "bad"}).data


def test_oversized_request_gets_persian_error(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "RATELIMIT_ENABLED": False, "MAX_CONTENT_LENGTH": 20, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "UPLOAD_FOLDER": tmp_path / "up", "SECRET_KEY": "test"})
    with app.app_context():
        db.create_all()
    response = app.test_client().post("/contact", data={"message": "x" * 100})
    assert response.status_code == 413
    assert "حجم فایل".encode() in response.data


def test_sync_failure_does_not_break_public_site(app, client):
    with app.app_context():
        repo = ProductRepository.query.first()
        before = repo.product.short_description
        with patch("app.github_sync.client.GitHubClient.repository_snapshot", side_effect=GitHubError("شبکه قطع است", 500)):
            log = sync_repository(repo)
        assert log.status == "error"
        assert repo.product.short_description == before
    assert client.get("/").status_code == 200


def test_sync_records_pending_changes_without_editing_content(app):
    snapshot = {"metadata": {"description": "متن جدید", "default_branch": "main", "language": "Python", "archived": False, "visibility": "public", "updated_at": "2026-11-08", "html_url": "https://github.com/example/repo"}, "commit": {"sha": "newsha", "message": "new commit", "date": "2026-11-08T00:00:00Z"}, "readme_sha": "newreadme", "release": "v2"}
    with app.app_context():
        repo = ProductRepository.query.first()
        repo.last_commit_sha = "oldsha"
        repo.last_release = "v1"
        repo.remote_metadata = {"readme_sha": "oldreadme"}
        before = repo.product.short_description
        db.session.commit()
        with patch("app.github_sync.client.GitHubClient.repository_snapshot", return_value=snapshot):
            log = sync_repository(repo)
        assert log.status == "success"
        assert set(repo.pending_changes) == {"commit", "readme", "release"}
        assert repo.product.short_description == before
        assert repo.last_commit_sha == "newsha"
