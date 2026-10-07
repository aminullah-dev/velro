# ۰۶ — ویدیو

ویدیوهای متحرکِ ویلرو حالا با پروژهٔ **Remotion** ساخته می‌شوند، نه اینجا.

- **جای ساختِ ویدیو:** `~/Velro/motion/` (در همین ریپو: `motion/`).
  - پیش‌نمایش زنده: `cd ~/Velro/motion && npm run studio`
  - رندر: `cd ~/Velro/motion && npx remotion render <id> out/<id>.mp4 --codec=h264 --crf=18`
  - همهٔ compositionها (StoryFilm، GhorbandDrive، AcceptRide، RequestRide،
    RouteMap، SeatFill، LogoReveal، StatsCounter، DayToNight، NowOnAppStore …)
    و راهنمای کامل در `motion/README.md`.

## این پوشه

- `exports/` — نسخهٔ نهاییِ mp4ها که از پروژهٔ Remotion بیرون آمده و برای
  آپلود (فیس‌بوک/اینستاگرام) اینجا کپی شده. در گیت ذخیره نمی‌شوند (`*.mp4`
  در `.gitignore`)؛ فقط یک کتابخانهٔ محلیِ آمادهٔ آپلود است.
- `archive/` — نسخهٔ **قدیمیِ** تیزر که با canvas ساده ساخته شده بود
  (`teaser-ghorband.html` + `render-video.sh`). با Remotion جایگزین شد؛ فقط
  برای مرجع نگه داشته شده.
