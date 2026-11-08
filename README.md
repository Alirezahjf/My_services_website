# راهکارهای نرم‌افزاری HJF

وب‌سایت فارسی و راست‌چین برای معرفی محصولات نرم‌افزاری، ابزارهای هوش مصنوعی، اتوماسیون و خدمات دیجیتال؛ ساخته‌شده با **Flask، SQLAlchemy و Jinja2** و متصل به پایگاه داده واقعی. این پروژه فقط یک قالب نیست: کاتالوگ، صفحات محصول، CMS، کتابخانه رسانه، نمونه‌کارها، فرم‌های تماس/مشاوره، مدیریت سرنخ فروش و همگام‌سازی فقط‌خواندنی GitHub پیاده‌سازی شده‌اند.

## امکانات

- طراحی واکنش‌گرا و کاملاً RTL با فونت محلی Vazirmatn و ۱۷ لوگوی SVG اختصاصی.
- کاتالوگ متصل به دیتابیس با جست‌وجو، فیلتر دسته/نوع، محصولات منتخب، مرتب‌سازی و صفحه‌بندی.
- صفحه کامل هر محصول: قابلیت‌های تأییدشده، کاربردها، مخاطبان، پیش‌نیازها، محدودیت‌ها، فناوری، رسانه و FAQ.
- انتشار کنترل‌شده با وضعیت‌های پیش‌نویس، نیازمند بررسی، در حال توسعه، آماده ارائه، منتشرشده و آرشیوشده.
- پنل مدیریت فارسی برای محصولات، دسته‌ها، قابلیت‌ها، نمونه‌کارها، رسانه‌ها، محتوای صفحات، FAQ، برند، فرایند همکاری و شبکه‌های اجتماعی.
- آپلود چندتصویری، ویدئو و PDF با نام UUID، بررسی محتوا، Thumbnail برای تصاویر و پاک‌سازی SVG.
- فرم تماس، درخواست مشاوره/دمو و سفارش راهکار اختصاصی؛ ذخیره در دیتابیس، پیگیری وضعیت، یادداشت داخلی و خروجی CSV امن.
- گزارش مهندسی هر ۱۶ مخزن در پنل مدیریت، همراه Commit مبنای بررسی.
- دریافت اطلاعات GitHub به‌صورت فقط‌خواندنی، مقایسه Commit/README/Release و ثبت تغییرات برای تأیید مدیر؛ بدون بازنویسی خودکار محتوای عمومی.
- CSRF، هش Scrypt رمز عبور، محدودیت نرخ ورود و فرم‌ها، Session امن، CSP و سایر Headerهای امنیتی.
- Sitemap، Robots، Canonical، Open Graph و داده ساختاریافته واقعی برای محصولات.
- SQLite برای توسعه، PostgreSQL برای عملیات، Alembic Migration، Docker، Gunicorn و نمونه Nginx.

## شروع سریع روی Ubuntu

### ۱. پیش‌نیازها

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

### ۲. دریافت و نصب پروژه

```bash
git clone https://github.com/Alirezahjf/My_services_website.git
cd My_services_website
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

مقدار `SECRET_KEY` را در `.env` با یک رشته تصادفی قوی تغییر دهید:

```bash
python -c 'import secrets; print(secrets.token_hex(32))'
```

هیچ رمز مدیر یا توکنی در کد قرار ندارد. پورت پیش‌فرض `9900` و آدرس اجرا `0.0.0.0` است.

### ۳. ساخت دیتابیس، داده اولیه و مدیر

```bash
flask --app run.py db upgrade
flask --app run.py seed-content
flask --app run.py create-admin
```

دستور آخر نام کاربری و رمز را به‌صورت تعاملی می‌گیرد. رمز باید حداقل ۱۲ نویسه باشد. `seed-content` تکرارپذیر است و متن‌های تجاری ویرایش‌شده را بازنویسی نمی‌کند؛ گزارش فنی داخلی را با مبنای بررسی به‌روز می‌کند.

### ۴. اجرا

```bash
python run.py
```

- سایت: `http://SERVER_IP:9900`
- ورود مدیریت: `http://SERVER_IP:9900/admin/login`

برای تغییر پورت، `PORT` را در `.env` تغییر دهید.

## اجرای عملیاتی با Gunicorn

از Flask Development Server در عملیات استفاده نکنید:

```bash
gunicorn -w 4 -b 0.0.0.0:9900 "app:create_app()"
```

نمونه سرویس systemd و Nginx در پوشه `deploy/` قرار دارد. قبل از عمومی‌کردن سایت:

1. `SECRET_KEY` تصادفی و قوی تنظیم شود.
2. `COOKIE_SECURE=true` و `SITE_URL=https://your-domain.ir` تنظیم شود.
3. HTTPS با Certbot فعال شود.
4. PostgreSQL و Redis برای Rate Limit چند Worker پیکربندی شود.
5. مالکیت `instance/uploads` و دیتابیس محدود به کاربر سرویس باشد.
6. پشتیبان‌گیری و بازیابی آزمون شود.

## PostgreSQL

```env
DATABASE_URL=postgresql+psycopg://services:STRONG_PASSWORD@127.0.0.1/services
RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0
COOKIE_SECURE=true
SITE_URL=https://your-domain.ir
```

پس از تغییر DSN، `flask --app run.py db upgrade` را اجرا کنید. انتقال داده از SQLite به PostgreSQL را ابتدا روی نسخه آزمایشی انجام دهید.

## Docker

```bash
cp .env.example .env
# SECRET_KEY را تغییر دهید و مدیر را پس از اجرا بسازید
docker compose up -d --build
docker compose exec web flask --app run.py db upgrade
docker compose exec web flask --app run.py seed-content
docker compose exec web flask --app run.py create-admin
```

Volumeهای `app-data` و `uploads` اطلاعات را نگه می‌دارند. برای PostgreSQL عملیاتی می‌توانید سرویس دیتابیس خود را به Compose اضافه کنید.

## GitHub Sync

توکن اختیاری است؛ برای مخازن عمومی بدون آن هم می‌توان از API با سهمیه کمتر استفاده کرد:

```env
GITHUB_TOKEN=github_read_only_token
GITHUB_API_URL=https://api.github.com
GITHUB_TIMEOUT=20
```

توکن فقط از Environment خوانده می‌شود و در دیتابیس، HTML یا Log ذخیره نمی‌شود. در پنل، مسیر **GitHub و تحلیل مخازن** امکان بررسی هر مخزن را می‌دهد. تغییر Commit، SHA فایل README و Release در `pending_changes` ثبت می‌شود. دکمه «بررسی شد» فقط گزارش را می‌بندد و هیچ محتوایی را جایگزین نمی‌کند. قطع GitHub هیچ اثری بر اجرای صفحات عمومی ندارد.

## راهنمای مدیریت محتوا

1. **محصول جدید:** نام تجاری، مخزن، دسته، نوع، توضیحات سه‌سطحی، قابلیت‌ها و پیش‌نیازها را وارد کنید.
2. **ذخیره بدون انتشار:** وضعیت را روی «پیش‌نویس» نگه دارید و از «پیش‌نمایش» استفاده کنید.
3. **انتشار:** فقط پس از تأیید اطلاعات، وضعیت «منتشرشده» را انتخاب کنید. انتخاب «صفحه اصلی» محصول را به بخش منتخب خانه می‌آورد.
4. **قابلیت‌ها:** از منوی قابلیت‌ها، موارد واقعی را به محصول متصل کنید. قابلیت ناتمام را با وضعیت در حال توسعه/نیازمند بررسی مشخص کنید.
5. **رسانه:** تصویر، حداکثر ۲۰ تصویر در هر بار، یک ویدئو یا یک PDF را به محصول/نمونه‌کار متصل کنید. Mockupها را با گزینه مربوط علامت بزنید.
6. **نمونه‌کار:** ابتدا نمونه‌کار و ارتباط آن با محصول/دسته را بسازید، سپس رسانه واقعی اضافه و منتشر کنید.
7. **محتوای صفحه:** شناسه‌های صفحه/بخش در صفحه مدیریت محتوا فهرست شده‌اند. HTML فقط با تگ‌های امن پذیرفته می‌شود.
8. **درخواست‌ها:** از بخش سرنخ‌ها یا پیام‌ها وضعیت پیگیری و یادداشت داخلی ثبت کنید. خروجی CSV در برابر CSV Injection محافظت می‌شود.
9. **برند:** نام، لوگو، ایمیل، تلفن، فوتر، Copyright و SEO پیش‌فرض از پنل قابل تغییر است.

## تست و کنترل کیفیت

```bash
pytest
# یا با گزارش پوشش:
pytest --cov=app --cov-report=term-missing
```

نسخه فعلی شامل **۲۴ تست خودکار** برای صفحات عمومی، انتشار، جست‌وجو/فیلتر، فرم‌ها، احراز هویت، CRUD، آپلود معتبر و مخرب، آپلود چندتصویری، Sanitization، CSRF، Headerهای امنیتی، CSV و خطا/تغییرات GitHub است. تست‌های GitHub با Mock اجرا می‌شوند و به شبکه وابسته نیستند.

## پشتیبان‌گیری و بازیابی

اسکریپت کمکی:

```bash
bash scripts/backup.sh
```

خروجی در `backups/YYYYMMDD-HHMMSS/` شامل SQLite (با روش `.backup`)، فایل‌های رسانه و Manifest است. پوشه `backups/` در Git ذخیره نمی‌شود.

بازیابی را ابتدا روی محیط آزمایشی انجام دهید:

```bash
cp backups/DATE/services.sqlite3 instance/services.sqlite3
rm -rf instance/uploads
cp -a backups/DATE/uploads instance/uploads
flask --app run.py db upgrade
```

برای PostgreSQL از `pg_dump` و `pg_restore` مطابق مستندات رسمی استفاده کنید و از Volume رسانه نیز جداگانه نسخه بگیرید. فایل `.env` را امن و جدا از بکاپ عمومی نگه دارید.

## ساختار پروژه

```text
app/
├── public/             # صفحات عمومی و فرم‌های مشتری
├── admin/              # احراز هویت و مدیریت کامل محتوا
├── models/             # مدل‌های SQLAlchemy و روابط
├── services/           # آپلود امن، ابزار و Activity Log
├── github_sync/        # کلاینت فقط‌خواندنی و ثبت تفاوت‌ها
├── templates/          # قالب‌های عمومی، مدیریت و خطا
└── static/             # CSS/JS/فونت/لوگوهای SVG محلی
migrations/             # Migrationهای Alembic
scripts/                # Seed و Backup
deploy/                 # systemd و Nginx
tests/                  # تست‌های خودکار
docs/                   # گزارش مهندسی مخازن و راهنما
```

## محدودیت‌های شفاف نسخه

- درگاه پرداخت، فروش آنلاین، وبلاگ و سیستم تیکت عمداً اضافه نشده‌اند؛ در محدوده نسخه اول نبودند.
- ارسال ایمیل خودکار انجام نمی‌شود؛ درخواست‌ها به‌صورت پایدار در پنل ذخیره و پیگیری می‌شوند.
- سرویس‌های AI، پیام‌رسان یا Scraping محصولات معرفی‌شده اجرا نشده‌اند؛ این سایت کاتالوگ آن‌هاست. ادعاهای هر محصول بر اساس کد مخزن خودش ثبت شده است.
- فونت Vazirmatn تحت SIL Open Font License استفاده می‌شود؛ متن مجوز در `app/static/fonts/OFL.txt` قرار دارد.

گزارش کامل ۱۶ مخزن: [`docs/REPOSITORY_ANALYSIS.md`](docs/REPOSITORY_ANALYSIS.md).
