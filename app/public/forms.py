from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileSize
from wtforms import EmailField, HiddenField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional, Regexp, ValidationError
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
