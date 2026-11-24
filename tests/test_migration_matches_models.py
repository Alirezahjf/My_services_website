"""The migration and the models must agree.

A migration that does not match the models leaves a server that runs
but does not work: the tables are there, but with the wrong columns or
the wrong rules. This test walks the migrations from the very beginning
on a fresh database and then asks Alembic to find the difference
between the result and the models. There must be none.
"""

import os

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app import create_app
from app.extensions import db


@pytest.fixture()
def migrated(tmp_path):
    """A database that has been walked by every migration."""
    database = tmp_path / "migrated.sqlite3"
    application = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
        "UPLOAD_FOLDER": tmp_path / "uploads",
        "SECRET_KEY": "test-secret",
    })
    with application.app_context():
        from flask_migrate import upgrade
        upgrade()
        yield application


def test_the_migration_makes_the_tables_of_the_new_models(migrated):
    with migrated.app_context():
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())
        for name in ("visitors", "portfolio_live_links", "sample_accesses"):
            assert name in tables, name


def test_the_migration_and_the_models_agree(migrated):
    """There must be no difference between what the migration makes and
    what the models ask for."""
    with migrated.app_context():
        with db.engine.connect() as connection:
            context = MigrationContext.configure(connection)
            difference = compare_metadata(context, db.metadata)
    assert not difference, difference


def test_the_migration_can_be_turned_back(migrated):
    """The new tables may be taken away again, and put back."""
    with migrated.app_context():
        from flask_migrate import downgrade, upgrade
        downgrade(revision="a69c5352e3c7")
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())
        for name in ("visitors", "portfolio_live_links", "sample_accesses"):
            assert name not in tables, name

        upgrade()
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())
        for name in ("visitors", "portfolio_live_links", "sample_accesses"):
            assert name in tables, name


def test_the_tables_of_the_migration_take_the_rows(migrated):
    """A row written through the models is really in the tables."""
    with migrated.app_context():
        from app.models import Portfolio, PortfolioLiveLink, Product, Visitor
        item = Portfolio(title="نمونه‌کار", slug="nmk", is_published=True)
        db.session.add(item)
        db.session.flush()

        product = Product(name="محصول", slug="mhs", short_description="شرح", status="published")
        db.session.add(product)
        db.session.flush()

        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.flush()

        link = PortfolioLiveLink(portfolio_id=item.id, product_id=product.id,
                                 title="نمونه", url="https://x.test/a",
                                 display_mode="live", requires_login=True, is_published=True)
        db.session.add(link)
        db.session.commit()

        assert db.session.get(Visitor, visitor.id).display_name == "کریم"
        assert db.session.get(PortfolioLiveLink, link.id).title == "نمونه"
        # The rules of the table are the ones of the model.
        assert db.session.get(PortfolioLiveLink, link.id).requires_login is True
        assert db.session.get(Visitor, visitor.id).is_active is True
