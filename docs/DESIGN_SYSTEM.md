# رابط بصری و الگوهای تعاملی سایت

پوسته سایت با Flask/Jinja و CSS/JavaScript سبک پیاده‌سازی شده است؛ نیازی به مهاجرت به React یا بارگیری runtime شخص ثالث نیست. الگوهای زیر با الهام از جامعه 21st.dev بازطراحی و بومی‌سازی شده‌اند:

- [Background Paths — Kokonut UI](https://21st.dev/@kokonutd/components/background-paths): مسیرهای SVG نورانی و حرکت آهسته در پس‌زمینه Hero.
- [Spotlight Card — Jahed / EaseMize](https://21st.dev/@jahed/components/spotlight-card): نور موضعی دنبال‌کننده مکان‌نما برای کارت محصولات، دسته‌ها و نمونه‌کارها.
- [Hover Preview — Le Thanh](https://21st.dev/@minhxthanh/components/hover-preview): تصویر جلد واقعی یا نشان تجاری محصول در پنل تصویری کارت، با بزرگ‌نمایی آرام هنگام Hover.
- [Bento Grid — Kokonut UI](https://21st.dev/@kokonutd/components/bento-grid): چیدمان دسته‌بندی‌های منتخب با کارت شاخص و responsive grid.
- [Limelight Nav — Jahed / EaseMize](https://21st.dev/@jahed/components/limelight-nav): خط فعال روشن و قابل‌دسترسی در ناوبری دسکتاپ.

این‌ها پیاده‌سازی‌های سازگار با DOM سروری فعلی‌اند، نه کپی از bundle React/Tailwind یا بارگیری وابستگی خارجی. افکت‌ها در `app/templates/public/`، `app/static/css/main.css` و `app/static/js/main.js` قرار دارند. برای کاربرانی که `prefers-reduced-motion` را فعال کرده‌اند انیمیشن‌ها خاموش/کاهش می‌یابد؛ لینک‌ها با صفحه‌کلید Focus واضح دارند و کارت‌ها در صفحه لمسی به شکل ثابت و کامل دیده می‌شوند.

## اصول طراحی

- فارسی RTL و فونت Vazirmatn محلی؛ بدون فونت یا اسکریپت خارجی در صفحات عمومی.
- محتوا و رسانه از دیتابیس واقعی می‌آیند؛ تصویر مفهومی به‌عنوان رابط واقعی محصول جا زده نمی‌شود.
- رنگ‌های اختصاصی کارت از Accent محصول می‌آیند؛ جای خالی رسانه با طرح هندسی CSS نشان داده می‌شود.
- حرکت کوتاه، قابل کاهش و تزئینی است؛ هیچ محتوای ضروری فقط با Hover ظاهر نمی‌شود.
- پنل مدیریت عمداً از این تغییرات گستردهٔ بصری عمومی جدا نگه داشته شده است.
