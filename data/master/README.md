# Master data — Ghorband, Parwan

`ghorband-villages-source.md` is the list as supplied, kept verbatim.
`convert_villages.py` turns it into `ghorband-villages.csv`, which is what the
importer reads. The conversion is deliberately mechanical: it splits a
parenthetical into an alias and changes nothing else. No spelling is corrected,
no duplicate dropped, no coordinate invented — whatever is wrong in the source
stays wrong in the CSV, so the importer's validation is what finds it.

## Importing

```
python3 data/master/convert_villages.py > data/master/ghorband-villages.csv
```

Then, as an operator: **وارد کردن قریه‌ها** → upload → review the preview →
commit. Afterwards run **مسیرها و قیمت → تولید مسیرها** (`POST
/admin/routes/generate`), or the imported stations have no routes and nothing
can be booked from them.

## The 19 rows the importer flagged

Nothing was merged. These were skipped and need a decision from someone who
knows Ghorband; accepting a row creates a second village with that name, which
is correct when they really are two places.

### Already in the database (5)
The development seed sampled these villages before the real list arrived. The
existing record stands.

| Row | In the file | Already stored | Note |
|---|---|---|---|
| 2 | خیشکی | خیشکی | same |
| 94 | دره‌قول‌خول | دره‌قول‌خول | same |
| 142 | قلعه‌نو | قلعه نو | differs only by a space; the source spelling is the one to keep |
| 176 | صدوار | صدوار | same |
| 390 | سرخ پارسا | بازار سرخ‌پارسا | **likely two places** — a village and its bazaar |

### Repeated inside the file (14)

Marked by the compiler:

| Row | Name | Note |
|---|---|---|
| 29 | دوآبه | the source marks it `(تکرار)` — a repeat of row 22 |

A block of شیخ‌علی repeated at the end of its table (items 26–31 repeat 3, 8,
11–14). Almost certainly a copy-paste when the list was compiled:

| Rows | Names |
|---|---|
| 429–434 | جرف · نرخ · ناوی · قرلق · کرم‌علی · بابر |

Same name, twice, and **it cannot be told from the list whether these are one
place or two.** Afghanistan has many same-named villages, and without
coordinates there is nothing here to decide it on:

| Rows | District | Name |
|---|---|---|
| 77, 148 | سیاه‌گرد | گداره |
| 128, 170 | سیاه‌گرد | قلعچه |
| 201, 202 | شینواری | آب‌خانه اشترشهر — the second is `(قلعه محمود)`, so probably a different place |
| 380, 381 | سرخ پارسا | شیبرک |
| 382–384 | سرخ پارسا | شینه (three times) |
| 393, 394 | سرخ پارسا | تنگی |

### One row worth checking at source

شیخ‌علی #32 is the single letter `ای`. It imported as a village of that name.
It reads like a truncated entry rather than a place.

## What is not here

No coordinates. The source says they must not be guessed, and nothing here
guesses them. Until they are supplied, `nearby` search cannot rank a station by
distance — it has no distance to rank by.
