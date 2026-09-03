"""What VELRO knows about a person, said plainly, at one public address.

An app that asks for a passenger's location and photographs a driver's
tazkira owes its users a page that says so -- and Google will not let the
backup's own sign-in leave "testing" without one. It lives here, beside the
download page, because api.velro.linumic.com/app is already the address said
aloud in a bazaar; /privacy is the same door one step over.

Dari first, then English. Every sentence below describes something the code
actually does; when the code changes, this page changes in the same commit.
"""

# ruff: noqa: E501 -- the page below is prose; a sentence of Dari wrapped at
# a hundred columns is harder to proofread than one left whole.

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

page_router = APIRouter(tags=["release"])

CONTACT = "aminhashemi979@gmail.com"
EFFECTIVE = "۱۱ سنبله ۱۴۰۵ — 2 September 2026"

_PAGE = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>سیاست حریم خصوصی ولرو · VELRO Privacy Policy</title>
<style>
 body { font-family: system-ui, "Noto Sans Arabic", sans-serif; background: #f6f8f6;
        color: #17211c; margin: 0; padding: 2rem 1.25rem 4rem; line-height: 1.8; }
 main { max-width: 42rem; margin: 0 auto; }
 h1 { color: #0e4d3c; font-size: 1.8rem; margin: 0 0 .25rem; }
 h2 { color: #0e4d3c; font-size: 1.2rem; margin: 2rem 0 .5rem; }
 p, li { margin: .4rem 0; }
 ul { padding-inline-start: 1.4rem; }
 .meta { color: #5f6e66; font-size: .9rem; }
 .en { direction: ltr; text-align: left; border-top: 1px solid #dce3de; margin-top: 3rem; padding-top: 2rem; }
 a { color: #0e4d3c; }
</style>
</head>
<body>
<main>
<h1>سیاست حریم خصوصی ولرو</h1>
<p class="meta">نافذ از {effective} · مالک: لینومیک (Linumic) · تماس: <a href="mailto:{contact}">{contact}</a></p>

<p>ولرو یک خدمت رزرو سفر بین‌شهری برای کابل، پروان و غوربند است: یک اپ برای مسافر، یک اپ برای راننده، و سروری که این دو را به هم می‌رساند. این صفحه می‌گوید چه معلوماتی از شما می‌گیریم، چرا، با چه کسی شریک می‌شود، و چطور می‌توانید آن را ببینید یا پاک کنید.</p>

<h2>۱. چه چیزی جمع می‌کنیم</h2>
<ul>
<li><strong>شمارهٔ تیلفون و نام.</strong> شماره هویت شما در ولرو است؛ کود ورود به همان شماره (از طریق پیامک یا تلگرام) فرستاده می‌شود. کارمندان لینومیک می‌توانند کود را با ایمیل بگیرند.</li>
<li><strong>موقعیت.</strong> مسافر: یک بار، در لحظهٔ درخواست یا رزرو، تا مطمئن شویم داخل ساحهٔ خدمات هستید. راننده: به‌طور مداوم تا وقتی آنلاین یا در سفر است، تا مسافر موتر را روی نقشه ببیند و راننده هشدارهای جاده را بگیرد. وقتی آفلاین شوید، فرستادن موقعیت متوقف می‌شود.</li>
<li><strong>مدارک رانندگان.</strong> عکس تذکره، جواز رانندگی و جواز سیر موتر، نمبر پلیت و مشخصات موتر، و عکس پروفایل — برای تأیید اینکه چه کسی پشت فرمان است.</li>
<li><strong>سفرها.</strong> درخواست‌ها، پیشنهادهای کرایه، رزروها، کرایهٔ توافق‌شده، کود سوارشدن، امتیازها، لغوها و دلیل‌شان، و گزارش‌های امنیتی یا شکایت‌هایی که خودتان ثبت می‌کنید.</li>
<li><strong>معلومات فنی.</strong> شناسهٔ دستگاه برای اعلان‌ها؛ گزارش کرش (نسخهٔ اپ، مدل دستگاه، متن خطا — بدون نام یا شماره)؛ و لاگ درخواست‌ها (زمان و آی‌پی) برای امنیت.</li>
</ul>

<h2>۲. برای چه استفاده می‌شود</h2>
<p>برای اینکه سفر انجام شود: مسافر و راننده همدیگر را پیدا کنند و به هم زنگ بزنند؛ راننده‌ها تأیید شوند؛ کرایه و کمیشن حساب شود؛ به گزارش امنیتی رسیدگی شود؛ و خرابی‌های اپ پیدا و رفع شود. برای تبلیغات استفاده نمی‌شود.</p>

<h2>۳. چه کسی می‌بیند</h2>
<ul>
<li><strong>طرف دیگر سفر.</strong> مسافر نام، عکس، نمبر پلیت و شمارهٔ تیلفون رانندهٔ خود را می‌بیند. راننده شمارهٔ تیلفون و نمبر رزرو مسافر خود را می‌بیند، نه نام او را.</li>
<li><strong>کارمندان لینومیک</strong> که عملیات و پشتیبانی را انجام می‌دهند، به اندازهٔ کارشان.</li>
<li><strong>خدمات‌دهنده‌ها.</strong> ارسال کود ورود از طریق Twilio (پیامک)، تلگرام، یا Google (ایمیل). سرور ولرو نزد Hetzner در اروپا است. نسخهٔ پشتیبان دیتابیس هر شب در Google Drive لینومیک نگهداری می‌شود.</li>
</ul>
<p>معلومات شما فروخته نمی‌شود و به هیچ تبلیغ‌کننده‌ای داده نمی‌شود.</p>

<h2>۴. تا کی نگه داشته می‌شود</h2>
<p>تا وقتی حساب شما فعال است. کود ورود چند دقیقه بعد از بین می‌رود. نسخهٔ پشتیبان ۱۴ روز روی سرور می‌ماند و کاپی‌های آن برای بازیابی در حادثه نگهداری می‌شود. اگر بخواهید حساب‌تان پاک شود، بنویسید؛ معلومات حساب پاک می‌شود و فقط آنچه برای حساب‌وکتاب کرایه‌ها لازم است، بدون نام، می‌ماند.</p>

<h2>۵. حق شما</h2>
<p>می‌توانید بپرسید چه چیزی از شما داریم، آن را اصلاح کنید، یا حذفش را بخواهید — از داخل اپ («کمک بگیرید») یا با ایمیل به <a href="mailto:{contact}">{contact}</a>. اجازهٔ موقعیت را هر وقت خواستید از تنظیمات تیلفون بردارید؛ بدون آن، مسافر نمی‌تواند درخواست بدهد.</p>

<h2>۶. امنیت</h2>
<p>همهٔ ارتباط اپ با سرور رمزگذاری‌شده (HTTPS) است. کود ورود روی سرور به‌شکل هش نگه داشته می‌شود، نه متن ساده. مدارک رانندگان فقط برای کارمندان مجاز قابل دیدن است و در مرورگر یا پراکسی ذخیره نمی‌شود.</p>

<h2>۷. تغییرات</h2>
<p>اگر این سیاست عوض شود، نسخهٔ جدید همین‌جا با تاریخ جدید می‌نشیند.</p>

<section class="en" lang="en">
<h1>VELRO Privacy Policy</h1>
<p class="meta">Effective {effective} · Operated by Linumic · Contact: <a href="mailto:{contact}">{contact}</a></p>

<p>VELRO is an intercity ride-booking service for Kabul, Parwan and Ghorband: one app for passengers, one for drivers, and a server that connects them. This page says what we collect, why, who sees it, and how you can see or delete it.</p>

<h2>1. What we collect</h2>
<ul>
<li><strong>Phone number and name.</strong> Your number is your identity on VELRO; the sign-in code goes to it by SMS or Telegram. Linumic staff may receive their code by email.</li>
<li><strong>Location.</strong> Passengers: once, at the moment of asking or booking, to confirm you are inside the service area. Drivers: continuously while online or on a trip, so the passenger can see the car on the map and the driver receives road warnings. Going offline stops it.</li>
<li><strong>Driver documents.</strong> Photographs of the tazkira, the driving licence and the vehicle permit, the number plate and vehicle details, and a profile photo — to verify who is behind the wheel.</li>
<li><strong>Trips.</strong> Requests, fare offers, bookings, the agreed fare, the boarding code, ratings, cancellations and their reasons, and any safety report or complaint you file.</li>
<li><strong>Technical data.</strong> A device token for notifications; crash reports (app version, device model, error text — no name or number); and request logs (time and IP address) for security.</li>
</ul>

<h2>2. What it is used for</h2>
<p>To make the trip happen: so passenger and driver can find and call each other; to verify drivers; to account for fares and commission; to act on safety reports; and to find and fix app failures. It is not used for advertising.</p>

<h2>3. Who sees it</h2>
<ul>
<li><strong>The other side of your trip.</strong> A passenger sees their driver's name, photo, number plate and phone number. A driver sees their passenger's phone number and booking number, not their name.</li>
<li><strong>Linumic staff</strong> running operations and support, to the extent their work requires.</li>
<li><strong>Service providers.</strong> Sign-in codes are delivered through Twilio (SMS), Telegram, or Google (email). The VELRO server is hosted by Hetzner in Europe. A database backup is stored nightly in Linumic's Google Drive.</li>
</ul>
<p>Your data is not sold and is not given to advertisers.</p>

<h2>4. How long it is kept</h2>
<p>For as long as your account is active. Sign-in codes expire within minutes. Backups stay on the server for 14 days, and copies are kept for disaster recovery. If you ask for your account to be deleted, account data is removed and only what is needed for fare accounting is kept, without your name.</p>

<h2>5. Your rights</h2>
<p>You can ask what we hold about you, correct it, or ask for it to be deleted — from inside the app ("Get help") or by email to <a href="mailto:{contact}">{contact}</a>. You can withdraw location permission in your phone's settings at any time; without it, a passenger cannot ask for a ride.</p>

<h2>6. Security</h2>
<p>All traffic between the apps and the server is encrypted (HTTPS). Sign-in codes are stored hashed, never in plain text. Driver documents are visible only to authorised staff and are never cached by browsers or proxies.</p>

<h2>7. Changes</h2>
<p>If this policy changes, the new version appears here with a new date.</p>
</section>
</main>
</body>
</html>"""


@page_router.get("/privacy", response_class=HTMLResponse)
def privacy_page() -> str:
    return _PAGE.replace("{effective}", EFFECTIVE).replace("{contact}", CONTACT)
