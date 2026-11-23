# دستور آپدیت RunUp

## فایل‌های ظاهر در آپدیت ساخته می‌شوند

شیوه‌نامه و اسکریپت سایت از روی منبع خوانایشان ساخته می‌شوند:

- `app/static/css/site.src.css` → `app/static/css/main.css`
- `app/static/js/site.src.js` → `app/static/js/main.js`

این کار در مرحلهٔ آپدیت، پس از نصب وابستگی‌ها و پیش از بالا آمدن سرویس‌ها انجام می‌شود. اگر خواستید دستی بررسی کنید که فایل ساخته‌شده با منبع هم‌خوان است:

```
python tools/build_assets.py --check
```

---

## چه اتفاقی افتاد

دستور قبلی روی سرور نیمه‌کاره اجرا شد:

```
git fetch origin
git checkout arena/5096b461-my-services-website
```

`git fetch` موفق بود و شاخه درست را گرفت، اما **`git checkout` درخت کاری را به‌روز نکرد**؛ چون شاخه محلی با شاخه دورراه واگرا بود (۷ commit محلی در برابر ۴ commit دور)، و در نتیجه `scripts/setup_runup.sh` روی دیسک نبود و دستور آخر گفت:

```
bash: scripts/setup_runup.sh: No such file or directory
```

پیام «leaving 3 commits behind» هم بی‌خطر بود: آن سه commit فقط در شاخه قدیمی محلی سرور بودند و در نسخه جدید جایگزین شده‌اند.

---

## دستور کامل

این بلوک را **یک‌جا** کپی و اجرا کنید:

```bash
cd /opt/hjf-services && sudo bash -c '
git fetch origin refs/heads/arena/6e2e1efe-my-services-website:refs/remotes/origin/arena/6e2e1efe-my-services-website &&
git checkout -B arena/6e2e1efe-my-services-website origin/arena/6e2e1efe-my-services-website &&
git reset --hard origin/arena/6e2e1efe-my-services-website &&
bash scripts/setup_runup.sh'
```

### چرا شاخه با نام کامل نوشته می‌شود

`git fetch origin <نام-شاخه>` فقط یک یادداشت در `FETCH_HEAD` می‌گذارد و شاخهٔ
`origin/<نام>` را **نمی‌سازد**، مگر آنکه `remote.origin.fetch` در مخزن سرور
همان شاخه را پوشش دهد. روی سرور آن تنظیم نبود، و به همین دلیل خطای زیر
می‌آمد:

```
fatal: 'origin/arena/6e2e1efe-my-services-website' is not a commit ...
```

نوشتن شاخه با نام کامل (`refs/heads/...:refs/remotes/origin/...`) شاخهٔ
دورراه را می‌سازد و دستور بعدی کار می‌کند. خودِ `scripts/setup_runup.sh` هم
از همین شکل استفاده می‌کند، پس از این پس یک‌بار درست شدن کافی است.

### اگر باز هم نخواست

```bash
cd /opt/hjf-services && sudo bash -c '
git fetch origin arena/6e2e1efe-my-services-website &&
git checkout -B arena/6e2e1efe-my-services-website FETCH_HEAD &&
git reset --hard FETCH_HEAD &&
bash scripts/setup_runup.sh'
```

`FETCH_HEAD` از همان fetch ساخته می‌شود و همیشه در دسترس است.

### اگر می‌خواهید این مشکل برای همیشه تمام شود

```bash
cd /opt/hjf-services && git config --add remote.origin.fetch \
  '+refs/heads/arena/6e2e1efe-my-services-website:refs/remotes/origin/arena/6e2e1efe-my-services-website'
```

---

## وقتی صفحه سیاه دیده می‌شود

اگر سایت بالا آمد ولی چیزی دیده نمی‌شود، این اسکریپت را اجرا کنید. فقط
می‌خواند و هیچ چیز را تغییر نمی‌دهد:

```bash
cd /opt/hjf-services && sudo bash tools/diagnose_site.sh
```

گزارش آن نشان می‌دهد کدام commit روی دیسک است، فایل‌های ساخته‌شده چه
اندازه‌اند، سرویس‌ها چه جوابی می‌دهند و مرورگر چه سربرگ‌هایی می‌گیرد.

دو چیز در آن گزارش ارزش نگاه کردن دارد:

- **پاسخی که یک گوشی می‌گیرد.** گوشی‌ها فشرده‌سازی brotli را می‌خواهند. اگر
  سرور بگوید `br` ولی بایت‌های gzip بفرستد، مرورگر شیوه‌نامه را نمی‌خواند و
  صفحه **کاملاً خالی** می‌ماند، بدون هیچ پیامی. گزارش می‌گوید نام چیست و
  بایت‌های اول چیست.
- **شمارهٔ روی نشانی فایل‌های ظاهر.** نشانی شیوه‌نامه و اسکریپت باید یک
  شمارهٔ یکسان داشته باشند: `/static/css/main.css?v=...` و
  `/static/js/main.js?v=...`. اگر شماره نداشته باشند، مرورگر فایل کهنه را یک
  سال نگه می‌دارد و صفحه با قاعده‌های یک نسخهٔ دیگر باز می‌شود.
- **اندازهٔ `main.css` و `main.js`.** اگر صفر باشند یا خیلی کوچک، ساخت
  فایل‌های ظاهر نیمه‌کاره مانده است.

---

## اگر `.env` وجود ندارد

اسکریپت بدون `.env` نمی‌دواند و پیام فارسی می‌دهد:

```
[RunUp] خطا: فایل .env پیدا نشد؛ این اسکریپت فایل تنظیمات موجود را تغییر نمی‌دهد.
```

در آن صورت یک `.env` بسازید (این فایل در Git نیست و روی سرور می‌ماند):

```bash
cd /opt/hjf-services
cp .env.example .env
chown services:services .env
chmod 0640 .env
sudo bash scripts/setup_runup.sh
```

اسکریپت خودش `HTTPS_PUBLIC_PORT`، `HTTP_PUBLIC_PORT`، `SITE_URL`، `PUBLIC_ORIGIN`، `COOKIE_SECURE` و `TLS_CERT_PATH` را در `.env` می‌نویسد.

---

## اگر گواهی همسایه پیدا نشد

اسکریپت هشدار فارسی می‌دهد و سایت را روی HTTP بالا می‌گذارد (سکو نمی‌افتد):

```
[RunUp] هشدار: گواهی معتبر برای 212.237.217.171 پیدا نشد؛ سایت روی HTTP بالا می‌ماند و خودش دوباره بررسی می‌کند.
```

در آن حالت مسیر واقعی گواهی را دستی بدهید:

```bash
sudo bash scripts/setup_runup.sh CERT_PATH=/path/to/data/tls/trusted.pem
```

مسیر را پیدا کنید (پوشه همسایه فقط خوانده می‌شود):

```bash
find / -name trusted.pem -path '*tls*' 2>/dev/null
```

---

## وقتی گواهی زیر پوشه‌ای بسته باشد

اگر گواهی همسایه زیر پوشه‌ای باشد که کاربر `services` نمی‌تواند واردش شود —
برای نمونه زیر `/root` — اسکریپت این کار را **خودش** انجام می‌دهد:

1. گواهی را با دسترسی خودش می‌خواند
2. از آن یک رونوشت در `instance/tls/` پروژه خودمان می‌گیرد
3. مالکیت رونوشت را به کاربر سرویس می‌دهد (کلید خصوصی فقط برای او خوانا)

**مجوز هیچ پوشه‌ای در پروژه همسایه تغییر نمی‌کند.** سرویس از رونوشت خودش
استفاده می‌کند و دیگر فایل همسایه را نمی‌خواند.

اگر باز هم گواهی پیدا نشد، این پیام را می‌بینید:

```
[RunUp] هشدار: گواهی معتبر برای 212.237.217.171 پیدا نشد؛ سایت روی HTTP بالا می‌ماند و خودش دوباره بررسی می‌کند.
```

در آن صورت مسیر را دستی بدهید (همان دستور بالا).

---

## گزارش وضعیت

```bash
sudo -u services /opt/hjf-services/.venv/bin/flask --app run.py status
```

خروجی وقتی HTTPS روشن است:

```
وضعیت سایت RunUp
─────────────────
نشانی سایت: https://212.237.217.171:9900
HTTPS: روشن
اعتبار گواهی: ...
منبع گواهی: /path/to/data/tls/trusted.pem
درگاه HTTPS: 9900
لینک قدیمی HTTP: درگاه 19900 (به نشانی امن هدایت می‌شود)
```

---

## نشانی‌های نهایی

| نشانی | توضیح |
|---|---|
| `https://212.237.217.171:9900` | نشانی اصلی و امن |
| `http://212.237.217.171:19900` | لینک قدیمی؛ در مرورگر به نشانی امن می‌رود |

اگر درگاه ۹۹۰۰ از قبل اشغال باشد، اسکریپت خودش یک درگاه آزاد دیگر انتخاب می‌کند و همان را در `flask status` گزارش می‌دهد.

---

## چه چیزی دست‌نخورده می‌ماند

اسکریپت عمداً این کارها را **نمی‌کند**:

- nginx / apache / Caddy نصب نمی‌کند
- درگاه‌های ۸۰ و ۴۴۳ را نمی‌گیرد و به آن‌ها دست نمی‌زند
- فایروال را فعال، ریست یا خالی نمی‌کند
- پردازه‌ای را که خودش نساخته متوقف نمی‌کند
- فایل `.env`، پایگاه داده و `uploads` را دست نمی‌زند
- در پوشه همسایه چیزی نمی‌نویسد؛ فایل گواهی را فقط می‌خواند
