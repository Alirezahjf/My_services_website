from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, MultipleFileField
from wtforms import BooleanField, DateField, IntegerField, PasswordField, SelectField, SelectMultipleField, StringField, TextAreaField
from wtforms.validators import DataRequired, EqualTo, Length, NumberRange, Optional, URL, ValidationError
from app.models import Product

IMAGE_TYPES = ["jpg", "jpeg", "png", "webp", "gif", "svg"]


class LoginForm(FlaskForm):
    username = StringField("نام کاربری", validators=[DataRequired(), Length(max=80)])
    password = PasswordField("رمز عبور", validators=[DataRequired(), Length(max=200)])


class PasswordForm(FlaskForm):
    current_password = PasswordField("رمز عبور فعلی", validators=[DataRequired()])
    new_password = PasswordField("رمز عبور جدید", validators=[DataRequired(), Length(min=12, max=200), EqualTo("confirm_password", message="تکرار رمز عبور یکسان نیست.")])
    confirm_password = PasswordField("تکرار رمز عبور جدید", validators=[DataRequired()])


class ProductForm(FlaskForm):
    name = StringField("نام تجاری محصول", validators=[DataRequired(), Length(max=160)])
    repository_name = StringField("نام مخزن", validators=[Optional(), Length(max=160)])
    slug = StringField("نامک (Slug)", validators=[Optional(), Length(max=180)])
    category_id = SelectField("دسته‌بندی اصلی", coerce=int, validators=[Optional()])
    category_ids = SelectMultipleField("دسته‌بندی‌های مکمل", coerce=int, validators=[Optional()])
    origin_type = SelectField("منشأ محصول", default="github", choices=[("github", "مبتنی بر GitHub"), ("independent", "محصول مستقل"), ("custom", "محصول سفارشی"), ("hybrid", "ترکیبی از چند مخزن")])
    commercial_status = SelectField("وضعیت تجاری", default="development", choices=[("concept", "معرفی اولیه / Concept"), ("development", "در حال توسعه"), ("ready", "آماده ارائه"), ("custom", "سفارش اختصاصی"), ("internal", "داخلی")])
    repository_enabled = BooleanField("همگام‌سازی مخزن فعال باشد")
    repository_url = StringField("نشانی مخزن (اختیاری)", validators=[Optional(), URL(), Length(max=255)])
    platforms_text = StringField("پلتفرم‌ها؛ جدا با ویرگول", validators=[Optional(), Length(max=500)])
    integration_status = SelectField("وضعیت یکپارچه‌سازی", default="not_applicable", choices=[("not_applicable", "بدون اتصال"), ("planned", "برنامه‌ریزی‌شده"), ("development", "در حال توسعه"), ("api_required", "نیازمند API"), ("ready", "آماده"), ("partial", "ناقص")])
    ai_enabled = BooleanField("موتور AI پیاده‌سازی شده است")
    automation_enabled = BooleanField("اتوماسیون پیاده‌سازی شده است")
    demo_available = BooleanField("دمو قابل استفاده موجود است")
    pricing_visibility = SelectField("نمایش قیمت", default="hidden", choices=[("on_request", "برآورد پس از بررسی"), ("visible", "قیمت قابل نمایش"), ("hidden", "عدم نمایش")])
    product_version = StringField("نسخه محصول", validators=[Optional(), Length(max=40)])
    release_date = DateField("تاریخ انتشار (اختیاری)", validators=[Optional()])
    product_type = SelectField("نوع محصول", choices=[("software", "نرم‌افزار"), ("ai", "هوش مصنوعی"), ("automation", "اتوماسیون"), ("library", "کتابخانه"), ("infrastructure", "زیرساخت"), ("service", "سرویس")])
    status = SelectField("وضعیت", choices=[("draft", "پیش‌نویس"), ("review", "نیازمند بررسی"), ("development", "در حال توسعه"), ("ready", "آماده ارائه"), ("published", "منتشرشده"), ("archived", "آرشیوشده")])
    development_status = StringField("وضعیت توسعه", validators=[Optional(), Length(max=120)])
    confidence = SelectField("اطمینان اطلاعات", choices=[("high", "زیاد"), ("medium", "متوسط"), ("low", "کم")])
    tagline = StringField("شعار", validators=[Optional(), Length(max=240)])
    short_description = TextAreaField("توضیح خیلی کوتاه", validators=[DataRequired(), Length(max=1200)])
    medium_description = TextAreaField("توضیح متوسط", validators=[Optional(), Length(max=5000)])
    full_description = TextAreaField("توضیح کامل", validators=[Optional(), Length(max=20000)])
    value_proposition = TextAreaField("ارزش پیشنهادی", validators=[Optional(), Length(max=3000)])
    problem_statement = TextAreaField("مسئله و راهکار", validators=[Optional(), Length(max=5000)])
    use_cases_text = TextAreaField("کاربردها؛ هر مورد در یک خط")
    target_audience_text = TextAreaField("مخاطبان؛ هر مورد در یک خط")
    prerequisites_text = TextAreaField("پیش‌نیازها؛ هر مورد در یک خط")
    limitations_text = TextAreaField("محدودیت‌ها؛ هر مورد در یک خط")
    technologies_text = TextAreaField("فناوری‌ها؛ هر مورد در یک خط")
    tags_text = StringField("برچسب‌ها؛ جدا با ویرگول", validators=[Optional(), Length(max=500)])
    accent_color = StringField("رنگ تأکیدی", validators=[Optional(), Length(max=20)])
    position = IntegerField("ترتیب نمایش", default=0, validators=[NumberRange(min=0, max=10000)])
    is_featured = BooleanField("محصول منتخب")
    show_on_home = BooleanField("نمایش در صفحه اصلی")
    logo = FileField("لوگو", validators=[Optional(), FileAllowed(IMAGE_TYPES, "فرمت لوگو مجاز نیست.")])
    cover = FileField("تصویر کاور", validators=[Optional(), FileAllowed(IMAGE_TYPES, "فرمت تصویر مجاز نیست.")])
    seo_title = StringField("عنوان SEO", validators=[Optional(), Length(max=180)])
    seo_description = TextAreaField("توضیح SEO", validators=[Optional(), Length(max=320)])


class CategoryForm(FlaskForm):
    name = StringField("نام فارسی", validators=[DataRequired(), Length(max=120)])
    english_name = StringField("نام انگلیسی", validators=[Optional(), Length(max=120)])
    slug = StringField("نامک", validators=[Optional(), Length(max=140)])
    description = TextAreaField("توضیح", validators=[Optional(), Length(max=3000)])
    icon = StringField("آیکون", default="sparkles", validators=[Optional(), Length(max=80)])
    position = IntegerField("ترتیب", default=0, validators=[NumberRange(min=0)])
    is_visible = BooleanField("نمایش در سایت", default=True)


class FeatureForm(FlaskForm):
    product_id = SelectField("محصول", coerce=int, validators=[DataRequired()])
    title = StringField("عنوان قابلیت", validators=[DataRequired(), Length(max=160)])
    description = TextAreaField("توضیح", validators=[Optional(), Length(max=3000)])
    example = TextAreaField("مثال کاربردی", validators=[Optional(), Length(max=3000)])
    icon = StringField("آیکون", default="check", validators=[Optional(), Length(max=80)])
    verification_status = SelectField("وضعیت قابلیت", choices=[("verified", "تأییدشده در کد"), ("implemented", "پیاده‌سازی‌شده"), ("development", "در حال توسعه"), ("planned", "برنامه‌ریزی‌شده"), ("api_required", "نیازمند API"), ("platform_approval", "نیازمند تأیید پلتفرم"), ("review", "نیازمند بررسی فنی"), ("unsupported", "پشتیبانی نمی‌شود")])
    position = IntegerField("ترتیب", default=0)
    is_published = BooleanField("منتشر شود", default=True)


class ConnectorForm(FlaskForm):
    product_id = SelectField("محصول", coerce=int, validators=[DataRequired()])
    platform = StringField("شناسه پلتفرم", validators=[DataRequired(), Length(max=80)], description="مثلاً telegram یا instagram")
    display_name = StringField("نام نمایشی", validators=[DataRequired(), Length(max=120)])
    adapter_key = StringField("کلید Adapter", validators=[Optional(), Length(max=120)])
    auth_method = StringField("روش احراز هویت", validators=[Optional(), Length(max=160)])
    connection_status = SelectField("وضعیت اتصال", choices=[("not_connected", "متصل نیست"), ("configuration_required", "نیازمند پیکربندی"), ("connected", "متصل"), ("error", "خطا"), ("disabled", "غیرفعال")])
    capability_status = SelectField("وضعیت قابلیت", choices=[("implemented", "پیاده‌سازی‌شده"), ("development", "در حال توسعه"), ("planned", "برنامه‌ریزی‌شده"), ("api_required", "نیازمند API"), ("platform_approval", "نیازمند تأیید پلتفرم"), ("review", "نیازمند بررسی"), ("unsupported", "پشتیبانی نمی‌شود")])
    supported_features_text = TextAreaField("قابلیت‌های پشتیبانی‌شده؛ هر مورد در یک خط")
    limitations_text = TextAreaField("محدودیت‌ها؛ هر مورد در یک خط")
    api_required = BooleanField("نیازمند API", default=True)
    approval_required = BooleanField("نیازمند تأیید پلتفرم")
    is_enabled = BooleanField("Connector فعال است")
    position = IntegerField("ترتیب", default=0)


class ModuleForm(FlaskForm):
    product_id = SelectField("محصول", coerce=int, validators=[DataRequired()])
    name = StringField("نام ماژول", validators=[DataRequired(), Length(max=160)])
    description = TextAreaField("توضیح", validators=[Optional(), Length(max=5000)])
    status = SelectField("وضعیت", choices=[("implemented", "پیاده‌سازی‌شده"), ("development", "در حال توسعه"), ("planned", "برنامه‌ریزی‌شده"), ("api_required", "نیازمند API"), ("review", "نیازمند بررسی")])
    position = IntegerField("ترتیب", default=0)


class MediaForm(FlaskForm):
    owner_type = SelectField("نوع اتصال", choices=[("product", "محصول"), ("portfolio", "نمونه‌کار")])
    owner_id = SelectField("محصول / نمونه‌کار", coerce=int, validators=[DataRequired()])
    title = StringField("عنوان", validators=[DataRequired(), Length(max=180)])
    description = TextAreaField("توضیح", validators=[Optional(), Length(max=3000)])
    alt_text = StringField("متن جایگزین", validators=[Optional(), Length(max=240)])
    media_type = SelectField("نوع رسانه", choices=[("image", "تصویر"), ("video", "ویدئو"), ("document", "PDF")])
    file = MultipleFileField("فایل رسانه؛ امکان انتخاب چند تصویر", validators=[DataRequired()])
    position = IntegerField("ترتیب", default=0)
    is_cover = BooleanField("کاور نمونه‌کار")
    is_mockup = BooleanField("تصویر نمایشی/Mockup است")
    is_published = BooleanField("منتشر شود", default=True)


class PortfolioForm(FlaskForm):
    title = StringField("عنوان", validators=[DataRequired(), Length(max=180)])
    slug = StringField("نامک", validators=[Optional(), Length(max=200)])
    summary = TextAreaField("خلاصه", validators=[Optional(), Length(max=3000)])
    description = TextAreaField("توضیح کامل", validators=[Optional(), Length(max=20000)])
    product_ids = SelectMultipleField("محصولات مرتبط", coerce=int, validators=[Optional()])
    category_ids = SelectMultipleField("دسته‌های مرتبط", coerce=int, validators=[Optional()])
    cover = FileField("کاور", validators=[Optional(), FileAllowed(IMAGE_TYPES, "فرمت تصویر مجاز نیست.")])
    position = IntegerField("ترتیب", default=0)
    is_published = BooleanField("منتشر شود")
    show_on_home = BooleanField("نمایش در صفحه اصلی")
    show_on_product = BooleanField("نمایش در محصول", default=True)
    show_in_gallery = BooleanField("نمایش در گالری", default=True)


class FAQForm(FlaskForm):
    product_id = SelectField("محصول (خالی = عمومی)", coerce=int, validators=[Optional()])
    question = StringField("پرسش", validators=[DataRequired(), Length(max=300)])
    answer = TextAreaField("پاسخ", validators=[DataRequired(), Length(max=10000)])
    position = IntegerField("ترتیب", default=0)
    is_published = BooleanField("منتشر شود", default=True)


class PageContentForm(FlaskForm):
    page_key = StringField("شناسه صفحه", validators=[DataRequired(), Length(max=100)])
    section_key = StringField("شناسه بخش", validators=[DataRequired(), Length(max=100)])
    title = StringField("عنوان", validators=[Optional(), Length(max=240)])
    subtitle = StringField("زیرعنوان", validators=[Optional(), Length(max=300)])
    body = TextAreaField("متن HTML امن", validators=[Optional(), Length(max=50000)])
    position = IntegerField("ترتیب", default=0)
    is_published = BooleanField("منتشر شود", default=True)


class SettingsForm(FlaskForm):
    brand_name = StringField("نام برند", validators=[DataRequired(), Length(max=160)])
    brand_tagline = StringField("شعار برند", validators=[Optional(), Length(max=300)])
    brand_description = TextAreaField("معرفی کوتاه", validators=[Optional(), Length(max=3000)])
    email = StringField("ایمیل", validators=[Optional(), Length(max=180)])
    phone = StringField("تلفن", validators=[Optional(), Length(max=60)])
    address = TextAreaField("نشانی", validators=[Optional(), Length(max=500)])
    website_url = StringField("نشانی وب‌سایت", validators=[Optional(), Length(max=300)])
    footer_text = TextAreaField("متن فوتر", validators=[Optional(), Length(max=3000)])
    copyright_text = StringField("کپی‌رایت", validators=[Optional(), Length(max=300)])
    default_seo_title = StringField("عنوان پیش‌فرض SEO", validators=[Optional(), Length(max=180)])
    default_seo_description = TextAreaField("توضیح پیش‌فرض SEO", validators=[Optional(), Length(max=320)])
    social_share_image = StringField("تصویر اشتراک‌گذاری", validators=[Optional(), Length(max=255)])
    logo = FileField("لوگوی برند", validators=[Optional(), FileAllowed(IMAGE_TYPES, "فرمت لوگو مجاز نیست.")])


class WorkflowForm(FlaskForm):
    title = StringField("عنوان مرحله", validators=[DataRequired(), Length(max=180)])
    description = TextAreaField("توضیح", validators=[Optional(), Length(max=2000)])
    icon = StringField("آیکون", default="arrow", validators=[Optional(), Length(max=80)])
    position = IntegerField("ترتیب", default=0)
    is_published = BooleanField("منتشر شود", default=True)


class ServiceForm(FlaskForm):
    title = StringField("عنوان خدمت", validators=[DataRequired(), Length(max=180)])
    description = TextAreaField("توضیح", validators=[Optional(), Length(max=3000)])
    icon = StringField("آیکون", default="workflow", validators=[Optional(), Length(max=80)])
    position = IntegerField("ترتیب", default=0)
    is_published = BooleanField("منتشر شود", default=True)


class SocialForm(FlaskForm):
    title = StringField("عنوان", validators=[DataRequired(), Length(max=100)])
    url = StringField("نشانی", validators=[DataRequired(), URL(), Length(max=500)])
    icon = StringField("آیکون", default="link", validators=[Optional(), Length(max=80)])
    position = IntegerField("ترتیب", default=0)
    is_published = BooleanField("منتشر شود", default=True)


class LeadUpdateForm(FlaskForm):
    status = SelectField("وضعیت پیگیری", choices=[("new", "جدید"), ("reviewing", "در حال بررسی"), ("call_needed", "نیازمند تماس"), ("negotiation", "مذاکره"), ("completed", "تکمیل‌شده"), ("archived", "بایگانی‌شده")])
    admin_note = TextAreaField("یادداشت داخلی", validators=[Optional(), Length(max=10000)])


class DeleteForm(FlaskForm):
    pass
