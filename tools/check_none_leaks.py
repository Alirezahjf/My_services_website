"""Find every place where a missing text column could reach the page.

The script clears all nullable text columns of the seeded content, renders
every public page and reports the places where the literal word "None"
appears in the answer. It writes to a copy of the database, never to the
database of the site.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    Category, FAQ, PlatformConnector, Portfolio, PortfolioMedia, Product,
    ProductFeature, ProductMedia, ProductModule, WorkflowStep,
)

NULLABLE_TEXT = {
    Product: ["tagline", "medium_description", "full_description", "problem_statement",
              "repository_name", "public_repository_url"],
    ProductFeature: ["description", "example"],
    ProductModule: ["description"],
    PlatformConnector: ["description", "auth_method"],
    FAQ: ["answer", "question"],
    Portfolio: ["summary", "description"],
    PortfolioMedia: ["description", "title", "alt_text"],
    ProductMedia: ["description", "title", "alt_text"],
    Category: ["description"],
    WorkflowStep: ["description", "title"],
}


def main():
    workdir = tempfile.mkdtemp(prefix="runup-none-check-")
    database = os.path.join(workdir, "check.sqlite3")
    application = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
        "UPLOAD_FOLDER": os.path.join(workdir, "uploads"),
        "SECRET_KEY": "check-secret",
        "SERVER_NAME": None,
    })
    with application.app_context():
        db.create_all()
        from scripts.seed_data import seed
        seed()

        # Clear every nullable text column so that the templates have to
        # cope with the missing values.
        for model, fields in NULLABLE_TEXT.items():
            # Only the columns that really allow a missing value are
            # cleared; a NOT NULL column cannot be emptied.
            nullable = {column.key for column in model.__table__.columns if column.nullable}
            for row in db.session.query(model).all():
                for field in fields:
                    if field in nullable:
                        setattr(row, field, None)
        db.session.commit()

        from app.models import Product as P
        urls = ["/", "/products", "/services", "/portfolio", "/about", "/contact",
                "/consultation", "/custom-solution", "/legal/privacy", "/legal/terms"]
        urls += [f"/products/{p.slug}" for p in db.session.query(P).filter_by(status="published").all()]
        urls += [f"/portfolio/{p.slug}" for p in db.session.query(Portfolio).all()]

        client = application.test_client()
        findings = []
        for url in urls:
            response = client.get(url)
            body = response.get_data(as_text=True)
            if response.status_code != 200:
                findings.append((url, f"status {response.status_code}", ""))
                continue
            index = 0
            while True:
                index = body.find("None", index)
                if index < 0:
                    break
                snippet = body[max(0, index - 90):index + 40].replace("\n", " ")
                findings.append((url, "None", snippet))
                index += 4
        db.session.remove()
        db.drop_all()

    shutil.rmtree(workdir, ignore_errors=True)

    if findings:
        print(f"FOUND {len(findings)} occurrence(s) of 'None':\n")
        for url, kind, snippet in findings:
            print(f"  {url}\n      {snippet}\n")
        return 1
    print("PASS: no 'None' reaches any public page, even with every text column cleared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
