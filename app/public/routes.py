"""Public, read-only catalogue and lead capture routes."""
from pathlib import Path
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from sqlalchemy import or_
from sqlalchemy.orm import joinedload, selectinload
from app.extensions import db, limiter
from app.models import Category, ContactMessage, FAQ, Lead, PageContent, Portfolio, Product, ProductPortfolio, Service, SiteSetting, SocialLink, WorkflowStep
from app.services.media_service import MediaValidationError, save_upload
from app.services.utils import client_ip_hash
from .forms import ConsultationForm, ContactForm, CustomSolutionForm

bp = Blueprint("public", __name__)


def published_products():
    return Product.query.options(joinedload(Product.category)).filter_by(status="published")


def products_for_forms():
    return published_products().order_by(Product.position, Product.name).all()


def page_sections(page_key):
    return {row.section_key: row for row in PageContent.query.filter_by(page_key=page_key, is_published=True).all()}


@bp.get("/")
def home():
    categories = Category.query.filter_by(is_visible=True).order_by(Category.position, Category.id).all()
    for category in categories:
        category._published_count = published_products().filter(or_(Product.category_id == category.id, Product.additional_categories.any(Category.id == category.id))).count()
    featured = published_products().options(selectinload(Product.features)).filter(Product.show_on_home.is_(True)).order_by(Product.position, Product.id).limit(6).all()
    portfolios = Portfolio.query.filter_by(is_published=True, show_on_home=True).order_by(Portfolio.position).limit(6).all()
    faqs = FAQ.query.filter_by(product_id=None, is_published=True).order_by(FAQ.position).all()
    steps = WorkflowStep.query.filter_by(is_published=True).order_by(WorkflowStep.position).all()
    return render_template("public/home.html", categories=categories, products=featured,
                           portfolios=portfolios, faqs=faqs, steps=steps,
                           sections=page_sections("home"))


@bp.get("/products")
def products():
    query = published_products().options(selectinload(Product.features))
    q = (request.args.get("q") or "").strip()[:120]
    category_slug = (request.args.get("category") or "").strip()
    product_type = (request.args.get("type") or "").strip()
    featured = request.args.get("featured") == "1"
    sort = request.args.get("sort", "position")
    if q:
        term = f"%{q}%"
        query = query.filter(or_(Product.name.ilike(term), Product.short_description.ilike(term), Product.medium_description.ilike(term)))
    if category_slug:
        query = query.filter(or_(Product.category.has(Category.slug == category_slug), Product.additional_categories.any(Category.slug == category_slug)))
    if product_type in Product.PRODUCT_TYPES:
        query = query.filter(Product.product_type == product_type)
    if featured:
        query = query.filter(Product.is_featured.is_(True))
    ordering = {
        "position": (Product.position.asc(), Product.id.asc()),
        "newest": (Product.created_at.desc(),),
        "name": (Product.name.asc(),),
        "featured": (Product.is_featured.desc(), Product.position.asc()),
    }.get(sort, (Product.position.asc(),))
    page = request.args.get("page", 1, type=int)
    pagination = query.order_by(*ordering).paginate(page=max(page, 1), per_page=9, error_out=False)
    categories = Category.query.filter_by(is_visible=True).order_by(Category.position).all()
    return render_template("public/products.html", pagination=pagination, products=pagination.items,
                           categories=categories, q=q, selected_category=category_slug,
                           selected_type=product_type, selected_featured=featured, sort=sort)


@bp.get("/products/<slug>")
def product_detail(slug):
    product = Product.query.options(joinedload(Product.category), selectinload(Product.features),
                                    selectinload(Product.media), selectinload(Product.faqs),
                                    selectinload(Product.portfolio_links).joinedload(ProductPortfolio.portfolio),
                                    selectinload(Product.connectors), selectinload(Product.modules),
                                    selectinload(Product.additional_categories)
                                   ).filter_by(slug=slug, status="published").first_or_404()
    related_query = published_products().options(selectinload(Product.features)).filter(Product.id != product.id)
    category_ids = {category.id for category in product.all_categories}
    if category_ids:
        related_query = related_query.filter(or_(Product.category_id.in_(category_ids), Product.additional_categories.any(Category.id.in_(category_ids))))
    related = related_query.limit(3).all()
    portfolios = [link.portfolio for link in product.portfolio_links if link.portfolio and link.portfolio.is_published and link.portfolio.show_on_product]
    form = ConsultationForm()
    form.product_id.choices = [(0, "انتخاب محصول")] + [(p.id, p.name) for p in products_for_forms()]
    form.product_id.data = product.id
    return render_template("public/product_detail.html", product=product, related=related,
                           portfolios=portfolios, form=form)


@bp.get("/portfolio")
def portfolio():
    page = request.args.get("page", 1, type=int)
    category_slug = request.args.get("category", "")
    query = Portfolio.query.filter_by(is_published=True, show_in_gallery=True)
    if category_slug:
        query = query.join(Portfolio.categories).filter(Category.slug == category_slug)
    pagination = query.order_by(Portfolio.position, Portfolio.id.desc()).paginate(page=max(page, 1), per_page=12, error_out=False)
    categories = Category.query.filter_by(is_visible=True).order_by(Category.position).all()
    return render_template("public/portfolio.html", portfolios=pagination.items, pagination=pagination, categories=categories, selected_category=category_slug)


@bp.get("/portfolio/<slug>")
def portfolio_detail(slug):
    item = Portfolio.query.filter_by(slug=slug, is_published=True).first_or_404()
    return render_template("public/portfolio_detail.html", item=item)


@bp.get("/services")
def services():
    return render_template("public/services.html", sections=page_sections("services"), categories=Category.query.filter_by(is_visible=True).order_by(Category.position).all(), services=Service.query.filter_by(is_published=True).order_by(Service.position).all())


@bp.get("/about")
def about():
    return render_template("public/about.html", sections=page_sections("about"))


@bp.route("/contact", methods=["GET", "POST"])
@limiter.limit("8 per hour", methods=["POST"])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        entry = ContactMessage(name=form.name.data.strip(), phone=form.phone.data.strip(),
                               email=form.email.data, subject=form.subject.data.strip(),
                               message=form.message.data.strip(), ip_hash=client_ip_hash())
        db.session.add(entry)
        db.session.commit()
        flash("پیام شما با موفقیت ثبت شد. برای پیگیری، اطلاعات تماس شما در سامانه ذخیره شده است.", "success")
        return redirect(url_for("public.contact"))
    return render_template("public/contact.html", form=form, sections=page_sections("contact"))


@bp.route("/consultation", methods=["GET", "POST"])
@limiter.limit("8 per hour", methods=["POST"])
def consultation():
    form = ConsultationForm()
    choices = products_for_forms()
    form.product_id.choices = [(0, "انتخاب محصول (اختیاری)")] + [(p.id, p.name) for p in choices]
    requested = request.args.get("product", type=int)
    if request.method == "GET" and requested and any(p.id == requested for p in choices):
        form.product_id.data = requested
    if form.validate_on_submit():
        lead = Lead(name=form.name.data.strip(), phone=form.phone.data.strip(), email=form.email.data,
                    product_id=form.product_id.data or None, request_type=form.request_type.data,
                    message=form.message.data, ip_hash=client_ip_hash())
        db.session.add(lead)
        db.session.commit()
        flash("درخواست شما ثبت شد و در پنل پیگیری قرار گرفت.", "success")
        return redirect(url_for("public.consultation"))
    return render_template("public/consultation.html", form=form)


@bp.route("/custom-solution", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def custom_solution():
    form = CustomSolutionForm()
    if form.validate_on_submit():
        attachment_path = None
        try:
            if form.attachment.data:
                attachment_path = save_upload(form.attachment.data, "document")["path"]
            lead = Lead(name=form.name.data.strip(), organization=form.organization.data.strip(),
                        phone=form.phone.data.strip(), email=form.email.data, industry=form.industry.data,
                        need_type=form.need_type.data, message=form.message.data, budget=form.budget.data,
                        attachment_path=attachment_path, request_type="custom", ip_hash=client_ip_hash())
            db.session.add(lead)
            db.session.commit()
        except (MediaValidationError, OSError):
            db.session.rollback()
            flash("بارگذاری پیوست انجام نشد. نوع و حجم فایل را بررسی کنید.", "error")
        else:
            flash("شرح نیاز شما با موفقیت ثبت شد.", "success")
            return redirect(url_for("public.custom_solution"))
    return render_template("public/custom_solution.html", form=form)


@bp.get("/legal/<page_key>")
def legal(page_key):
    if page_key not in {"privacy", "terms"}:
        abort(404)
    section = PageContent.query.filter_by(page_key=page_key, section_key="main", is_published=True).first()
    if not section:
        abort(404)
    return render_template("public/legal.html", section=section)


@bp.get("/media/<path:filename>")
def media(filename):
    if ".." in filename or filename.startswith("/"):
        abort(404)
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    return send_from_directory(root, filename, conditional=True, max_age=86400, download_name=Path(filename).name)


@bp.get("/sitemap.xml")
def sitemap():
    pages = [url_for("public.home", _external=True), url_for("public.products", _external=True),
             url_for("public.portfolio", _external=True), url_for("public.services", _external=True),
             url_for("public.about", _external=True), url_for("public.contact", _external=True)]
    pages += [url_for("public.product_detail", slug=p.slug, _external=True) for p in published_products().all()]
    pages += [url_for("public.portfolio_detail", slug=p.slug, _external=True) for p in Portfolio.query.filter_by(is_published=True).all()]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    xml += [f"<url><loc>{__import__('html').escape(page)}</loc></url>" for page in pages]
    xml.append("</urlset>")
    return "\n".join(xml), 200, {"Content-Type": "application/xml; charset=utf-8"}


@bp.get("/robots.txt")
def robots():
    sitemap_url = url_for("public.sitemap", _external=True)
    return f"User-agent: *\nAllow: /\nDisallow: /admin/\nSitemap: {sitemap_url}\n", 200, {"Content-Type": "text/plain; charset=utf-8"}
