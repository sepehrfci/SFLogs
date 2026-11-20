# SFLogs

دفتر کار و پیگیری عملیات شخصی برای مهندس دواپس؛ ساخته‌شده با Flask و SQLite.

داشبورد اصلی شامل تابلوی کانبان شش‌مرحله‌ای با کارت‌های قابل drag-and-drop، خلاصه‌ی کارهای باز و رخدادهای اخیر است.

## تنظیم اولیه دسترسی

برنامه بدون تنظیم دسترسی اجرا نمی‌شود. فایل نمونه را کپی و سه مقدار محرمانه را تنظیم کن:

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

خروجی دستور را به‌عنوان `SFLOGS_SECRET_KEY` در `.env` قرار بده و `SFLOGS_USERNAME` و `SFLOGS_PASSWORD` را هم تنظیم کن. گذرواژه باید حداقل ۱۲ نویسه داشته باشد. فایل `.env` در Git نادیده گرفته می‌شود؛ آن را commit نکن.

## اجرای محلی

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

برنامه فایل `.env` کنار `app.py` را هنگام اجرای مستقیم به‌صورت خودکار می‌خواند. برای نصب وابستگی جدید و اجرای برنامه:

```bash
pip install -r requirements.txt
python app.py
```

برنامه در `http://localhost:5000` اجرا می‌شود و دیتابیس را در `data/sflogs.sqlite3` می‌سازد.

صفحه‌ی «گزارش‌ها» در `/reports` گزارش این هفته یا ماه را نشان می‌دهد. بازه‌ی تاریخ، سرویس و محیط را می‌توان فیلتر کرد و نتیجه‌ی همان فیلتر را به CSV خروجی گرفت.

## اجرای Docker

```bash
docker compose up --build -d
```

Compose مقدارهای `.env` را می‌خواند. برنامه به‌طور پیش‌فرض فقط روی localhost پورت 5000 را باز می‌کند؛ اگر آن را پشت reverse proxy با HTTPS قرار دادی، `SFLOGS_COOKIE_SECURE=true` تنظیم کن. volume داده با نام `sflogs_data` و volume نسخه‌های پشتیبان با نام `sflogs_backups` ساخته می‌شود.

سرویس `backup` پس از آماده‌شدن دیتابیس، هر ۲۴ ساعت یک snapshot سازگار SQLite می‌سازد و ۱۴ نسخه‌ی آخر را نگه می‌دارد. برای ساخت snapshot دستی:

```bash
docker compose exec backup python backup.py
```

برای بازیابی، ابتدا سرویس‌ها را متوقف کن و نام فایل snapshot موردنظر را جایگزین کن:

```bash
docker compose stop sflogs backup
docker compose run --rm --no-deps backup python backup.py --restore /app/backups/sflogs-YYYYMMDDTHHMMSSZ.sqlite3
docker compose up -d
```

snapshotهای خودکار روی همان میزبان و در volume جدا ذخیره می‌شوند؛ برای تاب‌آوری در برابر خرابی میزبان، volume پشتیبان را به محل دیگری نیز کپی کن.

## فازبندی پیشنهادی

1. **دفتر کار و اینسیدنت‌ها:** ثبت گزارش روزانه، سرویس و محیط، زمان صرف‌شده، ثبت و پیگیری وضعیت اینسیدنت، علت، راهکار و اقدام بعدی؛ داشبورد اولیه.
2. **مدیریت کارها (فعلی):** برد کانبان، اولویت، موعد و پیوند اقدام‌های پس از اینسیدنت به کارت‌های پیگیری.
3. **گزارش‌ها (فعلی):** فیلتر تاریخ/سرویس/محیط، گزارش هفتگی و ماهانه، خروجی CSV و روند زمان رسیدگی به اینسیدنت‌ها.
4. **عملیاتی‌سازی (فعلی):** ورود تک‌کاربره، محافظت CSRF، cookie امن نشست، bind محلی Docker، سلامت‌سنجی و پشتیبان‌گیری/بازیابی SQLite.

## CI

Workflow موجود در `.github/workflows/ci.yml` روی push و pull request syntax پایتون را بررسی و Docker image را build می‌کند. Workflow فایل `.github/workflows/release.yml` با push یک tag مانند `v0.1.0` image را به `ghcr.io/<owner>/<repository>` منتشر می‌کند؛ برای انتشار، مجوز Packages در تنظیمات GitHub Actions مخزن باید فعال باشد.

## دیپلوی خودکار

بعد از موفقیت انتشار GHCR، job دیپلوی با SSH به سرور وصل می‌شود، `compose.yaml` را به‌روز می‌کند، image تگ‌شده را می‌کشد و سرویس را بالا می‌آورد. تا زمان healthy شدن health check صبر می‌کند و اگر سرویس سالم نشود، تلاش می‌کند image قبلی را برگرداند. دیپلوی با push کردن tag نسخه مثل `v1.0.1` آغاز می‌شود.

در GitHub برو به **Settings → Secrets and variables → Actions** و این Repository secrets را اضافه کن:

- `DEPLOY_HOST`: IP یا نام میزبان SSH
- `DEPLOY_PORT`: پورت SSH سرور؛ اختیاری است و اگر حذف شود 22 استفاده می‌شود
- `DEPLOY_USER`: کاربر SSH که اجازه‌ی اجرای Docker Compose دارد
- `DEPLOY_PATH`: مسیر مطلق پوشه‌ی فعلی استقرار، شامل فایل `.env`؛ همین مسیر قبلی را استفاده کن تا volume داده به پروژه‌ی Compose دیگری اشاره نکند
- `DEPLOY_SSH_KEY`: کلید خصوصی SSH؛ کلید عمومی متناظر باید در `authorized_keys` کاربر سرور باشد
- `DEPLOY_KNOWN_HOSTS`: کلید میزبان SSH سرور با اثر انگشتی که از مسیر مورداعتماد تأیید کرده‌ای

پوشه‌ی استقرار و `.env` باید از قبل روی سرور موجود باشند. اگر package در GHCR خصوصی است، سرور باید از قبل با `docker login ghcr.io` و توکنی با دسترسی `read:packages` وارد شده باشد. توکن GHCR را در workflow قرار نده. سرور هم باید از runnerهای GitHub روی SSH قابل دسترسی باشد؛ برای میزبان خصوصی پشت NAT از self-hosted runner استفاده کن.

### ساخت کلید SSH برای GitHub Actions

روی سیستم خودت یک کلید مخصوص deploy بساز (برای استفاده‌ی غیرتعاملی Actions بدون passphrase):

```bash
ssh-keygen -t ed25519 -C "github-actions-sflogs" -f ./sflogs_deploy -N ""
```

کلید عمومی را به کاربر deploy سرور اضافه کن:

```bash
ssh-copy-id -i ./sflogs_deploy.pub -p PORT USER@HOST
```

در GitHub secret به نام `DEPLOY_SSH_KEY`، **تمام محتوای فایل خصوصی** `sflogs_deploy` را قرار بده؛ فایل `.pub` را آنجا نگذار و کلید خصوصی را در مخزن commit نکن.

برای مقدار `DEPLOY_KNOWN_HOSTS`، کلید میزبان سرور را با پورت واقعی دریافت کن:

```bash
ssh-keyscan -p PORT -t ed25519 HOST
```

خروجی را فقط پس از تطبیق fingerprint با مقداری که از کنسول یا مسیر مورداعتماد سرور گرفته‌ای، در secret `DEPLOY_KNOWN_HOSTS` بگذار. برای پورت غیرپیش‌فرض، خروجی کلید میزبان به شکل `[HOST]:PORT` است. همان پورت را در secret `DEPLOY_PORT` وارد کن.
