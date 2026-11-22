"""Application factory for the Persian software catalogue."""
import logging
import os
from pathlib import Path
import click
from flask import Flask, g, render_template, request
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
    if app.config.get("TRUST_PROXY_HEADERS"):
        # Trust exactly one local reverse proxy. The HTTPS installer binds both
        # application backends to loopback before enabling this setting.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    from .extensions import db, migrate, login_manager, csrf, limiter
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from .models import AdminUser, CustomPage, MenuItem, SiteSetting, SocialLink
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(AdminUser, int(user_id))

    from .public.routes import bp as public_bp
    from .admin.routes import bp as admin_bp
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    from .agent_api import bp as agent_api_bp, discovery as agent_discovery_bp
    app.register_blueprint(agent_api_bp)
    app.register_blueprint(agent_discovery_bp)
    csrf.exempt(agent_api_bp)

    @app.context_processor
    def global_content():
        from .services.public_origin import canonical_url, public_url, request_is_legacy_http, secure_origin
        settings = {row.key: row.value for row in SiteSetting.query.all()}
        socials = SocialLink.query.filter_by(is_published=True).order_by(SocialLink.position).all()
        pages = CustomPage.query.filter_by(status="published", menu_links_enabled=True).order_by(CustomPage.menu_order, CustomPage.title).all()
        custom_items = MenuItem.query.filter_by(is_enabled=True, parent_id=None).order_by(MenuItem.location, MenuItem.position).all()
        return {"site": settings, "socials": socials, "setting": lambda key, default="": settings.get(key) or default,
                "csp_nonce": g.get("csp_nonce", ""),
                "canonical_url": canonical_url,
                "public_url": public_url,
                "secure_origin": secure_origin,
                "legacy_http": request_is_legacy_http(),
                "linked_pages": lambda content_id: CustomPage.query.filter_by(parent_content_id=content_id, status="published").order_by(CustomPage.menu_order, CustomPage.title).all(),
                "page_menus": {location: [p for p in pages if getattr(p, "show_in_" + location)] for location in ("main", "hamburger", "footer")},
                "custom_menu_items": custom_items}

    @app.template_filter("fa_num")
    def fa_num(value):
        from .services.utils import persian_digits
        return persian_digits(value)

    @app.template_filter("fa_date")
    def fa_date(value):
        from .services.utils import persian_digits
        return persian_digits(value.strftime("%Y/%m/%d %H:%M")) if value else "—"

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
        from .services.https_upgrade import csp_connect_sources
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        script_source = "script-src 'self'"
        if g.get("csp_nonce"):
            script_source += f" 'nonce-{g.csp_nonce}'"
        policy = (f"default-src 'self'; img-src 'self' data:; media-src 'self'; "
                  f"style-src 'self' 'unsafe-inline'; {script_source}; font-src 'self'; "
                  f"connect-src 'self'; object-src 'none'; base-uri 'self'; "
                  f"form-action 'self'; frame-ancestors 'none'")
        # The legacy-HTTP page probes the secure origin from the browser. When
        # that origin is a different host it has to be allowed explicitly;
        # nothing else about the strict policy changes.
        secure = app.config.get("PUBLIC_ORIGIN") or ""
        if secure and request.scheme != "https":
            policy = csp_connect_sources(policy, secure)
        response.headers.setdefault("Content-Security-Policy", policy)
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

    @app.cli.command("status")
    @click.option("--cert-path", default=None, help="مسیر دستی فایل گواهی همسایه.")
    def status_command(cert_path):
        """Show the public address of the site and the state of its HTTPS."""
        from .services.tls_manager import collect_status

        cert_path = cert_path or app.config.get("TLS_CERT_PATH") or None
        public_port = app.config.get("HTTPS_PUBLIC_PORT")
        http_port = app.config.get("HTTP_PUBLIC_PORT")
        origin = app.config.get("PUBLIC_ORIGIN") or app.config.get("SITE_URL") or ""

        state = collect_status(
            explicit_cert_path=cert_path,
            public_port=public_port,
            http_port=http_port,
            site_url=origin,
        )

        click.echo("وضعیت سایت RunUp")
        click.echo("─────────────────")
        if state.site_url:
            click.echo(f"نشانی سایت: {state.site_url}")
        else:
            click.echo("نشانی سایت: در پیکربندی ثبت نشده است.")

        if state.enabled and state.certificate:
            click.echo("HTTPS: روشن")
            click.echo(f"اعتبار گواهی: {state.certificate.expires_in} (تا {state.certificate.not_after.strftime('%Y-%m-%d %H:%M')} UTC)")
            if state.source_path:
                click.echo(f"منبع گواهی: {state.source_path}")
            if state.public_port:
                click.echo(f"درگاه HTTPS: {state.public_port}")
            if state.http_port:
                click.echo(f"لینک قدیمی HTTP: درگاه {state.http_port} (به نشانی امن هدایت می‌شود)")
        else:
            click.echo("HTTPS: خاموش")
            click.echo(f"دلیل: {state.reason}")
            if state.detail:
                click.echo(f"توضیح: {state.detail}")
            click.echo("اقدام لازم: فایل گواهی همسایه باید در دسترس و خوانا باشد؛ سایت خودش هر چند دقیقه دوباره بررسی می‌کند.")

    logging.basicConfig(level=app.config["LOG_LEVEL"], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return app
