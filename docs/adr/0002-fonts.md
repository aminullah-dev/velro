# ADR 0002 — Perso-Arabic typography

## Status
Open. The seam is built; the font file itself is outstanding.

## Context
VELRO ships in Dari and Pashto before English. Both are written in Perso-Arabic
script, and Pashto uses seven consonants and two vowels that Persian does not:
`ټ ډ ړ ږ ښ ګ ڼ ې ۍ`.

Android's system font varies by manufacturer. Several handsets common in the
Afghan market — particularly inexpensive devices built for the Chinese domestic
market and re-exported — ship a Perso-Arabic font covering Persian and Arabic
but not Pashto. On those devices Pashto text renders with tofu boxes for exactly
the letters that distinguish one word from another.

`platform-core/references/localization-rtl.md` is explicit: bundle the family,
do not rely on the system font.

## Decision
Bundle a Perso-Arabic family with verified Pashto coverage, in Regular, Medium
and Bold. Ship the real weights; never synthesise bold, which smears the joins
in Naskh forms.

Noto Naskh Arabic (SIL Open Font License 1.1) is the intended choice: it is
freely redistributable, has the required coverage, and is already the reference
face for this script on Android.

## Current state
Not yet bundled. `VelroFonts.familyFor` falls back to `FontFamily.Default`, so
Pashto will show tofu on affected devices until this is closed.

## To close this
1. Place `NotoNaskhArabic-Regular.ttf`, `-Medium.ttf` and `-Bold.ttf` in
   `mobile/core/ui/src/main/res/font/`, named in lower snake case as Android
   requires (`noto_naskh_arabic_regular.ttf` and so on).
2. Add `OFL.txt` beside them; the licence requires the notice to ship.
3. Replace the body of `VelroFonts.familyFor` with a `FontFamily` naming the
   three weights.
4. Render this string on a device and confirm no box appears:
   `ټول ډېر ړوند ږغ ښکلی ګوته ڼه ېې ۍ`

## Consequences
Roughly 1–1.5 MB added to each APK. That is worth it: the alternative is a
product that is unreadable in one of its two primary languages on an unknown
share of devices, and the failure is invisible during development on a
developer's phone.
