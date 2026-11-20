# SFLogs

دفتر کار و پیگیری عملیات شخصی برای مهندس دواپس؛ ساخته‌شده با Flask و SQLite.

## اجرای محلی

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

برنامه در `http://localhost:5000` در دسترس است و دیتابیس را در `data/sflogs.sqlite3` می‌سازد.

## اجرای Docker

```bash
docker compose up --build -d
```

سپس به `http://localhost:5000` برو. داده‌ها در volume به نام `sflogs_data` باقی می‌مانند. برای اجرا روی سرور، مقدار `SFLOGS_SECRET_KEY` را در محیط تنظیم کن.

## فازبندی پیشنهادی

1. **دفتر کار و اینسیدنت‌ها (فعلی):** ثبت گزارش روزانه، سرویس و محیط، زمان صرف‌شده، ثبت و پیگیری وضعیت اینسیدنت، علت، راهکار و اقدام بعدی؛ داشبورد اولیه.
2. **مدیریت کارها:** برد کانبان، اولویت، موعد، برچسب، کارهای مسدود و پیوند اقدام‌های پس از اینسیدنت به کارت‌های پیگیری.
3. **گزارش‌ها:** فیلتر تاریخ/سرویس/محیط، گزارش هفتگی و ماهانه، خروجی CSV و روند زمان رسیدگی به اینسیدنت‌ها.
4. **عملیاتی‌سازی:** نسخه پشتیبان و بازیابی SQLite، احراز هویت در صورت نیاز به دسترسی شبکه‌ای و بهبود امنیت فرم‌ها.

## CI

Workflow موجود در `.github/workflows/ci.yml` روی push و pull request syntax پایتون را بررسی و Docker image را build می‌کند. Workflow فایل `.github/workflows/release.yml` با push یک tag مانند `v0.1.0` image را به `ghcr.io/<owner>/<repository>` منتشر می‌کند؛ برای انتشار، مجوز Packages در تنظیمات GitHub Actions مخزن باید فعال باشد.
