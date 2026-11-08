"""Authenticated content management. All mutations use POST and CSRF protection."""
import csv
import io
from datetime import datetime
from functools import wraps
import bleach
from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_
from app.extensions import db, limiter
from app.models import (ActivityLog, AdminUser, Category, ContactMessage, FAQ, GitHubSyncLog,
                        Lead, PageContent, Portfolio,
                        PortfolioMedia, Product, ProductFeature, ProductMedia, ProductPortfolio,
                        ProductRepository, RepositoryAnalysis, Service, SiteSetting, SocialLink, Tag, WorkflowStep)
from app.github_sync.service import sync_repository
from app.services.activity import log_activity
from app.services.media_service import MediaValidationError, delete_upload, save_upload
from app.services.utils import client_ip_hash, slugify, split_lines
from .forms import (CategoryForm, DeleteForm, FAQForm, FeatureForm, LeadUpdateForm, LoginForm,
                    MediaForm, PageContentForm, PasswordForm, PortfolioForm, ProductForm,
                    ServiceForm, SettingsForm, SocialForm, WorkflowForm)

bp = Blueprint("admin", __name__, url_prefix="/admin")
ALLOWED_HTML_TAGS = ["p", "br", "strong", "b", "em", "i", "ul", "ol", "li", "h2", "h3", "h4", "blockquote", "a", "code", "pre"]
ALLOWED_HTML_ATTRS = {"a": ["href", "title", "rel"]}


def superadmin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_superadmin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def unique_slug(model, value, current_id=None):
    base = slugify(value) or "item"
    candidate, number = base, 2
    while True:
        query = model.query.filter_by(slug=candidate)
        if current_id:
            query = query.filter(model.id != current_id)
        if not query.first():
            return candidate
        candidate = f"{base}-{number}"
        number += 1


def products_choices(empty=None):
    rows = Product.query.order_by(Product.name).all()
    return ([empty] if empty else []) + [(p.id, p.name) for p in rows]


def save_setting(key, value, group="brand"):
    row = SiteSetting.query.filter_by(key=key).first()
    if not row:
        row = SiteSetting(key=key, group_name=group)
        db.session.add(row)
    row.value = value or ""
    row.group_name = group


def clean_html(value):
    return bleach.clean(value or "", tags=ALLOWED_HTML_TAGS, attributes=ALLOWED_HTML_ATTRS, protocols=["http", "https", "mailto"], strip=True)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute;20 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        user = AdminUser.query.filter_by(username=form.username.data.strip()).first()
        if user and user.is_active and user.check_password(form.password.data):
            login_user(user, fresh=True)
            user.last_login_at = datetime.utcnow()
            log_activity("login", "AdminUser", user.id, "ورود موفق")
            db.session.commit()
            next_url = request.args.get("next", "")
            if next_url.startswith("/admin") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("admin.dashboard"))
        flash("نام کاربری یا رمز عبور نادرست است.", "error")
    return render_template("admin/login.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    log_activity("logout", "AdminUser", current_user.id)
    db.session.commit()
    logout_user()
    flash("با موفقیت خارج شدید.", "success")
    return redirect(url_for("admin.login"))


@bp.get("/")
@login_required
def dashboard():
    stats = {
        "products": Product.query.count(),
        "published": Product.query.filter_by(status="published").count(),
        "drafts": Product.query.filter(Product.status.in_(["draft", "review", "development"])).count(),
        "categories": Category.query.count(), "portfolios": Portfolio.query.count(),
        "messages": ContactMessage.query.count(), "leads": Lead.query.count(),
        "new_leads": Lead.query.filter_by(status="new").count(),
    }
    latest_leads = Lead.query.order_by(Lead.created_at.desc()).limit(6).all()
    latest_products = Product.query.order_by(Product.updated_at.desc()).limit(6).all()
    last_sync = GitHubSyncLog.query.order_by(GitHubSyncLog.created_at.desc()).first()
    return render_template("admin/dashboard.html", stats=stats, latest_leads=latest_leads,
                           latest_products=latest_products, last_sync=last_sync)


@bp.route("/password", methods=["GET", "POST"])
@login_required
def password():
    form = PasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            form.current_password.errors.append("رمز عبور فعلی نادرست است.")
        else:
            current_user.set_password(form.new_password.data)
            log_activity("password_change", "AdminUser", current_user.id)
            db.session.commit()
            flash("رمز عبور تغییر کرد.", "success")
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/password.html", form=form)


@bp.get("/products")
@login_required
def products():
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status", "")
    query = Product.query
    if q:
        query = query.filter(or_(Product.name.ilike(f"%{q}%"), Product.repository_name.ilike(f"%{q}%")))
    if status in Product.STATUSES:
        query = query.filter_by(status=status)
    rows = query.order_by(Product.position, Product.id).all()
    return render_template("admin/products.html", products=rows, q=q, status=status, delete_form=DeleteForm())


def populate_product_form(form, product=None):
    form.category_id.choices = [(0, "بدون دسته‌بندی")] + [(c.id, c.name) for c in Category.query.order_by(Category.position).all()]
    if product:
        form.use_cases_text.data = "\n".join(product.use_cases or [])
        form.target_audience_text.data = "\n".join(product.target_audience or [])
        form.prerequisites_text.data = "\n".join(product.prerequisites or [])
        form.limitations_text.data = "\n".join(product.limitations or [])
        form.technologies_text.data = "\n".join(product.technologies or [])
        form.tags_text.data = "، ".join(t.name for t in product.tags)


def apply_product_form(form, product):
    fields = ["name", "repository_name", "tagline", "short_description", "medium_description",
              "full_description", "value_proposition", "problem_statement", "product_type",
              "status", "development_status", "confidence", "github_url", "position",
              "is_featured", "show_on_home", "seo_title", "seo_description"]
    for field in fields:
        setattr(product, field, getattr(form, field).data)
    product.category_id = form.category_id.data or None
    product.accent_color = form.accent_color.data if __import__("re").fullmatch(r"#[0-9a-fA-F]{6}", form.accent_color.data or "") else "#6d5dfc"
    product.use_cases = split_lines(form.use_cases_text.data)
    product.target_audience = split_lines(form.target_audience_text.data)
    product.prerequisites = split_lines(form.prerequisites_text.data)
    product.limitations = split_lines(form.limitations_text.data)
    product.technologies = split_lines(form.technologies_text.data)
    tag_names = [x.strip() for x in (form.tags_text.data or "").replace("،", ",").split(",") if x.strip()]
    tags = []
    for name in tag_names[:20]:
        tag_slug = unique_slug(Tag, name)
        tag = Tag.query.filter(db.func.lower(Tag.name) == name.lower()).first()
        if not tag:
            tag = Tag(name=name, slug=tag_slug)
            db.session.add(tag)
        tags.append(tag)
    product.tags = tags


@bp.route("/products/new", methods=["GET", "POST"])
@login_required
def product_new():
    form = ProductForm()
    populate_product_form(form)
    if form.validate_on_submit():
        product = Product(slug=unique_slug(Product, form.slug.data or form.name.data))
        apply_product_form(form, product)
        try:
            if form.logo.data:
                product.logo_path = save_upload(form.logo.data, "image")["path"]
            if form.cover.data:
                product.cover_path = save_upload(form.cover.data, "image")["path"]
            db.session.add(product)
            if product.repository_name:
                product.repository = ProductRepository(owner="Alirezahjf", name=product.repository_name)
            log_activity("create", "Product", detail=product.name)
            db.session.commit()
            flash("محصول ذخیره شد. برای نمایش عمومی، وضعیت را «منتشرشده» قرار دهید.", "success")
            return redirect(url_for("admin.product_edit", product_id=product.id))
        except (MediaValidationError, OSError) as exc:
            db.session.rollback()
            flash(str(exc) or "ذخیره فایل انجام نشد.", "error")
    return render_template("admin/product_form.html", form=form, product=None, title="افزودن محصول")


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    form = ProductForm(obj=product)
    populate_product_form(form, product if request.method == "GET" else None)
    if form.validate_on_submit():
        product.slug = unique_slug(Product, form.slug.data or form.name.data, product.id)
        apply_product_form(form, product)
        try:
            if form.logo.data:
                old = product.logo_path
                product.logo_path = save_upload(form.logo.data, "image")["path"]
                delete_upload(old)
            if form.cover.data:
                old = product.cover_path
                product.cover_path = save_upload(form.cover.data, "image")["path"]
                delete_upload(old)
            if product.repository_name and not product.repository:
                product.repository = ProductRepository(owner="Alirezahjf", name=product.repository_name)
            elif product.repository:
                product.repository.name = product.repository_name
            log_activity("update", "Product", product.id, product.name)
            db.session.commit()
            flash("تغییرات محصول ذخیره شد.", "success")
            return redirect(url_for("admin.product_edit", product_id=product.id))
        except (MediaValidationError, OSError) as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("admin/product_form.html", form=form, product=product, title=f"ویرایش {product.name}")


@bp.get("/products/<int:product_id>/preview")
@login_required
def product_preview(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template("public/product_detail.html", product=product, related=[], portfolios=[], form=None, admin_preview=True)


@bp.post("/products/<int:product_id>/status")
@login_required
def product_status(product_id):
    product = Product.query.get_or_404(product_id)
    status = request.form.get("status")
    if status not in Product.STATUSES:
        abort(400)
    product.status = status
    log_activity("status", "Product", product.id, status)
    db.session.commit()
    flash("وضعیت محصول تغییر کرد.", "success")
    return redirect(request.referrer or url_for("admin.products"))


@bp.post("/products/<int:product_id>/delete")
@login_required
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    name = product.name
    log_activity("delete", "Product", product.id, name)
    db.session.delete(product)
    db.session.commit()
    flash(f"محصول «{name}» حذف شد.", "success")
    return redirect(url_for("admin.products"))


@bp.get("/categories")
@login_required
def categories():
    return render_template("admin/categories.html", categories=Category.query.order_by(Category.position).all(), delete_form=DeleteForm())


@bp.route("/categories/new", methods=["GET", "POST"])
@bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
def category_edit(category_id=None):
    category = Category.query.get_or_404(category_id) if category_id else None
    form = CategoryForm(obj=category)
    if form.validate_on_submit():
        item = category or Category()
        form.populate_obj(item)
        item.slug = unique_slug(Category, form.slug.data or form.english_name.data or form.name.data, item.id)
        if not category:
            db.session.add(item)
        log_activity("update" if category else "create", "Category", detail=item.name)
        db.session.commit()
        flash("دسته‌بندی ذخیره شد.", "success")
        return redirect(url_for("admin.categories"))
    return render_template("admin/simple_form.html", form=form, title="ویرایش دسته‌بندی" if category else "دسته‌بندی جدید", back_url=url_for("admin.categories"))


@bp.post("/categories/<int:category_id>/delete")
@login_required
def category_delete(category_id):
    item = Category.query.get_or_404(category_id)
    if item.products or item.portfolios:
        flash("این دسته دارای محصول یا نمونه‌کار است. ابتدا ارتباط آن‌ها را تغییر دهید.", "error")
    else:
        db.session.delete(item)
        log_activity("delete", "Category", item.id, item.name)
        db.session.commit()
        flash("دسته‌بندی حذف شد.", "success")
    return redirect(url_for("admin.categories"))


@bp.get("/features")
@login_required
def features():
    return render_template("admin/features.html", features=ProductFeature.query.order_by(ProductFeature.product_id, ProductFeature.position).all(), delete_form=DeleteForm())


@bp.route("/features/new", methods=["GET", "POST"])
@bp.route("/features/<int:feature_id>/edit", methods=["GET", "POST"])
@login_required
def feature_edit(feature_id=None):
    item = ProductFeature.query.get_or_404(feature_id) if feature_id else None
    form = FeatureForm(obj=item)
    form.product_id.choices = products_choices()
    if request.args.get("product", type=int) and request.method == "GET":
        form.product_id.data = request.args.get("product", type=int)
    if form.validate_on_submit():
        feature = item or ProductFeature()
        form.populate_obj(feature)
        if not item:
            db.session.add(feature)
        log_activity("update" if item else "create", "ProductFeature", detail=feature.title)
        db.session.commit()
        flash("قابلیت ذخیره شد.", "success")
        return redirect(url_for("admin.features"))
    return render_template("admin/simple_form.html", form=form, title="ویرایش قابلیت" if item else "قابلیت جدید", back_url=url_for("admin.features"))


@bp.post("/features/<int:feature_id>/delete")
@login_required
def feature_delete(feature_id):
    item = ProductFeature.query.get_or_404(feature_id)
    db.session.delete(item)
    log_activity("delete", "ProductFeature", item.id, item.title)
    db.session.commit()
    flash("قابلیت حذف شد.", "success")
    return redirect(url_for("admin.features"))


@bp.get("/portfolios")
@login_required
def portfolios():
    return render_template("admin/portfolios.html", portfolios=Portfolio.query.order_by(Portfolio.position).all(), delete_form=DeleteForm())


@bp.route("/portfolios/new", methods=["GET", "POST"])
@bp.route("/portfolios/<int:portfolio_id>/edit", methods=["GET", "POST"])
@login_required
def portfolio_edit(portfolio_id=None):
    item = Portfolio.query.get_or_404(portfolio_id) if portfolio_id else None
    form = PortfolioForm(obj=item)
    form.product_ids.choices = products_choices()
    form.category_ids.choices = [(c.id, c.name) for c in Category.query.order_by(Category.position).all()]
    if item and request.method == "GET":
        form.product_ids.data = [link.product_id for link in item.product_links]
        form.category_ids.data = [c.id for c in item.categories]
    if form.validate_on_submit():
        portfolio = item or Portfolio()
        form.populate_obj(portfolio)
        portfolio.slug = unique_slug(Portfolio, form.slug.data or form.title.data, portfolio.id)
        portfolio.categories = Category.query.filter(Category.id.in_(form.category_ids.data or [])).all()
        if not item:
            db.session.add(portfolio)
            db.session.flush()
        selected = set(form.product_ids.data or [])
        for link in list(portfolio.product_links):
            if link.product_id not in selected:
                db.session.delete(link)
        existing = {link.product_id for link in portfolio.product_links}
        for pid in selected - existing:
            portfolio.product_links.append(ProductPortfolio(product_id=pid))
        try:
            if form.cover.data:
                old = portfolio.cover_path
                portfolio.cover_path = save_upload(form.cover.data, "image")["path"]
                delete_upload(old)
            log_activity("update" if item else "create", "Portfolio", detail=portfolio.title)
            db.session.commit()
            flash("نمونه‌کار ذخیره شد.", "success")
            return redirect(url_for("admin.portfolios"))
        except (MediaValidationError, OSError) as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("admin/simple_form.html", form=form, title="ویرایش نمونه‌کار" if item else "نمونه‌کار جدید", back_url=url_for("admin.portfolios"))


@bp.post("/portfolios/<int:portfolio_id>/delete")
@login_required
def portfolio_delete(portfolio_id):
    item = Portfolio.query.get_or_404(portfolio_id)
    db.session.delete(item)
    log_activity("delete", "Portfolio", item.id, item.title)
    db.session.commit()
    flash("نمونه‌کار حذف شد.", "success")
    return redirect(url_for("admin.portfolios"))


@bp.get("/media")
@login_required
def media_library():
    product_media = ProductMedia.query.order_by(ProductMedia.created_at.desc()).all()
    portfolio_media = PortfolioMedia.query.order_by(PortfolioMedia.created_at.desc()).all()
    return render_template("admin/media.html", product_media=product_media, portfolio_media=portfolio_media, delete_form=DeleteForm())


@bp.route("/media/new", methods=["GET", "POST"])
@login_required
def media_new():
    form = MediaForm()
    owner_type = request.values.get("owner_type", "product")
    form.owner_type.data = owner_type
    if owner_type == "portfolio":
        form.owner_id.choices = [(p.id, p.title) for p in Portfolio.query.order_by(Portfolio.title).all()]
    else:
        form.owner_id.choices = products_choices()
    if form.validate_on_submit():
        kind = {"image": "image", "video": "video", "document": "document"}[form.media_type.data]
        uploaded_files = form.file.data if isinstance(form.file.data, list) else [form.file.data]
        uploaded_files = [file for file in uploaded_files if file and file.filename]
        if len(uploaded_files) > (20 if kind == "image" else 1):
            form.file.errors.append("در هر بار حداکثر ۲۰ تصویر یا یک ویدئو/PDF انتخاب کنید.")
        else:
            saved_paths = []
            try:
                for index, upload in enumerate(uploaded_files):
                    saved = save_upload(upload, kind)
                    saved_paths.extend([saved["path"], saved["thumbnail"]])
                    title = form.title.data if len(uploaded_files) == 1 else f"{form.title.data} — {index + 1}"
                    if form.owner_type.data == "portfolio":
                        Portfolio.query.get_or_404(form.owner_id.data)
                        item = PortfolioMedia(portfolio_id=form.owner_id.data, title=title,
                            description=form.description.data, alt_text=form.alt_text.data,
                            media_type=form.media_type.data, file_path=saved["path"], thumbnail_path=saved["thumbnail"],
                            mime_type=saved["mime_type"], file_size=saved["size"], position=form.position.data + index,
                            is_cover=form.is_cover.data and index == 0, is_published=form.is_published.data)
                        if item.is_cover:
                            PortfolioMedia.query.filter_by(portfolio_id=item.portfolio_id).update({"is_cover": False})
                            item.portfolio.cover_path = item.file_path
                    else:
                        Product.query.get_or_404(form.owner_id.data)
                        item = ProductMedia(product_id=form.owner_id.data, title=title,
                            description=form.description.data, alt_text=form.alt_text.data,
                            media_type=form.media_type.data, file_path=saved["path"], thumbnail_path=saved["thumbnail"],
                            mime_type=saved["mime_type"], file_size=saved["size"], position=form.position.data + index,
                            is_mockup=form.is_mockup.data, is_published=form.is_published.data)
                    db.session.add(item)
                log_activity("upload", "Media", detail=f"{len(uploaded_files)} فایل برای {form.title.data}")
                db.session.commit()
                flash(f"{len(uploaded_files)} رسانه بارگذاری و متصل شد.", "success")
                return redirect(url_for("admin.media_library"))
            except (MediaValidationError, OSError) as exc:
                db.session.rollback()
                for path in saved_paths:
                    delete_upload(path)
                flash(str(exc), "error")
    return render_template("admin/simple_form.html", form=form, title="بارگذاری رسانه", back_url=url_for("admin.media_library"))


@bp.post("/media/<kind>/<int:media_id>/delete")
@login_required
def media_delete(kind, media_id):
    model = ProductMedia if kind == "product" else PortfolioMedia if kind == "portfolio" else None
    if not model:
        abort(404)
    item = model.query.get_or_404(media_id)
    delete_upload(item.file_path)
    delete_upload(item.thumbnail_path)
    db.session.delete(item)
    log_activity("delete_media", kind, media_id)
    db.session.commit()
    flash("رسانه حذف شد.", "success")
    return redirect(url_for("admin.media_library"))


@bp.get("/faqs")
@login_required
def faqs():
    return render_template("admin/faqs.html", faqs=FAQ.query.order_by(FAQ.product_id, FAQ.position).all(), delete_form=DeleteForm())


@bp.route("/faqs/new", methods=["GET", "POST"])
@bp.route("/faqs/<int:faq_id>/edit", methods=["GET", "POST"])
@login_required
def faq_edit(faq_id=None):
    item = FAQ.query.get_or_404(faq_id) if faq_id else None
    form = FAQForm(obj=item)
    form.product_id.choices = products_choices((0, "پرسش عمومی"))
    if form.validate_on_submit():
        faq = item or FAQ()
        form.populate_obj(faq)
        faq.product_id = form.product_id.data or None
        if not item:
            db.session.add(faq)
        log_activity("update" if item else "create", "FAQ", detail=faq.question)
        db.session.commit()
        flash("پرسش ذخیره شد.", "success")
        return redirect(url_for("admin.faqs"))
    return render_template("admin/simple_form.html", form=form, title="ویرایش پرسش" if item else "پرسش جدید", back_url=url_for("admin.faqs"))


@bp.post("/faqs/<int:faq_id>/delete")
@login_required
def faq_delete(faq_id):
    item = FAQ.query.get_or_404(faq_id)
    db.session.delete(item)
    db.session.commit()
    flash("پرسش حذف شد.", "success")
    return redirect(url_for("admin.faqs"))


@bp.get("/content")
@login_required
def content():
    rows = PageContent.query.order_by(PageContent.page_key, PageContent.position).all()
    return render_template("admin/content.html", contents=rows, delete_form=DeleteForm())


@bp.route("/content/new", methods=["GET", "POST"])
@bp.route("/content/<int:content_id>/edit", methods=["GET", "POST"])
@login_required
def content_edit(content_id=None):
    item = PageContent.query.get_or_404(content_id) if content_id else None
    form = PageContentForm(obj=item)
    if form.validate_on_submit():
        duplicate = PageContent.query.filter_by(page_key=form.page_key.data, section_key=form.section_key.data).first()
        if duplicate and duplicate.id != content_id:
            form.section_key.errors.append("این بخش قبلاً برای صفحه ساخته شده است.")
        else:
            content = item or PageContent()
            form.populate_obj(content)
            content.body = clean_html(form.body.data)
            if not item:
                db.session.add(content)
            log_activity("update" if item else "create", "PageContent", detail=f"{content.page_key}/{content.section_key}")
            db.session.commit()
            flash("محتوای صفحه ذخیره شد.", "success")
            return redirect(url_for("admin.content"))
    return render_template("admin/simple_form.html", form=form, title="ویرایش محتوا" if item else "محتوای جدید", back_url=url_for("admin.content"))


@bp.post("/content/<int:content_id>/delete")
@login_required
def content_delete(content_id):
    item = PageContent.query.get_or_404(content_id)
    db.session.delete(item)
    db.session.commit()
    flash("بخش محتوایی حذف شد.", "success")
    return redirect(url_for("admin.content"))


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    form = SettingsForm()
    keys = ["brand_name", "brand_tagline", "brand_description", "email", "phone", "address", "website_url", "footer_text", "copyright_text", "default_seo_title", "default_seo_description", "social_share_image"]
    if request.method == "GET":
        for key in keys:
            getattr(form, key).data = SiteSetting.get(key)
    if form.validate_on_submit():
        try:
            for key in keys:
                save_setting(key, getattr(form, key).data)
            if form.logo.data:
                saved = save_upload(form.logo.data, "image")
                save_setting("brand_logo", saved["path"])
            log_activity("update", "SiteSetting", detail="brand")
            db.session.commit()
            flash("تنظیمات برند و سایت ذخیره شد.", "success")
            return redirect(url_for("admin.settings"))
        except (MediaValidationError, OSError) as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("admin/settings.html", form=form)


@bp.get("/services")
@login_required
def services():
    return render_template("admin/services.html", services=Service.query.order_by(Service.position).all(), delete_form=DeleteForm())


@bp.route("/services/new", methods=["GET", "POST"])
@bp.route("/services/<int:service_id>/edit", methods=["GET", "POST"])
@login_required
def service_edit(service_id=None):
    item = Service.query.get_or_404(service_id) if service_id else None
    form = ServiceForm(obj=item)
    if form.validate_on_submit():
        service = item or Service()
        form.populate_obj(service)
        if not item:
            db.session.add(service)
        log_activity("update" if item else "create", "Service", detail=service.title)
        db.session.commit()
        flash("خدمت ذخیره شد.", "success")
        return redirect(url_for("admin.services"))
    return render_template("admin/simple_form.html", form=form, title="ویرایش خدمت" if item else "خدمت جدید", back_url=url_for("admin.services"))


@bp.post("/services/<int:service_id>/delete")
@login_required
def service_delete(service_id):
    item = Service.query.get_or_404(service_id)
    db.session.delete(item)
    log_activity("delete", "Service", item.id, item.title)
    db.session.commit()
    flash("خدمت حذف شد.", "success")
    return redirect(url_for("admin.services"))


@bp.get("/workflow")
@login_required
def workflow():
    return render_template("admin/workflow.html", steps=WorkflowStep.query.order_by(WorkflowStep.position).all(), socials=SocialLink.query.order_by(SocialLink.position).all(), delete_form=DeleteForm())


@bp.route("/workflow/new", methods=["GET", "POST"])
@bp.route("/workflow/<int:step_id>/edit", methods=["GET", "POST"])
@login_required
def workflow_edit(step_id=None):
    item = WorkflowStep.query.get_or_404(step_id) if step_id else None
    form = WorkflowForm(obj=item)
    if form.validate_on_submit():
        step = item or WorkflowStep()
        form.populate_obj(step)
        if not item:
            db.session.add(step)
        db.session.commit()
        flash("مرحله ذخیره شد.", "success")
        return redirect(url_for("admin.workflow"))
    return render_template("admin/simple_form.html", form=form, title="مرحله همکاری", back_url=url_for("admin.workflow"))


@bp.post("/workflow/<int:step_id>/delete")
@login_required
def workflow_delete(step_id):
    db.session.delete(WorkflowStep.query.get_or_404(step_id))
    db.session.commit()
    return redirect(url_for("admin.workflow"))


@bp.route("/socials/new", methods=["GET", "POST"])
@bp.route("/socials/<int:social_id>/edit", methods=["GET", "POST"])
@login_required
def social_edit(social_id=None):
    item = SocialLink.query.get_or_404(social_id) if social_id else None
    form = SocialForm(obj=item)
    if form.validate_on_submit():
        social = item or SocialLink()
        form.populate_obj(social)
        if not item:
            db.session.add(social)
        db.session.commit()
        flash("شبکه اجتماعی ذخیره شد.", "success")
        return redirect(url_for("admin.workflow"))
    return render_template("admin/simple_form.html", form=form, title="شبکه اجتماعی", back_url=url_for("admin.workflow"))


@bp.post("/socials/<int:social_id>/delete")
@login_required
def social_delete(social_id):
    db.session.delete(SocialLink.query.get_or_404(social_id))
    db.session.commit()
    return redirect(url_for("admin.workflow"))


@bp.get("/leads")
@login_required
def leads():
    status = request.args.get("status", "")
    q = (request.args.get("q") or "").strip()
    kind = request.args.get("kind", "lead")
    model = ContactMessage if kind == "message" else Lead
    query = model.query
    if status:
        query = query.filter_by(status=status)
    if q:
        query = query.filter(or_(model.name.ilike(f"%{q}%"), model.phone.ilike(f"%{q}%")))
    rows = query.order_by(model.created_at.desc()).all()
    return render_template("admin/leads.html", leads=rows, kind=kind, q=q, status=status)


@bp.route("/leads/<kind>/<int:lead_id>", methods=["GET", "POST"])
@login_required
def lead_detail(kind, lead_id):
    model = ContactMessage if kind == "message" else Lead if kind == "lead" else None
    if not model:
        abort(404)
    item = model.query.get_or_404(lead_id)
    form = LeadUpdateForm(obj=item)
    if form.validate_on_submit():
        item.status = form.status.data
        item.admin_note = form.admin_note.data
        log_activity("lead_update", kind, item.id, item.status)
        db.session.commit()
        flash("وضعیت پیگیری ذخیره شد.", "success")
        return redirect(url_for("admin.lead_detail", kind=kind, lead_id=item.id))
    return render_template("admin/lead_detail.html", item=item, form=form, kind=kind)


@bp.get("/leads/export.csv")
@login_required
def leads_export():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["نام", "مجموعه", "تلفن", "ایمیل", "محصول", "نوع", "پیام", "وضعیت", "تاریخ"])
    for lead in Lead.query.order_by(Lead.created_at.desc()).all():
        def safe(value):
            text = str(value or "")
            return "'" + text if text.startswith(("=", "+", "-", "@")) else text
        writer.writerow([safe(x) for x in [lead.name, lead.organization, lead.phone, lead.email, lead.product.name if lead.product else "", lead.request_type, lead.message, lead.status, lead.created_at.isoformat()]])
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=leads.csv"})


@bp.get("/repositories")
@login_required
def repositories():
    repos = ProductRepository.query.order_by(ProductRepository.name).all()
    analyses = RepositoryAnalysis.query.order_by(RepositoryAnalysis.repository_name).all()
    return render_template("admin/repositories.html", repositories=repos, analyses=analyses, delete_form=DeleteForm())


@bp.post("/repositories/<int:repo_id>/sync")
@login_required
def repository_sync(repo_id):
    repo = ProductRepository.query.get_or_404(repo_id)
    if not repo.is_enabled:
        flash("همگام‌سازی این مخزن غیرفعال است.", "warning")
    else:
        log = sync_repository(repo)
        log_activity("github_sync", "ProductRepository", repo.id, log.status)
        db.session.commit()
        flash(log.message, "success" if log.status == "success" else "error")
    return redirect(url_for("admin.repositories"))


@bp.post("/repositories/<int:repo_id>/toggle")
@login_required
def repository_toggle(repo_id):
    repo = ProductRepository.query.get_or_404(repo_id)
    repo.is_enabled = not repo.is_enabled
    log_activity("github_toggle", "ProductRepository", repo.id, str(repo.is_enabled))
    db.session.commit()
    flash("وضعیت همگام‌سازی تغییر کرد.", "success")
    return redirect(url_for("admin.repositories"))


@bp.post("/repositories/<int:repo_id>/approve")
@login_required
def repository_approve(repo_id):
    repo = ProductRepository.query.get_or_404(repo_id)
    repo.pending_changes = {}
    log_activity("github_approve", "ProductRepository", repo.id, "تغییرات بررسی شد؛ محتوای عمومی تغییر نکرد.")
    db.session.commit()
    flash("گزارش تغییرات بررسی و بسته شد. محتوای دستی محصول تغییری نکرد.", "success")
    return redirect(url_for("admin.repositories"))


@bp.get("/analyses/<int:analysis_id>")
@login_required
def analysis_detail(analysis_id):
    item = RepositoryAnalysis.query.get_or_404(analysis_id)
    return render_template("admin/analysis_detail.html", item=item)


@bp.get("/activity")
@superadmin_required
def activity():
    rows = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(300).all()
    return render_template("admin/activity.html", activities=rows)
