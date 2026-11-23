"""Generate original, editable SVG identities and explicitly-labelled concept mockups."""
from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parents[1] / "app/static/img"
PRODUCTS = [
    ("instapilot-ai", "InstaPilot AI", "IP", "#6d4aff", "#ef4f91", "calendar", ["تقویم محتوا", "پیش‌نویس کپشن", "زمان‌بندی", "تأیید پیش از انتشار"]),
    ("audienceflow-ai", "AudienceFlow AI", "AF", "#087ea4", "#26b99a", "audience", ["کمپین رضایت‌محور", "بخش‌بندی مخاطب", "قیف تعامل", "ثبت رضایت"]),
    ("leadradar-ai", "LeadRadar AI", "LR", "#e56b24", "#f4b740", "radar", ["سرنخ‌های مجاز", "امتیاز اولویت", "پیگیری بعدی", "مالک سرنخ"]),
    ("rubicast", "RubiCast", "RC", "#7954d8", "#b082f4", "broadcast", ["پیام‌رسان روبیکا", "صف پیام درون‌برنامه‌ای", "پاسخ‌گویی", "گزارش تحویل"]),
    ("omnicast", "OmniCast", "OC", "#146c94", "#35a4c7", "omni", ["صندوق ورودی یکپارچه", "پیام‌رسان‌ها", "قواعد مسیریابی", "رضایت مخاطب"]),
    ("marketmind-ai", "MarketMind AI", "MM", "#1f766e", "#62bd91", "market", ["داده‌های مجاز بازار", "روندها", "مقایسه رقبا", "فرضیه تحلیلی"]),
]

ICON_PATHS = {
    "calendar": '<rect x="20" y="23" width="56" height="50" rx="10"/><path d="M20 40h56M36 17v13m24-13v13M35 51h8m8 0h10M35 61h8m8 0h10"/>',
    "audience": '<circle cx="37" cy="36" r="11"/><circle cx="64" cy="40" r="9"/><path d="M17 73c2-15 10-23 21-23s20 8 21 23M55 56c12-3 23 4 25 17"/>',
    "radar": '<circle cx="48" cy="48" r="29"/><circle cx="48" cy="48" r="16"/><path d="M48 48 68 29M48 15v8m0 50v8M15 48h8m50 0h8"/><circle cx="64" cy="36" r="4"/>',
    "broadcast": '<rect x="34" y="34" width="28" height="28" rx="8"/><path d="M25 25a33 33 0 0 0 0 46m46-46a33 33 0 0 1 0 46M15 15a47 47 0 0 0 0 66m66-66a47 47 0 0 1 0 66"/>',
    "omni": '<rect x="14" y="20" width="30" height="24" rx="7"/><rect x="52" y="52" width="30" height="24" rx="7"/><path d="M44 32h18c8 0 12 5 12 12v8M52 64H34c-8 0-12-5-12-12v-8"/>',
    "market": '<path d="M18 73h62M24 66V45m17 21V30m17 36V39m17 27V20"/><path d="m22 34 18-12 17 7 20-14"/>',
}

for slug, name, initials, c1, c2, icon, labels in PRODUCTS:
    (ROOT / "logos").mkdir(parents=True, exist_ok=True)
    (ROOT / "mockups").mkdir(parents=True, exist_ok=True)
    logo = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160" role="img" aria-labelledby="title"><title id="title">{name} logo</title><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs><rect x="5" y="5" width="150" height="150" rx="40" fill="url(#g)"/><circle cx="126" cy="29" r="27" fill="#fff" opacity=".12"/><g fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" transform="translate(32 32)">{ICON_PATHS[icon]}</g><text x="80" y="137" text-anchor="middle" font-family="Arial,sans-serif" font-size="18" font-weight="700" fill="#fff">{initials}</text></svg>'''
    (ROOT / "logos" / f"{slug}.svg").write_text(logo)
    cards = "".join(f'<g transform="translate({90+i*255} 300)"><rect width="230" height="250" rx="22" fill="#fff"/><rect width="230" height="7" rx="4" fill="{c1}" opacity=".8"/><circle cx="34" cy="42" r="15" fill="{c2}" opacity=".25"/><text x="60" y="48" font-family="Tahoma,Arial" font-size="18" font-weight="bold" fill="#24324a">{escape(label)}</text><rect x="24" y="85" width="182" height="11" rx="5" fill="#e9edf4"/><rect x="24" y="111" width="142" height="11" rx="5" fill="#eef1f6"/><rect x="24" y="156" width="182" height="52" rx="12" fill="{c1}" opacity=".08"/><path d="M40 193l24-17 23 7 29-18 31 9 33-11" fill="none" stroke="{c2}" stroke-width="4" stroke-linecap="round"/></g>' for i, label in enumerate(labels))
    mockup = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 760" role="img" aria-labelledby="title desc"><title id="title">{name} — Concept Mockup</title><desc id="desc">تصویر مفهومی رابط آینده؛ نرم‌افزار اجراشده، داده واقعی یا اتصال فعال نیست.</desc><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs><rect width="1200" height="760" rx="38" fill="#f4f6fa"/><rect width="1200" height="92" rx="38" fill="url(#bg)"/><path d="M0 60h1200v32H0z" fill="url(#bg)"/><text x="70" y="57" font-family="Arial" font-size="27" font-weight="bold" fill="#fff">{name}</text><rect x="735" y="22" width="395" height="48" rx="24" fill="#fff" opacity=".96"/><text x="932" y="52" text-anchor="middle" direction="rtl" font-family="Tahoma,Arial" font-size="17" font-weight="bold" fill="#8a4b16">MOCKUP / تصویر مفهومی — نرم‌افزار اجراشده نیست</text><text x="90" y="170" direction="rtl" font-family="Tahoma,Arial" font-size="31" font-weight="bold" fill="#1c2940">پیش‌نمایش هدف طراحی، نه داشبورد واقعی</text><text x="90" y="213" direction="rtl" font-family="Tahoma,Arial" font-size="18" fill="#67748a">تمام داده‌ها نمایشی‌اند؛ هیچ اتصال، هوش مصنوعی یا اتوماسیون فعالی وجود ندارد.</text>{cards}<rect x="90" y="610" width="1020" height="82" rx="20" fill="#fff8e8" stroke="#e6c47f"/><text x="600" y="660" text-anchor="middle" direction="rtl" font-family="Tahoma,Arial" font-size="20" font-weight="bold" fill="#775520">Concept / در حال توسعه — بدون تضمین نتیجه تجاری یا پشتیبانی کامل پلتفرم</text></svg>'''
    (ROOT / "mockups" / f"{slug}-concept.svg").write_text(mockup)
print(f"Generated {len(PRODUCTS)} logos and {len(PRODUCTS)} explicitly-labelled concept mockups.")
