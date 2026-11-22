"""Truthful introductory content for six independent, in-development product concepts.
No connector, AI, automation, customer result or platform support is represented as implemented.
Existing records and administrator edits are never overwritten.
"""
from app.extensions import db
from app.models import Category, FAQ, PlatformConnector, Product, ProductFeature, ProductMedia, ProductModule

CATEGORIES = [
    ("مدیریت هوشمند شبکه‌های اجتماعی", "smart-social-management", "برنامه‌ریزی و مدیریت مسئولانه محتوا و تعامل در شبکه‌های اجتماعی.", "workflow"),
    ("بازاریابی و جذب مخاطب", "marketing-audience-growth", "مسیرهای رضایت‌محور برای جذب، بخش‌بندی و ارتباط با مخاطب.", "audience"),
    ("تحلیل کسب‌وکار و بازار", "business-market-analysis", "تبدیل داده‌های مجاز و شفاف به گزارش و فرضیه قابل بررسی.", "chart"),
    ("مدیریت پیام‌رسان‌ها", "messenger-management", "معماری مدیریت گفتگو، صف و مقصد در پیام‌رسان‌ها.", "layers"),
    ("اتوماسیون ارتباطات", "communication-automation", "خودکارسازی کنترل‌شده ارتباطات بر اساس API، مجوز و رضایت.", "workflow"),
    ("CRM و مدیریت سرنخ", "crm-lead-management", "ثبت، اولویت‌بندی و پیگیری سرنخ‌های دارای مبنای قانونی.", "layers"),
    ("دستیارهای هوش مصنوعی", "ai-assistant-products", "دستیارهای تحلیلی و محتوایی با کنترل انسانی و مرزهای مشخص.", "brain"),
]

PRODUCTS = [
{
 "name":"InstaPilot AI", "slug":"instapilot-ai", "color":"#6d4aff", "cats":["smart-social-management","ai-assistant-products"],
 "tag":"دستیار برنامه‌ریزی محتوای اینستاگرام؛ از پیش‌نویس تا انتشار کنترل‌شده",
 "short":"کانسپت مستقل برای تقویم محتوا، پیش‌نویس کپشن و گردش تأیید؛ بدون اتصال فعال به اینستاگرام.",
 "medium":"InstaPilot AI در وضعیت معرفی اولیه و توسعه است. هدف آن ساده‌سازی برنامه‌ریزی محتوا، ساخت پیش‌نویس و کنترل انسانی پیش از انتشار است؛ هیچ AI، زمان‌بند یا اتصال اینستاگرام در حال حاضر پیاده‌سازی نشده است.",
 "full":"محصول آینده برای تیم‌های محتوا یک میز کار واحد پیشنهاد می‌کند: ثبت ایده، ساخت پیش‌نویس قابل ویرایش، تقویم انتشار و تأیید نهایی. اتصال انتشار فقط از مسیر API رسمی و پس از دریافت دسترسی و تأیید پلتفرم بررسی خواهد شد. تصویر صفحه Mockup است و خروجی نرم‌افزار اجراشده نیست.",
 "problem":"پراکنده‌بودن ایده‌ها، کپشن‌ها و زمان‌بندی میان ابزارهای مختلف باعث دوباره‌کاری و انتشار بدون بازبینی می‌شود. راهکار هدف، گردش کار قابل ردیابی با تصمیم نهایی انسان است.",
 "features":[("تقویم و پیش‌نویس محتوا","ثبت ایده، کپشن و وضعیت بازبینی در یک تقویم قابل ویرایش.","planned"),("دستیار پیش‌نویس کپشن","پیشنهاد متن اولیه با سرویس AI، بدون انتشار خودکار یا ادعای اجرای فعلی.","development"),("زمان‌بندی انتشار مجاز","ارسال فقط پس از تأیید کاربر و از طریق API رسمی در دسترس.","api_required"),("تأیید انسانی و سابقه تغییرات","ثبت تأیید نهایی و نسخه پیش‌نویس پیش از هر انتشار.","planned"),("اتصال رسمی اینستاگرام","انتشار و دریافت وضعیت مشروط به مجوز، API و تأیید پلتفرم.","platform_approval")],
 "uses":["ساخت تقویم هفتگی محتوا برای یک برند","بازبینی پیش‌نویس کپشن پیش از انتشار","هماهنگی تولیدکننده و تأییدکننده محتوا"], "audience":["تیم‌های محتوا و مدیران شبکه اجتماعی","کسب‌وکارهای کوچک با گردش تأیید محتوا"],
 "pre":["تعریف سیاست محتوا و نقش تأییدکننده","برای اتصال آینده: حساب تجاری، API رسمی و مجوزهای لازم","برای AI آینده: سرویس مدل و سیاست حفاظت از داده"], "limits":["اتصال یا انتشار خودکار اینستاگرام پیاده‌سازی نشده است.","AI و زمان‌بند فعال وجود ندارد و Mockup دمو نیست.","افزایش بازدید، فروش یا تعامل تضمین نمی‌شود.","داده خصوصی یا غیرمجاز جمع‌آوری نمی‌شود."], "platforms":["Instagram"], "integration":"api_required",
 "modules":[("Content Studio","مدیریت ایده، پیش‌نویس و دارایی‌های محتوا.","planned"),("Approval & Publishing","گردش تأیید و Adapter انتشار رسمی آینده.","development")],
 "connectors":[("instagram","Instagram","OAuth رسمی / حساب تجاری","api_required",True,True,["انتشار خودکار یا دسترسی به داده خصوصی فعال نیست.","دامنه API و تأیید اپ هنوز نهایی نشده است."])],
 "faqs":[("آیا اکنون به اینستاگرام وصل می‌شود؟","خیر. Connector در وضعیت نیازمند API و تأیید پلتفرم است و هیچ اتصال فعال یا حساب متصلی وجود ندارد."),("آیا کپشن را خودکار منتشر می‌کند؟","خیر. طراحی هدف بر تأیید انسانی تأکید دارد؛ AI و انتشار خودکار در نسخه فعلی پیاده‌سازی نشده‌اند.")]
},
{
 "name":"AudienceFlow AI", "slug":"audienceflow-ai", "color":"#087ea4", "cats":["marketing-audience-growth","ai-assistant-products","communication-automation"],
 "tag":"طراحی سفر مخاطب و کمپین‌های رضایت‌محور، بدون پیام انبوه ناخواسته",
 "short":"کانسپت بخش‌بندی مخاطب و گردش کمپین با ثبت رضایت و کنترل انسانی؛ فاقد اتصال و AI فعال.",
 "medium":"AudienceFlow AI برای طراحی مسیر جذب و تعامل مخاطب در حال توسعه است. خروجی هدف، بخش‌بندی داده‌های دارای مجوز و پیشنهاد اقدام است؛ هیچ ارسال انبوه، Scraping یا AI اجراشده‌ای وجود ندارد.",
 "full":"محصول آینده داده‌های مجاز فرم‌ها و CRM را به بخش‌های قابل فهم تبدیل می‌کند و سناریوی تماس را با قواعد رضایت و توقف پیشنهاد می‌دهد. اتصال به پیام‌رسان یا ایمیل فقط پس از بررسی API و سیاست ارسال انجام می‌شود. تمام نمودارهای تصویر نمایشی‌اند و نشان‌دهنده نتیجه واقعی نیستند.",
 "problem":"تیم بازاریابی اغلب مخاطبان و مراحل تماس را بدون سابقه رضایت یا اولویت روشن مدیریت می‌کند. AudienceFlow مسیر شفاف و قابل توقف را جایگزین اقدامات پراکنده می‌کند.",
 "features":[("بخش‌بندی مخاطب مجاز","گروه‌بندی داده‌های ارسالی کاربر بر اساس معیارهای غیرحساس.","planned"),("ثبت وضعیت رضایت","نگهداری منبع و وضعیت رضایت برای مسیرهای ارتباطی.","development"),("پیشنهاد اقدام با AI","پیشنهاد متن یا گام بعدی با بازبینی انسانی؛ غیرفعال در وضعیت فعلی.","planned"),("ارسال از API رسمی","اتصال کمپین مشروط به API، سیاست پلتفرم و رضایت مخاطب.","api_required"),("توقف و حذف مخاطب","طراحی مسیر لغو رضایت و حذف از ارتباطات بعدی.","planned")],
 "uses":["دسته‌بندی ثبت‌نام‌کنندگان یک رویداد با رضایت روشن","طراحی پیگیری برای مخاطبان فرم تماس","بررسی وضعیت رضایت پیش از کمپین"], "audience":["تیم‌های بازاریابی مسئولیت‌پذیر","مدیران رویداد و جامعه مشتریان"],
 "pre":["منبع داده با مبنای قانونی و رضایت قابل اثبات","سیاست نگهداری، حذف و لغو رضایت","API رسمی برای هر کانال ارتباطی آینده"], "limits":["ارسال پیام یا اتصال به پلتفرم فعال نیست.","هیچ استنباط داده حساس یا پروفایل‌سازی پنهان انجام نمی‌شود.","رشد مخاطب یا فروش تضمین نمی‌شود.","دعوت یا پیام انبوه بدون رضایت پشتیبانی نمی‌شود."], "platforms":["Email","Telegram"], "integration":"api_required",
 "modules":[("Consent & Segments","مدیریت رضایت و بخش‌های مخاطب.","development"),("Journey Designer","طراحی گام‌های ارتباط و نقاط توقف.","planned")],
 "connectors":[("email","Email / SMTP","SMTP متعلق به کاربر","api_required",True,False,["ارسال فعال نیست؛ رضایت و سیاست ارائه‌دهنده لازم است."]),("telegram","Telegram","Bot API و رضایت کاربر","platform_approval",True,True,["ربات متصل نیست و شروع گفتگو توسط کاربر لازم است."])],
 "faqs":[("آیا برای جذب فالوور یا ارسال انبوه است؟","خیر. هدف محصول مدیریت ارتباط با مخاطب رضایت‌داده است، نه خرید مخاطب، دعوت انبوه یا دور زدن محدودیت‌ها."),("آیا AI مخاطبان را تحلیل می‌کند؟","در حال حاضر AI فعال نیست. طراحی آینده فقط روی داده مجاز و بدون استنباط ویژگی حساس بررسی می‌شود.")]
},
{
 "name":"LeadRadar AI", "slug":"leadradar-ai", "color":"#e56b24", "cats":["crm-lead-management","ai-assistant-products","business-market-analysis"],
 "tag":"اولویت‌بندی و پیگیری سرنخ‌های دارای مجوز، با تصمیم نهایی تیم فروش",
 "short":"کانسپت CRM سبک برای ثبت سرنخ، قواعد اولویت و یادآوری پیگیری؛ بدون اتصال یا امتیازدهی AI فعال.",
 "medium":"LeadRadar AI یک محصول در حال توسعه برای ساماندهی سرنخ‌های فرم و CRM است. امتیازها باید قابل توضیح و مبتنی بر داده مجاز باشند؛ هیچ پیش‌بینی فروش یا استنباط شخصی حساسی ادعا نمی‌شود.",
 "full":"هدف LeadRadar ایجاد صف پیگیری روشن برای سرنخ‌هایی است که خودشان درخواست تماس ثبت کرده‌اند یا مبنای قانونی ارتباط دارند. تیم می‌تواند قواعد اولویت، مالک سرنخ و اقدام بعدی را تعریف کند. ماژول AI صرفاً نقشه راه است و داشبورد تصویر، Mockup مشخص است.",
 "problem":"سرنخ‌های ورودی بدون مالک، وضعیت و زمان پیگیری از دست می‌روند. یک صف اولویت‌بندی شفاف می‌تواند کار تیم را منظم کند بدون اینکه تصمیم فروش را به مدل واگذار کند.",
 "features":[("ثبت و یکسان‌سازی سرنخ","تجمیع ورودی مجاز فرم‌ها و ثبت منبع هر سرنخ.","development"),("قواعد اولویت قابل توضیح","امتیازدهی بر اساس قواعد تعریف‌شده تیم، نه پیش‌بینی تضمینی.","planned"),("یادآوری و مالک پیگیری","تعیین مسئول، موعد و اقدام بعدی برای هر سرنخ.","planned"),("خلاصه‌سازی AI","پیشنهاد خلاصه گفتگو با بازبینی انسان؛ پیاده‌سازی نشده است.","development"),("اتصال CRM","دریافت و ارسال داده مشروط به API و مجوز سامانه مقصد.","api_required")],
 "uses":["تخصیص درخواست‌های فرم مشاوره به کارشناس","تعیین پیگیری بعدی برای سرنخ‌های دارای رضایت","مقایسه قواعد اولویت در محیط آزمایشی"], "audience":["تیم‌های فروش B2B کوچک","مدیران پشتیبانی و موفقیت مشتری"],
 "pre":["منبع سرنخ با مجوز ارتباط و سیاست حریم خصوصی","قواعد اولویت و نقش‌های تیم","API و دسترسی رسمی برای اتصال CRM آینده"], "limits":["CRM یا سرویس ایمیل متصل نیست.","AI و پیش‌بینی احتمال خرید فعال نیست.","تضمین تبدیل سرنخ یا افزایش فروش وجود ندارد.","استنباط سلامت، قومیت، عقیده یا سایر داده حساس مجاز نیست."], "platforms":["CRM API","Email"], "integration":"api_required",
 "modules":[("Lead Inbox","ورود، پاک‌سازی و ثبت منبع سرنخ.","development"),("Priority & Follow-up","قواعد اولویت، تخصیص و یادآوری.","planned")],
 "connectors":[("crm","CRM API","API key / OAuth سامانه کاربر","api_required",True,False,["هیچ CRM مشخص یا متصل نشده است."]),("email","Email","SMTP متعلق به کاربر","planned",True,False,["ارسال پیگیری خودکار پیاده‌سازی نشده است."])],
 "faqs":[("آیا LeadRadar احتمال خرید را تضمین می‌کند؟","خیر. هیچ پیش‌بینی فعال یا تضمین تبدیل وجود ندارد؛ قواعد اولویت فقط ابزار ساماندهی تیم خواهند بود."),("آیا سرنخ را از اینستاگرام استخراج می‌کند؟","خیر. Scraping داده خصوصی یا ساخت سرنخ بدون مبنای مجاز بخشی از محصول نیست.")]
},
{
 "name":"RubiCast", "slug":"rubicast", "color":"#7954d8", "cats":["messenger-management","communication-automation"],
 "tag":"میز کار آینده برای مدیریت پیام و محتوای روبیکا با API مجاز",
 "short":"کانسپت مستقل مدیریت گفتگو و صف محتوا برای روبیکا؛ بدون ربات، Adapter یا اتصال رسمی پیاده‌سازی‌شده.",
 "medium":"RubiCast در مرحله معرفی اولیه است و معماری هدف برای صف پیام، پاسخ‌گویی و گزارش وضعیت را نمایش می‌دهد. هیچ اتصال به روبیکا یا ارسال واقعی انجام نمی‌شود.",
 "full":"RubiCast برای کسب‌وکارهایی طراحی می‌شود که گفتگوهای مجاز روبیکا را با نقش‌های تیمی و صف پاسخ مدیریت می‌کنند. دسترسی به پیام‌ها و ارسال محتوا فقط از مسیر رسمی، با حساب متعلق به کاربر و در چارچوب قوانین پلتفرم بررسی خواهد شد. هیچ ارتباطی با قابلیت‌های مخازن قبلی ندارد.",
 "problem":"مدیریت تیمی پیام‌ها بدون وضعیت، مالک و صف روشن می‌تواند به پاسخ تکراری یا فراموش‌شده منجر شود. RubiCast مدل هدف برای این گردش کار است.",
 "features":[("صندوق گفتگوی تیمی","نمای هدف برای تخصیص وضعیت و مسئول پاسخ.","planned"),("صف و قالب پاسخ","آماده‌سازی پاسخ‌های قابل بازبینی پیش از ارسال.","development"),("Connector روبیکا","اتصال فقط با API مجاز و احراز هویت معتبر؛ در حال بررسی.","review"),("گزارش وضعیت پیام","ثبت نتیجه Adapter در آینده، نه آمار تحویل واقعی فعلی.","planned"),("کنترل رضایت و محدودیت","اعمال قواعد توقف و نرخ مجاز پلتفرم در طراحی.","planned")],
 "uses":["تخصیص پیام‌های دریافتی مجاز به پشتیبان","آماده‌سازی پاسخ برای بازبینی مدیر","طراحی صف محتوای کانال متعلق به کاربر"], "audience":["تیم‌های پشتیبانی دارای حساب رسمی","مدیران کانال و جامعه در روبیکا"],
 "pre":["حساب و مجوز رسمی متعلق به کاربر","مشخصات API و محدودیت‌های معتبر روبیکا","سیاست پاسخ‌گویی و مدیریت رضایت"], "limits":["API و سطح دسترسی روبیکا هنوز نیازمند بررسی است.","هیچ ارسال، دریافت یا ربات فعال وجود ندارد.","پیام ناخواسته، عضویت اجباری یا دور زدن محدودیت پشتیبانی نمی‌شود.","پشتیبانی کامل روبیکا ادعا نمی‌شود."], "platforms":["Rubika"], "integration":"review",
 "modules":[("Conversation Desk","صندوق گفتگو و تخصیص پاسخ.","planned"),("Rubika Adapter","لایه اتصال رسمی پس از بررسی API.","review")],
 "connectors":[("rubika","Rubika","در انتظار بررسی API رسمی","review",True,True,["هیچ Adapter اجراشده یا حساب متصلی وجود ندارد.","دامنه قابلیت پس از مستندات و تأیید رسمی مشخص می‌شود."])],
 "faqs":[("آیا RubiCast اکنون پیام روبیکا ارسال می‌کند؟","خیر. وضعیت Connector نیازمند بررسی است و هیچ کد اتصال یا ارسال فعال برای این محصول وجود ندارد."),("آیا می‌توان مخاطبان را انبوه دعوت کرد؟","خیر. دعوت انبوه بدون رضایت، ارسال ناخواسته و دور زدن محدودیت پلتفرم در طراحی محصول جایی ندارد.")]
},
{
 "name":"OmniCast", "slug":"omnicast", "color":"#146c94", "cats":["messenger-management","communication-automation","smart-social-management"],
 "tag":"معماری یکپارچه‌سازی گفتگوها با Connector مستقل و وضعیت شفاف هر پلتفرم",
 "short":"کانسپت صندوق ورودی چندکاناله و مسیریابی قاعده‌محور؛ هیچ پلتفرمی متصل یا پشتیبانی کامل نشده است.",
 "medium":"OmniCast برای طراحی یک میز کار چندکاناله در حال توسعه است. وضعیت هر Connector مستقل است و ثبت نام پلتفرم به‌معنی پشتیبانی یا اتصال آماده نیست.",
 "full":"OmniCast مدل هدف برای دریافت پیام از کانال‌های مجاز، تخصیص به اپراتور و مسیریابی قواعد است. Adapter هر پلتفرم جداگانه توسعه و آزمون می‌شود و شکست یکی به معنی توقف یا پشتیبانی دیگری نیست. ارسال انبوه، ترکیب داده خصوصی و اتوماسیون بدون رضایت خارج از دامنه است.",
 "problem":"گفتگوهای مشتری در کانال‌های مختلف پراکنده‌اند، اما یکپارچه‌سازی بدون مدل مجوز و وضعیت هر Adapter می‌تواند گمراه‌کننده و ناپایدار باشد.",
 "features":[("قرارداد مشترک Connector","مدل واحد پیام و رویداد با Adapter جداگانه هر پلتفرم.","development"),("صندوق ورودی تیمی","تخصیص گفتگو و وضعیت پاسخ در طراحی آینده.","planned"),("مسیریابی قاعده‌محور","انتخاب مسیر بر اساس قواعد قابل بازبینی، نه اتوماسیون فعال.","planned"),("رضایت و محدودیت هر کانال","سیاست جداگانه ارسال، توقف و نگهداری داده.","planned"),("API و تأیید پلتفرم","هر اتصال مشروط به دسترسی رسمی و آزمون مستقل.","platform_approval")],
 "uses":["طراحی میز پشتیبانی برای کانال‌های دارای API رسمی","مسیریابی گفتگو به اپراتور مناسب","ارزیابی جداگانه امکان اتصال یک پیام‌رسان"], "audience":["تیم‌های پشتیبانی چندکاناله","کسب‌وکارهای دارای زیرساخت API رسمی"],
 "pre":["API رسمی و حساب متعلق به کاربر برای هر کانال","سیاست رضایت، نگهداری و حذف داده","تست جداگانه Adapter پیش از تغییر وضعیت"], "limits":["هیچ Connector فعال یا پشتیبانی کامل پلتفرم وجود ندارد.","Telegram، Bale و WhatsApp فقط اهداف اتصال آینده‌اند.","ارسال انبوه و همگام‌سازی داده خصوصی مجاز نیست.","Mockup به‌معنی دمو یا ادعای اتوماسیون پیاده‌شده نیست."], "platforms":["Telegram","Bale","WhatsApp"], "integration":"platform_approval",
 "modules":[("Unified Inbox","مدل مشترک گفتگو و تخصیص اپراتور.","planned"),("Connector Runtime","چرخه عمر و تست مستقل Adapterها.","development"),("Routing Rules","قواعد مسیریابی و کنترل رضایت.","planned")],
 "connectors":[("telegram","Telegram","Bot API و شروع گفتگو توسط کاربر","api_required",True,False,["ربات یا Adapter فعال نیست."]),("bale","Bale","Bot API رسمی","api_required",True,False,["اتصال فعال نیست و قابلیت‌ها آزمون نشده‌اند."]),("whatsapp","WhatsApp Business","Cloud API و تأیید Meta","platform_approval",True,True,["تأیید تجاری و قالب پیام لازم است؛ اتصال فعال نیست."])],
 "faqs":[("آیا همه پیام‌رسان‌ها پشتیبانی می‌شوند؟","خیر. هیچ پشتیبانی کامل یا اتصال فعالی وجود ندارد. هر Connector وضعیت مستقل و محدودیت خودش را دارد."),("آیا پیام‌ها به‌طور خودکار بین پلتفرم‌ها منتقل می‌شوند؟","خیر. اتوماسیون فعال نیست و هرگز داده بدون مجوز و سیاست مشخص میان پلتفرم‌ها منتقل نمی‌شود.")]
},
{
 "name":"MarketMind AI", "slug":"marketmind-ai", "color":"#1f766e", "cats":["business-market-analysis","ai-assistant-products"],
 "tag":"دستیار تحلیل بازار بر اساس داده مجاز، منابع روشن و فرضیه‌های قابل بازبینی",
 "short":"کانسپت تحلیل روند و رقبا از داده‌های مجاز؛ بدون Scraping، AI فعال یا نتیجه تضمینی.",
 "medium":"MarketMind AI برای ساخت گزارش تحلیلی قابل ردیابی در حال توسعه است. هدف، خلاصه‌سازی داده‌های مجاز و نمایش منبع و عدم قطعیت است، نه پیش‌بینی تضمینی بازار.",
 "full":"محصول آینده داده‌هایی را که کاربر حق استفاده از آن‌ها دارد به شاخص، روند و فرضیه قابل بررسی تبدیل می‌کند. هر گزارش باید منبع، بازه زمانی و محدودیت داده را نمایش دهد. اتصال منابع عمومی فقط در چارچوب مجوز و شرایط استفاده بررسی می‌شود و هیچ داده خصوصی یا پشت لاگین جمع‌آوری نمی‌شود.",
 "problem":"گزارش‌های بازار اغلب از منابع پراکنده و بدون ثبت فرضیه ساخته می‌شوند. MarketMind تمرکز را بر قابلیت ردیابی و بازبینی انسانی می‌گذارد.",
 "features":[("ثبت منابع و بازه داده","اتصال هر شاخص به منبع مجاز و زمان جمع‌آوری.","development"),("گزارش روند و مقایسه","مصورسازی داده ورودی با محدودیت‌های روشن.","planned"),("خلاصه تحلیلی AI","پیشنهاد خلاصه با منبع و بازبینی انسانی؛ غیرفعال.","planned"),("ورود داده از API","دریافت داده فقط از API یا فایل مجاز کاربر.","api_required"),("برچسب عدم قطعیت","تفکیک مشاهده، فرضیه و پیشنهاد در گزارش.","planned")],
 "uses":["مقایسه شاخص‌های فایل داده متعلق به کسب‌وکار","تهیه گزارش روند با منبع و تاریخ مشخص","ثبت فرضیه‌های قابل بازبینی برای جلسه برنامه‌ریزی"], "audience":["تحلیلگران کسب‌وکار و مدیران محصول","تیم‌های پژوهش بازار با داده مجاز"],
 "pre":["فایل یا API با مجوز استفاده و منبع مشخص","تعریف شاخص، بازه و سیاست کیفیت داده","سرویس AI و سیاست داده در صورت توسعه خلاصه‌ساز"], "limits":["هیچ Scraping یا اتصال منبع خارجی فعال نیست.","AI، پیش‌بینی و تحلیل خودکار پیاده‌سازی نشده است.","داده نمودارها ساختگی و صرفاً برای Mockup است.","دقت تحلیل و نتیجه تجاری تضمین نمی‌شود."], "platforms":["File import","Approved data APIs"], "integration":"api_required",
 "modules":[("Data Provenance","ثبت منبع، مجوز و بازه داده.","development"),("Analysis Workspace","شاخص، روند و گزارش قابل بازبینی.","planned")],
 "connectors":[("data-api","Approved Data APIs","API key و مجوز استفاده","api_required",True,False,["منبع مشخصی متصل نیست؛ هر API جداگانه بررسی می‌شود."]),("file-import","CSV / XLSX Import","بارگذاری آگاهانه توسط کاربر","planned",False,False,["ورودی فایل هنوز پیاده‌سازی نشده است."])],
 "faqs":[("آیا MarketMind بازار را پیش‌بینی می‌کند؟","نسخه فعلی هیچ AI یا پیش‌بینی اجراشده‌ای ندارد. هدف آینده گزارش فرضیه و روند با منبع است، نه پیش‌بینی قطعی."),("آیا داده رقبا را از صفحات خصوصی جمع می‌کند؟","خیر. دسترسی به داده خصوصی، پشت لاگین یا بدون مجوز بخشی از طراحی محصول نیست.")]
},
]


def seed_concepts():
    categories = {}
    start = Category.query.count()
    for index, (name, slug, description, icon) in enumerate(CATEGORIES):
        category = Category.query.filter_by(slug=slug).first()
        if not category:
            category = Category(name=name, slug=slug, description=description, icon=icon, position=start + index)
            db.session.add(category)
            db.session.flush()
        categories[slug] = category

    start_position = Product.query.count()
    for index, data in enumerate(PRODUCTS):
        product = Product.query.filter_by(slug=data["slug"]).first()
        if product:
            continue
        product = Product(
            name=data["name"], slug=data["slug"], repository_name=None, repository_url=None,
            origin_type="independent", commercial_status="concept", status="published",
            development_status="in_development", product_type="ai" if "AI" in data["name"] else "automation",
            integration_status=data["integration"], ai_enabled=False, automation_enabled=False,
            demo_available=False, repository_enabled=False, product_version="Concept — معرفی اولیه",
            pricing_visibility="hidden", category=categories[data["cats"][0]],
            additional_categories=[categories[slug] for slug in data["cats"][1:]], platforms=data["platforms"],
            tagline=data["tag"], short_description=data["short"], medium_description=data["medium"],
            full_description=data["full"], value_proposition=data["tag"], problem_statement=data["problem"],
            use_cases=data["uses"], target_audience=data["audience"], prerequisites=data["pre"],
            limitations=data["limits"], technologies=["طراحی محصول", "REST API رسمی (برنامه‌ریزی‌شده)"],
            is_featured=False, show_on_home=True, position=start_position + index, accent_color=data["color"],
            logo_path=f"static/img/logos/{data['slug']}.svg", confidence="high",
            seo_title=f"{data['name']} | معرفی اولیه محصول در حال توسعه", seo_description=data["short"][:300],
        )
        db.session.add(product)
        db.session.flush()
        for position, (title, description, status) in enumerate(data["features"]):
            product.features.append(ProductFeature(title=title, description=description, position=position, verification_status=status, is_published=True))
        for position, (question, answer) in enumerate(data["faqs"]):
            product.faqs.append(FAQ(question=question, answer=answer, position=position, is_published=True))
        for position, (name, description, status) in enumerate(data["modules"], 1):
            product.modules.append(ProductModule(name=name, description=description, status=status, position=position))
        for position, (platform, display, auth, status, api, approval, limitations) in enumerate(data["connectors"]):
            product.connectors.append(PlatformConnector(platform=platform, display_name=display, auth_method=auth,
                connection_status="not_connected", capability_status=status, api_required=api,
                approval_required=approval, supported_features=[], limitations=limitations,
                is_enabled=False, position=position, last_checked_at=None))
        product.media.append(ProductMedia(title=f"Mockup مفهومی {data['name']}",
            description="تصویر نمایشی هدف طراحی؛ اسکرین‌شات نرم‌افزار اجراشده، داده واقعی یا اتصال فعال نیست.",
            alt_text=f"Mockup مفهومی و در حال توسعه {data['name']}؛ نه دمو واقعی",
            media_type="image", file_path=f"static/img/mockups/{data['slug']}-concept.svg",
            mime_type="image/svg+xml", position=0, is_published=True, is_mockup=True))
    db.session.commit()
