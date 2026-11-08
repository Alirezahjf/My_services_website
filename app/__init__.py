"""Application factory for the Persian software catalogue."""
import logging
import os
from pathlib import Path
import click
from flask import Flask, render_template, request
from markupsafe import Markup
from flask_login import current_user
from flask_wtf.csrf import CSRFError


def create_app(test_config=None):
    from dotenv import load_dotenv
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    from config import Config
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    from .extensions import db, migrate, login_manager, csrf, limiter
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from .models import AdminUser, SiteSetting, SocialLink
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(AdminUser, int(user_id))

    from .public.routes import bp as public_bp
    from .admin.routes import bp as admin_bp
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def global_content():
        settings = {row.key: row.value for row in SiteSetting.query.all()}
        socials = SocialLink.query.filter_by(is_published=True).order_by(SocialLink.position).all()
        return {"site": settings, "socials": socials, "setting": lambda key, default="": settings.get(key) or default}

    @app.template_filter("fa_num")
    def fa_num(value):
        from .services.utils import persian_digits
        return persian_digits(value)

    @app.template_filter("safe_html")
    def safe_html(value):
        return Markup(value or "")

    @app.template_filter("media_url")
    def media_url(path):
        from flask import url_for
        if not path:
            return ""
        if path.startswith(("static/", "http://", "https://")):
            return url_for("static", filename=path[7:]) if path.startswith("static/") else path
        return url_for("public.media", filename=path)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        if request.path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template("errors/500.html"), 500

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_template("errors/400.html", message="نشست فرم منقضی شده است. صفحه را تازه‌سازی و دوباره تلاش کنید."), 400

    @app.errorhandler(413)
    def upload_too_large(error):
        return render_template("errors/400.html", message="حجم فایل یا درخواست بیش از سقف مجاز است. فایل کوچک‌تری انتخاب کنید.", code="۴۱۳"), 413

    @app.errorhandler(429)
    def too_many_requests(error):
        return render_template("errors/400.html", message="تعداد تلاش‌ها بیش از حد مجاز است. لطفاً کمی بعد دوباره تلاش کنید.", code="۴۲۹"), 429

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/400.html", message="شما مجوز دسترسی به این بخش را ندارید.", code="۴۰۳"), 403

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(username, password):
        """Create the first administrator without hard-coded credentials."""
        if len(password) < 12:
            raise click.ClickException("رمز عبور باید حداقل ۱۲ نویسه باشد.")
        if AdminUser.query.filter_by(username=username).first():
            raise click.ClickException("این نام کاربری قبلاً ثبت شده است.")
        user = AdminUser(username=username, is_superadmin=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo("مدیر با موفقیت ساخته شد.")

    @app.cli.command("seed-content")
    def seed_content():
        """Idempotently seed repository analysis and editable initial content."""
        from scripts.seed_data import seed
        seed()
        click.echo("داده‌های اولیه ثبت/به‌روز شد.")

    logging.basicConfig(level=app.config["LOG_LEVEL"], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return app
