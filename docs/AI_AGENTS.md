# اتصال AI Agent به وب‌سایت

دو رابط مستقل روی یک لایه سرویس مشترک کار می‌کنند:

| رابط | آدرس پیش‌فرض | کاربرد |
|---|---|---|
| REST | `http://SERVER_IP:9900/api/agent/v1` | فراخوانی مستقیم JSON از برنامه‌ها |
| MCP | `http://SERVER_IP:9901/mcp` | اتصال Client سازگار با Model Context Protocol |

MCP با پکیج رسمی `mcp` و FastMCP روی **Streamable HTTP**، حالت Stateless و JSON Response اجرا می‌شود. مسیر REST جایگزین یا نام مستعار MCP نیست. در عملیات هر دو آدرس باید HTTPS باشند.

## ساخت اتصال و دریافت Token

1. وارد `/admin/agents` شوید و **اتصال جدید** را باز کنید.
2. نام، توضیح کاربرد، فقط مجوزهای لازم، Rate Limit و تاریخ انقضای اختیاری را تعیین کنید.
3. «عملیات حساس نیازمند تأیید مدیر» را برای Agentهای غیرکاملاً مورداعتماد فعال نگه دارید.
4. Token با پیشوند `hjf_` فقط **یک بار** نمایش داده می‌شود. آن را در Secret Manager کلاینت ذخیره کنید.
5. در دیتابیس فقط Hash تصادفی‌نمک‌دار Scrypt، پیشوند کوتاه و وضعیت اتصال نگهداری می‌شود. Token کامل در Log، HTML بعدی یا API بازگردانده نمی‌شود.

از همان صفحه می‌توان مجوزها را ویرایش، Token را چرخاند، اتصال را لغو یا حذف کرد. چرخش بلافاصله Token قبلی را باطل می‌کند. انقضا و غیرفعال بودن نیز با 401 مشخص می‌شود.

```bash
export HJF_AGENT_TOKEN='hjf_...'
```

Token را در URL، Source Code، Prompt، Git یا Log ننویسید.

## REST API

### احراز هویت

تمام مسیرها Header زیر را لازم دارند:

```http
Authorization: Bearer hjf_...
Content-Type: application/json
Accept: application/json
```

- `GET /api/agent/v1/health`: وضعیت سرویس و شناسه اتصال؛ بدون فهرست داده محرمانه.
- `GET /api/agent/v1/tools`: ابزارهای مجاز همان اتصال، توضیح و JSON Schema واقعی.
- `POST /api/agent/v1/call/<tool_name>`: اجرای ابزار با Body آبجکت JSON.

### دریافت Schema

```bash
curl -fsS http://SERVER_IP:9900/api/agent/v1/tools \
  -H "Authorization: Bearer $HJF_AGENT_TOKEN"
```

### خواندن محصولات

```bash
curl -fsS -X POST http://SERVER_IP:9900/api/agent/v1/call/list_products \
  -H "Authorization: Bearer $HJF_AGENT_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"status":"published"}'
```

### ساخت صفحه پیش‌نویس

```bash
curl -fsS -X POST http://SERVER_IP:9900/api/agent/v1/call/create_page \
  -H "Authorization: Bearer $HJF_AGENT_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "slug":"solutions/ai-consulting",
    "title":"مشاوره هوش مصنوعی",
    "heading":"مشاوره تخصصی راهکارهای هوش مصنوعی",
    "summary":"یک صفحه پیش‌نویس برای بررسی مدیر",
    "html_content":"<h2>خدمات</h2><p>متن صفحه</p>"
  }'
```

`create_page` همیشه Draft می‌سازد. برای انتشار، `publish_page` با `{"page_id":123}` لازم است. اگر تأیید حساس فعال باشد، نتیجه شامل `pending_approval=true` و `approval_id` است و صفحه هنوز منتشر نشده است. مدیر در `/admin/agents` درخواست را تأیید یا رد می‌کند.

### خطاها

پاسخ‌های خطا JSON و دارای `error.code` و `error.message` هستند:

| HTTP | Code | معنی |
|---|---|---|
| 400 | `invalid_input` / `validation_error` | Schema یا مقدار ورودی معتبر نیست |
| 401 | `unauthorized` | Token غایب، لغوشده یا منقضی است |
| 403 | `permission_denied` | مجوز لازم داده نشده است |
| 404 | `not_found` | ابزار یا رکورد وجود ندارد |
| 409 | `conflict` | عملیات با وضعیت فعلی سازگار نیست |
| 429 | `rate_limited` | سقف درخواست در دقیقه رد شده است |

Schemaها `additionalProperties=false` دارند. SQL، Shell، مسیر فایل، Source Code، رمز یا Token به‌عنوان ورودی ابزار پذیرفته نمی‌شود.

## اجرای MCP

در محیط پروژه و با همان `.env` وب‌سایت:

```bash
source .venv/bin/activate
uvicorn mcp_server:asgi_app --host 0.0.0.0 --port 9901
```

در systemd از `deploy/services-mcp.service` استفاده کنید. MCP و Flask Processهای جدا دارند؛ Migration و دیتابیس مشترک‌اند و Agent به Connection مستقیم دیتابیس یا فایل پروژه دسترسی ندارد.

### تست با Client رسمی Python

```bash
python -m pip install 'mcp>=1.30,<2'
```

```python
import asyncio
import json
import os
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    token = os.environ["HJF_AGENT_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(
        "http://SERVER_IP:9901/mcp", headers=headers
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print([tool.name for tool in tools.tools])
            response = await session.call_tool(
                "list_products", {"status": "published"}
            )
            print(json.loads(response.content[0].text))

asyncio.run(main())
```

### پیکربندی Client با URL

در Clientهایی که Remote Streamable HTTP و Header سفارشی را پشتیبانی می‌کنند:

```json
{
  "mcpServers": {
    "hjf-website": {
      "url": "https://mcp.example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${HJF_AGENT_TOKEN}"
      }
    }
  }
}
```

روش وارد کردن Environment/Secret در هر Client متفاوت است. اگر Client فقط stdio پشتیبانی کند، یک Bridge مورداعتماد لازم دارد؛ این پروژه Bridge یا OAuth Provider ارائه نمی‌کند.

## مجوزها

| مجوز | محدوده |
|---|---|
| `products.read` | مشاهده و گزارش محصول |
| `products.create` | ساخت پیش‌نویس محصول |
| `products.update` | ویرایش و بایگانی محصول |
| `products.delete` | حذف محصول، عملیات حساس |
| `categories.manage` | ساخت و ویرایش دسته |
| `pages.read` | صفحات، پیش‌نمایش و آدرس عمومی |
| `pages.create` | ساخت پیش‌نویس صفحه |
| `pages.update` | ویرایش و بایگانی صفحه |
| `pages.publish` | انتشار و لغو انتشار، عملیات حساس |
| `menus.read` | مشاهده منوها |
| `menus.manage` | ساخت، ویرایش، ترتیب و حذف منو؛ حذف حساس است |
| `portfolio.read` | مشاهده نمونه‌کارها |
| `portfolio.create` | ساخت پیش‌نویس نمونه‌کار |
| `portfolio.update` | ویرایش و بایگانی نمونه‌کار |
| `content.read` | محتوای عمومی و بخش‌ها |
| `content.manage` | ویرایش محتوای ثبت‌شده |
| `media.read` | فهرست و جزئیات رسانه |
| `media.delete` | حذف رسانه، عملیات حساس |
| `settings.read` | تنظیمات عمومی برند |
| `reports.read` | آمار و گزارش تغییرات |
| `logs.read` | فقط Audit مربوط به همان Agent |

ابزارهایی که مجوز Agent را ندارند در `tools/list` MCP و فهرست REST ظاهر نمی‌شوند. فراخوانی مستقیم نیز دوباره در لایه سرویس بررسی و 403 می‌شود.

## ابزارها

همه Schemaها از `/tools` و `tools/list` قابل دریافت‌اند؛ لیست ثابت زیر برای انتخاب مجوز است:

- محصول/دسته: `list_products`، `get_product`، `create_product`، `update_product`، `archive_product`، `delete_product`، `get_product_categories`، `create_product_category`، `update_product_category`.
- صفحه: `list_pages`، `get_page`، `create_page`، `update_page`، `preview_page`، `publish_page`، `unpublish_page`، `archive_page`، `get_page_public_url`.
- منو: `list_menus`، `get_menu`، `add_menu_item`، `update_menu_item`، `remove_menu_item`، `reorder_menu_items`.
- نمونه‌کار: `list_portfolio_items`، `get_portfolio_item`، `create_portfolio_item`، `update_portfolio_item`، `archive_portfolio_item`.
- محتوا/رسانه: `get_site_content`، `list_content_sections`، `update_site_content`، `update_content_section`، `list_media`، `get_media_details`، `delete_media`.
- گزارش/Audit: `get_site_overview`، `get_site_statistics`، `get_published_pages`، `get_draft_pages`، `get_product_statistics`، `get_recent_changes`، `get_agent_activity_logs`.

Resourceهای امن `site://overview` و `site://tools` و Prompt راهنمای `safe_content_manager` نیز در MCP وجود دارند. Resource اول به `reports.read` نیاز دارد.

## تأیید انسانی و Audit

انتشار، لغو انتشار، بایگانی و حذف حساس طبق سیاست اتصال Pending می‌شوند. رکورد Pending فقط یک بار قابل بررسی است. اجرای نهایی دوباره از لایه ابزار و با نام مدیر تأییدکننده ثبت می‌شود. رد کردن هیچ تغییری روی محتوا نمی‌دهد.

`/admin/agent-activity` بر اساس Agent، نوع عملیات و وضعیت قابل فیلتر است. زمان، ابزار، نوع رکورد، نتیجه خلاصه، خطای ساختاریافته و تأییدکننده ثبت می‌شود. Payload کامل و Token در Log ذخیره نمی‌شود.

## تست اتصال

```bash
# بدون Token باید 401 باشد
curl -i http://SERVER_IP:9900/api/agent/v1/tools
curl -i http://SERVER_IP:9901/mcp

# Token معتبر
curl -fsS http://SERVER_IP:9900/api/agent/v1/health \
  -H "Authorization: Bearer $HJF_AGENT_TOKEN"

# تست کامل پروژه، شامل MCP Client رسمی و دیتابیس موقت
pytest -q
```

## عیب‌یابی

- **401:** ساعت سرور، فعال بودن اتصال، انقضا و Bearer Header را بررسی کنید؛ در صورت چرخش، Secret کلاینت را تازه کنید.
- **403:** مجوز ابزار را در `/admin/agents` اضافه کنید؛ Token لازم نیست عوض شود.
- **404 روی `/mcp`:** Uvicorn مستقل روی پورت 9901 اجرا نشده یا Proxy مسیر را تغییر داده است.
- **429:** فاصله درخواست‌ها را بیشتر و Rate Limit منطقی تنظیم کنید. در چند Worker برای Rate Limit فرم‌ها Redis لازم است؛ سقف Agent از Audit دیتابیس شمرده می‌شود.
- **صفحه عمومی نیست:** Draft/Unpublished بودن طبیعی است. Pending انتشار را مدیر تأیید کند و وضعیت/منو را جدا بررسی کنید.
- **Client اتصال نمی‌گیرد:** پشتیبانی Streamable HTTP، دسترسی شبکه، HTTPS و Header Authorization را بررسی کنید. SSE قدیمی و stdio به‌صورت مستقیم Endpoint این سرویس نیستند.
- **Firewall:** در نصب آزمایشی پورت‌های 9900 و 9901 باز می‌شوند. در Production بهتر است فقط Nginx عمومی باشد و Backendها از طریق Reverse Proxy در دسترس قرار گیرند.
