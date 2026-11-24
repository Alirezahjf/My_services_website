import io
import pytest
from PIL import Image
from app import create_app
from app.extensions import db
from app.models import AdminUser
from scripts.seed_data import seed


@pytest.fixture()
def app(tmp_path):
    database = tmp_path / "test.sqlite3"
    application = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        # The counter of the limiter lives in one place for the whole
        # process. The tests make many small applications one after
        # another, and each of them must begin with an empty counter,
        # or a test would be troubled by the test that came before it.
        "RATELIMIT_STORAGE_URI": "memory://",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
        "UPLOAD_FOLDER": tmp_path / "uploads",
        "SECRET_KEY": "test-secret",
        "SERVER_NAME": None,
    })
    with application.app_context():
        db.create_all()
        seed()
        admin = AdminUser(username="admin", display_name="مدیر آزمون")
        admin.set_password("a-very-secure-test-password")
        db.session.add(admin)
        db.session.commit()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_client(client):
    response = client.post("/admin/login", data={"username": "admin", "password": "a-very-secure-test-password"}, follow_redirects=True)
    assert response.status_code == 200
    return client


@pytest.fixture()
def png_file():
    stream = io.BytesIO()
    Image.new("RGB", (100, 80), "#6758e8").save(stream, "PNG")
    stream.seek(0)
    return stream
