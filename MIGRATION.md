# راهنمای مهاجرت Agent API/MCP نسخه ۱٫۱

این نسخه مسیر `/api/agent/v1` و تمام ۴۳ ابزار اولیه را حفظ می‌کند. تغییرات عمداً افزایشی‌اند؛ خطاهای جدید فقط ورودی نامعتبر یا وضعیت ناسازگار را مشخص‌تر می‌کنند.

## ۱. ارتقای سرور

```bash
# ابتدا از دیتابیس و instance/uploads نسخه پشتیبان بگیرید
bash scripts/backup.sh
source .venv/bin/activate
pip install -r requirements.txt
flask --app run.py db upgrade
flask --app run.py db current
```

Head مورد انتظار `a69c5352e3c7` است. سرویس Flask/Gunicorn و سرویس مستقل MCP را پس از Migration راه‌اندازی کنید. داده‌های محصول موجود حفظ می‌شوند؛ نقش رسانه قبلی `gallery`، شمارش بازدید `۰` و وضعیت جشنواره `false` می‌شود.

## ۲. مهاجرت Listها

### ورودی قدیمی

```json
{"status":"published"}
```

این ورودی موقتاً کار می‌کند و Header `Deprecation: true` دارد، اما فهرست نا paginated است و برای کلاینت جدید توصیه نمی‌شود.

### ورودی جدید

```json
{"status":"published","limit":20,"sort":"updated_at","order":"desc"}
```

پاسخ جدید علاوه بر `result` دارای این بخش‌هاست:

```json
{
  "data": [],
  "pagination": {
    "total": 142,
    "next_cursor": "eyJvZmZzZXQiOjIwfQ",
    "has_more": true,
    "limit": 20
  }
}
```

برای صفحه بعد فقط `next_cursor` را همراه همان فیلترها بفرستید. از ساخت/رمزگشایی Cursor در کلاینت خودداری کنید. `offset` هم برای سازگاری پشتیبانی می‌شود. وضعیت نامعتبر دیگر فهرست خالی نمی‌دهد و `400 invalid_status` برمی‌گرداند.

مسیر GET معادل نیز در دسترس است:

```http
GET /api/agent/v1/products?limit=20&status=published&sort=updated_at&order=desc
Authorization: Bearer hjf_...
```

## ۳. Idempotency

برای هر `create_*` یک UUID تازه در Header بگذارید و در Retry شبکه همان UUID و Body را تکرار کنید:

```http
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```

پاسخ تکراری `Idempotent-Replay: true` دارد. استفاده از کلید قبلی با Body یا Tool متفاوت `409 conflict` است. نبود کلید در دوره سازگاری با Deprecation پذیرفته می‌شود، اما کلاینت‌های جدید باید همین حالا آن را ارسال کنند. MCP از جریان REST Idempotency عبور نمی‌کند.

## ۴. خطاها و Rate Limit

کلاینت باید `error.code` را بخواند، نه متن فارسی را. `error.message_en` برای پردازش انسانی انگلیسی و `error.request_id` برای پیگیری است. Headerهای `X-RateLimit-Agent-*` و `X-RateLimit-Global-*` جدا هستند. در `429` مقدار `Retry-After` را رعایت کنید.

CORS فقط Originهای لیست `TRUSTED_ORIGINS` (جدا شده با کاما) را می‌پذیرد. پس از فعال‌سازی Reverse Proxy صحیح HTTPS، `ENFORCE_HTTPS=true` تنظیم کنید؛ فعال‌سازی بدون Proxy مناسب می‌تواند Redirect نادرست ایجاد کند.

## ۵. توکن کوتاه‌مدت

اعتبار `hjf_` موجود همچنان معتبر است. برای کاهش عمر Secret در درخواست‌های معمولی:

1. با اعتبار فعلی `POST /auth/token` را بزنید.
2. `access_token` را حداکثر ۱۵ دقیقه و Refresh را امن نگه دارید.
3. پیش از انقضا `POST /auth/refresh` را با Refresh فعلی بزنید و هر دو مقدار جدید را جایگزین کنید.
4. Refresh قبلی پس از چرخش نامعتبر است. با 401 دوباره از `/auth/token` استفاده کنید.

`GET /auth/me` scopes توکن جاری را نشان می‌دهد.

## ۶. CSS/JavaScript و Approval

Agent می‌تواند `custom_css` و `custom_js` را در `create_page` و `update_page` ارسال کند. کد را بدون تگ `<style>`/`<script>` بفرستید. از DOM API امن مانند `textContent` استفاده کنید؛ `eval`، `new Function`، `innerHTML=` و `document.write` رد می‌شوند.

ویرایش Draft مستقیم است. ویرایش Published، انتشار/لغو انتشار، حذف و انتخاب لوگو/کاور در اتصال‌های Require Approval به `pending_approval=true` منجر می‌شود و نباید به‌عنوان اجرای کامل گزارش شود. `404 not_found` یا `400 no_changes` به‌معنای ساخته‌شدن Approval نیست.

## ۷. آپلود و لوگو/کاور

```bash
curl -X POST http://SERVER_IP:9900/api/agent/v1/media/upload \
  -H "Authorization: Bearer $HJF_AGENT_TOKEN" \
  -F 'file=@logo.png' -F 'product_id=15' -F 'kind=gallery' -F 'alt_text=لوگوی محصول'
```

سپس `set_product_logo` یا `set_product_cover` را با `product_id` و `media_id` بزنید و در صورت Pending منتظر تأیید بمانید. آپلود به‌تنهایی تصویر عمومی محصول را تغییر نمی‌دهد. Variantها در فیلد `variants` و URL اصلی در `url` هستند. برای حذف رسانه ابتدا `detach_media_from_product` لازم است.

## ۸. MCP

پیکربندی Streamable HTTP و Bearer قبلی تغییر نکرده است. کلاینت رسمی اکنون علاوه بر Tools می‌تواند `resources/list`، `resources/read`، `prompts/list` و `prompts/get` را اجرا کند. URI محصول/صفحه به شکل `hjf://products/15` و `hjf://pages/8` است. Discovery در `GET /.well-known/mcp.json` قرار دارد.
