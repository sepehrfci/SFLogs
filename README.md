# SFLogs

دفتر کار و پیگیری عملیات شخصی برای مهندس دواپس؛ ساخته‌شده با Flask و SQLite.

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

برای بارگذاری مقادیر در shell و اجرای برنامه:

```bash
set -a
source .env
set +a
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
