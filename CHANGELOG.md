# تغییرات

## [1.1.0] — 2026-11-09

### امنیت و قراردادها

- پاک‌سازی مرکزی ورودی متنی/HTML و مسدودسازی Stored XSS در همه ابزارهای REST و MCP.
- پیش‌بررسی وجود رکورد پیش از ساخت Approval؛ خطای `not_found` برای شناسه ناموجود و `no_changes` برای Update خالی.
- خطاهای ساختاریافته فارسی/انگلیسی با `request_id` و `X-Request-ID`، CORS مبتنی بر `TRUSTED_ORIGINS`، هدرهای Agent/Global Rate Limit و HTTPS/HSTS اختیاری با `ENFORCE_HTTPS=true`.
- `Idempotency-Key` برای سازگاری ایمن عملیات `create_*`؛ تکرار پاسخ و تشخیص تضاد Payload. نسخه سازگاری بدون کلید هنوز با `Deprecation` پشتیبانی می‌شود.
- JWT پانزده‌دقیقه‌ای، Refresh Token یک‌بارمصرف و چرخشی، لغو و چرخش اعتبار از REST؛ احراز هویت `/tools` حفظ شده است.

### صفحه و محصول

- افزودن `custom_css` و `custom_js` تا ۵۰٬۰۰۰ نویسه به ایجاد/ویرایش/دریافت صفحه، مسدودسازی JavaScript پرخطر و پیش‌نمایش ترکیبی با Nonce.
- ویرایش صفحه Published در اتصال‌های نیازمند تأیید، Pending می‌شود؛ ویرایش Draft مستقیم است.
- افزودن فیلدهای قیمت، ارز، لینک دمو/مستندات، جشنواره، بازدید و Agent ویرایش‌کننده به محصول بدون حذف فیلدهای قبلی.
- `add_menu_item` اکنون `page_id` یا `url` امن (HTTPS یا مسیر داخلی) را می‌پذیرد و نام مستعار `header` را به `main` تبدیل می‌کند.

### رسانه

- آپلود JPEG/PNG/WebP/SVG تا ۵MB با اعتبارسنجی محتوا و Magic Bytes، تبدیل تصاویر Raster به WebP و ساخت Variantهای ۲۵۶/۵۱۲/۱۰۲۴.
- اتصال/جدا کردن رسانه، انتخاب واقعی لوگو/کاور و گالری، پاسخ تصویری کامل در محصول و نمایش عمومی همان فایل‌ها.
- جلوگیری از حذف رسانه متصل با `409 conflict` و soft-delete رسانه‌ها هنگام حذف محصول.

### API و MCP

- فیلتر، مرتب‌سازی، Cursor/Offset و Total برای فهرست محصول، صفحه، نمونه‌کار، رسانه، محتوا و Audit. حالت بدون pagination موقتاً با Header `Deprecation` حفظ شده است.
- مسیرهای GET خواندنی `/products`، `/pages`، `/portfolio`، `/media`، `/content` و `/activity` افزوده شدند؛ ابزارهای POST قبلی حفظ شده‌اند.
- OpenAPI 3.1 در `/openapi.json`، Swagger UI در `/docs` و کشف MCP در `/.well-known/mcp.json`.
- افزودن Resource دینامیک محصول/صفحه، Promptهای خلاصه/شفافیت/جشنواره و Rate Limit مستقل MCP؛ SDK رسمی و Streamable HTTP حفظ شده‌اند.

### دیتابیس و آزمون

- Migration `a69c5352e3c7` برای فیلدهای محصول/رسانه، Idempotency و Refresh Token افزوده شد.
- آزمون‌های رگرسیون XSS، Approval، کد صفحه، آپلود، pagination، CORS، Idempotency، JWT و Resource/Prompt رسمی MCP اضافه شدند.
