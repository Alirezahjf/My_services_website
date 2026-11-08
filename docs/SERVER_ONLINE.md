# راه‌اندازی کامل سایت روی سرور Ubuntu

این دستورها Flask را با **Gunicorn + systemd + Nginx + HTTPS** اجرا می‌کنند. مقادیر `services.example.com` و مسیر `/srv/services` را با دامنه و مسیر واقعی خود عوض کنید. دستور `create-admin` تعاملی است؛ رمز را در History، Git یا فایل پروژه وارد نکنید.

## ۱. اجرای محلی برای توسعه

```bash
git clone https://github.com/Alirezahjf/My_services_website.git
cd My_services_website
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python -c 'import secrets; print(secrets.token_hex(32))'
# خروجی بالا را به‌عنوان SECRET_KEY در .env قرار دهید.
flask --app run.py db upgrade
flask --app run.py seed-content
flask --app run.py create-admin
flask --app run.py run --debug --host 0.0.0.0 --port 9900
```

سایت روی `http://localhost:9900` و مدیریت روی `http://localhost:9900/admin/login` است. `--debug` فقط برای توسعه محلی است.

## ۲. آماده‌سازی سرور و کاربر محدود

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx sqlite3
sudo adduser --system --group --home /srv/services services
sudo mkdir -p /srv/services
sudo chown services:services /srv/services
```

## ۳. دریافت کد و نصب وابستگی‌ها

```bash
sudo -u services git clone https://github.com/Alirezahjf/My_services_website.git /srv/services/app
cd /srv/services/app
sudo -u services python3 -m venv .venv
sudo -u services .venv/bin/python -m pip install --upgrade pip
sudo -u services .venv/bin/pip install -r requirements.txt
sudo -u services cp .env.example .env
sudo -u services mkdir -p instance/uploads backups
```

فایل Environment را ویرایش کنید:

```bash
sudo -u services nano .env
```

حداقل مقادیر زیر را تنظیم کنید. مقدار کلید را با دستور تصادفی جداگانه بسازید:

```bash
sudo -u services .venv/bin/python -c 'import secrets; print(secrets.token_hex(32))'
```

```env
SECRET_KEY=REPLACE_WITH_GENERATED_RANDOM_VALUE
FLASK_ENV=production
SITE_URL=https://services.example.com
COOKIE_SECURE=true
DATABASE_URL=sqlite:////srv/services/app/instance/services.sqlite3
RATELIMIT_STORAGE_URI=memory://
PORT=9900
MCP_PORT=9901
```

برای چند Worker عملیاتی، Redis و PostgreSQL توصیه می‌شود؛ نمونه DSN در README است. با SQLite می‌توانید ابتدا از دو Worker شروع کنید و Backups منظم بگیرید. سپس دسترسی فایل رازها را محدود کنید:

```bash
sudo chmod 640 .env
sudo chown services:services .env
sudo chmod 750 instance instance/uploads
```

## ۴. Migration، داده اولیه و مدیر

```bash
cd /srv/services/app
sudo -u services .venv/bin/flask --app run.py db upgrade
sudo -u services .venv/bin/flask --app run.py seed-content
sudo -u services .venv/bin/flask --app run.py create-admin
```

Seed تکرارپذیر است، شش Concept و دسته‌های آن را بدون بازنویسی ویرایش‌های مدیر اضافه می‌کند. هیچ یک از Connectorهای Concept فعال یا متصل نمی‌شوند.

## ۵. سرویس systemd برای Gunicorn

```bash
sudo tee /etc/systemd/system/services-website.service >/dev/null <<'UNIT'
[Unit]
Description=HJF Services Flask website (Gunicorn)
After=network.target

[Service]
Type=notify
User=services
Group=services
WorkingDirectory=/srv/services/app
EnvironmentFile=/srv/services/app/.env
Environment=PATH=/srv/services/app/.venv/bin
ExecStart=/srv/services/app/.venv/bin/gunicorn --workers 2 --threads 4 --timeout 60 --bind 0.0.0.0:9900 --access-logfile - --error-logfile - "app:create_app()"
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=/srv/services/app/instance /srv/services/app/backups

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now services-website
sudo systemctl status services-website --no-pager
curl -I http://127.0.0.1:9900/
# پس از بازشدن پورت در فایروال، از سیستم دیگر نیز بررسی کنید:
curl -I http://PUBLIC_SERVER_IP:9900/
```

Gunicorn روی `0.0.0.0` اجرا می‌شود؛ بنابراین روی همه Interfaceها از جمله IP عمومی سرور Listen می‌کند، نه فقط localhost. مسیر مستقیم سایت `http://PUBLIC_SERVER_IP:9900` و مدیریت `http://PUBLIC_SERVER_IP:9900/admin/login` است. برای محیط نهایی بهتر است کاربران از دامنه HTTPS وارد شوند و دسترسی مستقیم پورت 9900 محدود شود. برای تغییرات بعدی:

```bash
cd /srv/services/app
sudo -u services git pull
sudo -u services .venv/bin/pip install -r requirements.txt
sudo -u services .venv/bin/flask --app run.py db upgrade
sudo systemctl restart services-website
sudo journalctl -u services-website -n 100 --no-pager
```

### سرویس مستقل MCP

MCP با Uvicorn و SDK رسمی روی پورت 9901 اجرا می‌شود و دیتابیس و Secret وب‌سایت را از همان Environment می‌خواند:

```bash
sudo cp deploy/services-mcp.service /etc/systemd/system/services-mcp.service
sudo systemctl daemon-reload
sudo systemctl enable --now services-mcp
sudo systemctl restart services-website services-mcp
sudo systemctl is-active services-website services-mcp
curl -i http://127.0.0.1:9901/mcp
# پاسخ 401 بدون Bearer Token نشانه اجرای درست محافظت است.
```

آدرس آزمایشی `http://PUBLIC_SERVER_IP:9901/mcp` است. برای اتصال از بیرون در حالت آزمایش `sudo ufw allow 9901/tcp` را اجرا کنید. Token را در `/admin/agents` بسازید؛ آدرس و نمونه Client در `docs/AI_AGENTS.md` آمده است. هر بار تغییر کد یا Migration، هر دو سرویس را Restart کنید.

## ۶. Nginx به‌عنوان Reverse Proxy

```bash
sudo tee /etc/nginx/sites-available/services-website >/dev/null <<'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name services.example.com;

    client_max_body_size 32m;

    location / {
        proxy_pass http://127.0.0.1:9900;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }
}

server {
    listen 80;
    listen [::]:80;
    server_name mcp.services.example.com;
    client_max_body_size 1m;

    location /mcp {
        proxy_pass http://127.0.0.1:9901;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 75s;
        proxy_buffering off;
    }
}
NGINX
sudo ln -sfn /etc/nginx/sites-available/services-website /etc/nginx/sites-enabled/services-website
sudo nginx -t
sudo systemctl reload nginx
```

رکورد DNS نوع `A` و در صورت استفاده `AAAA` دامنه باید پیش از Certbot به IP سرور اشاره کند. پورت‌ها را باز کنید:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
# برای دسترسی مستقیم به Flask/Gunicorn با IP عمومی و پورت 9900:
sudo ufw allow 9900/tcp
sudo ufw enable
```

ورود ادمین روی HTTP عمومی رمزنگاری نمی‌شود. پورت 9900 را فقط برای آزمایش اولیه یا از IP مدیریتی مجاز باز کنید؛ پس از فعال‌شدن HTTPS می‌توانید دسترسی عمومی آن را با `sudo ufw delete allow 9900/tcp` ببندید. در این حالت نیز Gunicorn روی `0.0.0.0` باقی می‌ماند و Nginx از طریق Loopback به آن متصل می‌شود.

## ۷. HTTPS با Certbot

```bash
sudo certbot --nginx -d services.example.com -d mcp.services.example.com --redirect --hsts --staple-ocsp
sudo certbot renew --dry-run
sudo systemctl status certbot.timer --no-pager
curl -I https://services.example.com/
```

پس از فعال‌شدن HTTPS، `COOKIE_SECURE=true` و `SITE_URL=https://services.example.com` باید در `.env` باشند؛ سپس:

```bash
sudo systemctl restart services-website
```

## ۸. بررسی نهایی و پشتیبان

```bash
sudo systemctl is-active services-website services-mcp nginx
curl -fsS https://services.example.com/ >/dev/null
curl -fsS https://services.example.com/admin/login >/dev/null
cd /srv/services/app
sudo -u services bash scripts/backup.sh
```

پشتیبان‌ها را خارج از سرور نیز نگه دارید و Restore را آزمایش کنید. رمز مدیر، `SECRET_KEY`، توکن GitHub و فایل `.env` هرگز نباید وارد Git، HTML، JavaScript یا Log شوند.
