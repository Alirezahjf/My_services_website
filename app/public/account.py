"""The account of the visitor, and the samples that are given to it.

A visitor may look at the site without signing in. A sample of a
product is different: it is given only to a visitor whose name is
known, so that the work is not handed to the whole world without a
trace.

The pages here are:

* ``/account/register`` — a visitor makes an account;
* ``/account/login`` — a visitor comes back;
* ``/account/logout`` — a visitor leaves;
* ``/account`` — the account of the visitor, with what it has opened;
* ``/samples/<int:link_id>`` — the sample itself. It is only given to a
  visitor who has signed in; everybody else is sent to the sign-in page
  and comes back afterwards.
"""

from __future__ import annotations

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.extensions import db, limiter
from app.models import PortfolioLiveLink, Product, SampleAccess, Visitor
from app.services.utils import client_ip_hash
from app.services.visitor_auth import current_visitor, sign_in, sign_out

from .forms import VisitorLoginForm, VisitorRegisterForm

bp = Blueprint("account", __name__, url_prefix="/account")

# The sample itself does not live under ``/account``. It is a page of
# the site, and the visitor comes to it from the sample of work or from
# the page of the product.
samples_bp = Blueprint("samples", __name__, url_prefix="/samples")


def _safe_next(default: str = "/account") -> str:
    """The address to go to after the sign-in, when it is on this site."""
    target = request.args.get("next") or request.form.get("next") or ""
    if not target.startswith("/") or target.startswith("//"):
        return default
    return target


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute;20 per hour")
def register():
    """A visitor makes an account."""
    if current_visitor() is not None:
        return redirect(_safe_next())

    form = VisitorRegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        visitor = Visitor(
            email=email,
            display_name=form.display_name.data.strip(),
            organization=(form.organization.data or "").strip() or None,
        )
        visitor.set_password(form.password.data)
        visitor.touch_login(client_ip_hash())
        db.session.add(visitor)
        db.session.commit()

        sign_in(visitor, remember=bool(form.remember.data))

        flash("حساب شما ساخته شد. حالا می‌توانید نمونه‌ها را ببینید.", "success")
        return redirect(_safe_next())

    return render_template("public/account_register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("8 per minute;40 per hour")
def login():
    """A visitor comes back."""
    if current_visitor() is not None:
        return redirect(_safe_next())

    form = VisitorLoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        visitor = Visitor.query.filter(
            func.lower(Visitor.email) == email
        ).first()
        if visitor and visitor.is_active and visitor.check_password(form.password.data):
            visitor.touch_login(client_ip_hash())
            db.session.commit()
            sign_in(visitor, remember=bool(form.remember.data))
            flash(f"خوش آمدید، {visitor.display_name}.", "success")
            return redirect(_safe_next())
        flash("نشانی رایانامه یا رمز عبور درست نیست.", "error")

    return render_template("public/account_login.html", form=form)


@bp.post("/logout")
def logout():
    """A visitor leaves."""
    sign_out()
    flash("از حساب خود خارج شدید.", "success")
    return redirect(url_for("public.home"))


@bp.get("/")
def account():
    """The account of the visitor, with the samples it has opened."""
    visitor = current_visitor()
    if visitor is None:
        return redirect(url_for("account.login", next=url_for("account.account")))

    opened = (
        db.session.query(SampleAccess)
        .options(joinedload(SampleAccess.live_link), joinedload(SampleAccess.product))
        .filter(SampleAccess.visitor_id == visitor.id)
        .order_by(SampleAccess.opened_at.desc())
        .all()
    )
    return render_template("public/account.html", visitor=visitor, opened=opened)


# ---------------------------------------------------------------------------
# The samples
# ---------------------------------------------------------------------------


@samples_bp.get("/<int:link_id>")
def sample(link_id: int):
    """A sample of a product.

    The sample is only given to a visitor who has signed in. When the
    visitor has not signed in, the sign-in page is shown and the visitor
    comes back to the sample afterwards.
    """
    link = (
        db.session.query(PortfolioLiveLink)
        .options(joinedload(PortfolioLiveLink.portfolio), joinedload(PortfolioLiveLink.product))
        .filter(PortfolioLiveLink.id == link_id)
        .first_or_404()
    )

    # A sample that is not published, or whose sample is not published
    # either, is not there at all.
    if not link.is_published or not link.portfolio or not link.portfolio.is_published:
        abort(404)

    visitor = current_visitor()
    if visitor is None and link.requires_login:
        flash("برای باز کردن نمونهٔ زنده، نخست وارد شوید.", "warning")
        # The address of the sample is kept, so that the visitor comes
        # back to it after the sign-in. The trailing question mark of
        # the full path is left away.
        return redirect(url_for("account.login", next=request.full_path.rstrip("?")))

    # The opening is written down, so that the administrator can see
    # which samples are used. Every opening is kept in the record, but
    # the counter of the sample counts the people and not the visits,
    # so that a visitor who refreshes the page does not make the
    # sample look busier than it is.
    if visitor is not None:
        # The question is asked before the new opening is added, so
        # that the row that is being added is not counted as an older
        # one.
        seen_before = (
            db.session.query(SampleAccess.id)
            .filter(SampleAccess.visitor_id == visitor.id,
                    SampleAccess.live_link_id == link.id)
            .first()
        )
        db.session.add(SampleAccess(
            visitor_id=visitor.id,
            live_link_id=link.id,
            product_id=link.product_id,
            ip_hash=client_ip_hash(),
        ))
        if seen_before is None:
            link.open_count = (link.open_count or 0) + 1
        db.session.commit()

    related = []
    if link.product_id:
        product = db.session.get(Product, link.product_id)
        if product is not None and product.status == "published":
            related = product

    return render_template(
        "public/sample.html", link=link, visitor=visitor, related=related,
    )
