from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileSize
from wtforms import BooleanField, EmailField, HiddenField, PasswordField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp, ValidationError
from app.services.utils import normalize_digits


def valid_phone(form, field):
    value = normalize_digits(field.data).replace(" ", "").replace("-", "")
    if not 7 <= len(value.lstrip("+")) <= 15 or not __import__("re").fullmatch(r"\+?\d+", value):
        raise ValidationError("شماره تماس معتبر نیست.")


class HoneypotMixin:
    website = HiddenField("وب‌سایت")

    def validate_website(self, field):
        if field.data:
            raise ValidationError("ارسال فرم نامعتبر است.")


class ContactForm(FlaskForm, HoneypotMixin):
    name = StringField("نام و نام خانوادگی", validators=[DataRequired(), Length(max=160)])
    phone = StringField("شماره تماس", validators=[DataRequired(), valid_phone])
    email = EmailField("ایمیل (اختیاری)", validators=[Optional(), Email(), Length(max=180)])
    subject = StringField("موضوع", validators=[DataRequired(), Length(max=200)])
    message = TextAreaField("متن پیام", validators=[DataRequired(), Length(min=10, max=5000)])


class ConsultationForm(FlaskForm, HoneypotMixin):
    name = StringField("نام", validators=[DataRequired(), Length(max=160)])
    phone = StringField("شماره تماس", validators=[DataRequired(), valid_phone])
    email = EmailField("ایمیل (اختیاری)", validators=[Optional(), Email(), Length(max=180)])
    product_id = SelectField("محصول موردنظر", coerce=int, validators=[Optional()])
    request_type = SelectField("نوع درخواست", choices=[("consultation", "مشاوره"), ("demo", "درخواست دمو"), ("order", "سفارش و اطلاعات بیشتر")])
    message = TextAreaField("توضیحات تکمیلی", validators=[Optional(), Length(max=5000)])


class CustomSolutionForm(FlaskForm, HoneypotMixin):
    organization = StringField("نام مجموعه", validators=[DataRequired(), Length(max=180)])
    name = StringField("نام درخواست‌دهنده", validators=[DataRequired(), Length(max=160)])
    phone = StringField("شماره تماس", validators=[DataRequired(), valid_phone])
    email = EmailField("ایمیل (اختیاری)", validators=[Optional(), Email(), Length(max=180)])
    industry = StringField("حوزه فعالیت", validators=[DataRequired(), Length(max=160)])
    need_type = StringField("نوع نیاز", validators=[DataRequired(), Length(max=160)])
    message = TextAreaField("توضیحات پروژه", validators=[DataRequired(), Length(min=20, max=8000)])
    budget = StringField("بودجه تقریبی (اختیاری)", validators=[Optional(), Length(max=100)])
    attachment = FileField("پیوست PDF (اختیاری)", validators=[Optional(), FileAllowed(["pdf"], "فقط فایل PDF مجاز است."), FileSize(max_size=10 * 1024 * 1024)])


# ---------------------------------------------------------------------------
# The account of the visitor
#
# It is kept here, beside the other forms of the public side, because it
# belongs to the visitor and not to the manager.
# ---------------------------------------------------------------------------


class VisitorEmailMixin:
    """The address of a visitor.

    The address is folded to small letters before it is checked, so that
    ``Ali@Example.com`` and ``ali@example.com`` are the same account and
    not two of them.
    """

    def process_data(self, data):
        if isinstance(data, dict) and data.get("email"):
            data = dict(data)
            data["email"] = str(data["email"]).strip().lower()
        return super().process_data(data)


class VisitorRegisterForm(VisitorEmailMixin, FlaskForm, HoneypotMixin):
    """The form of a visitor who wants to try a sample."""

    display_name = StringField("نام شما", validators=[DataRequired(), Length(min=2, max=120)])
    email = EmailField("نشانی رایانامه", validators=[DataRequired(), Email(), Length(max=190)])
    organization = StringField("سازمان یا تیم (اختیاری)", validators=[Optional(), Length(max=160)])
    password = PasswordField("رمز عبور", validators=[DataRequired(), Length(min=8, max=200)])
    confirm_password = PasswordField("تکرار رمز عبور", validators=[
        DataRequired(), EqualTo("password", message="تکرار رمز عبور یکسان نیست."),
    ])
    remember = BooleanField("مرا به خاطر بسپار")

    def validate_email(self, field):
        """The address must be free, and it is compared without regard to
        the case of the letters."""
        from app.extensions import db
        from app.models import Visitor
        email = (field.data or "").strip().lower()
        if not email:
            return
        taken = Visitor.query.filter(db.func.lower(Visitor.email) == email).first()
        if taken:
            raise ValidationError("با این نشانی رایانامه قبلاً ثبت‌نام کرده‌اید.")


class VisitorLoginForm(VisitorEmailMixin, FlaskForm):
    """The form of a visitor who comes back."""

    email = EmailField("نشانی رایانامه", validators=[DataRequired(), Email(), Length(max=190)])
    password = PasswordField("رمز عبور", validators=[DataRequired(), Length(max=200)])
    remember = BooleanField("مرا به خاطر بسپار")
