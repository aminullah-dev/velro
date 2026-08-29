# ADR 0002 — Perso-Arabic typography

## Status
Closed, 29 August 2026. Vazirmatn is bundled in Regular, Medium and Bold, and
both APKs carry it. Noto Naskh Arabic was the first choice and was replaced the
same day -- see "Why Vazirmatn and not Noto Naskh" below.

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

## How it was closed
1. The three weights sit in `mobile/core/ui/src/main/res/font/` as
   `noto_naskh_arabic_regular.ttf`, `_medium.ttf` and `_bold.ttf`.

   Google ships this family as a single variable font with a `wght` axis. That
   would have been one smaller file, but `minSdk` is 24 and Android only honours
   variable axes from API 26 -- on Android 7 every weight would have rendered at
   400, which is the synthesised-bold problem arriving by another route. The
   three static instances were cut from the variable original with
   `fonttools varLib.instancer`, so they are the same outlines at fixed weights.

2. The licence is at `mobile/core/ui/src/main/assets/licences/`, not beside the
   fonts: Android's `res/font/` directory rejects any file that is not a font,
   so `assets/` is where a text notice can actually ship. It is in both APKs.

3. `VelroFonts.persoArabic` names the three weights. `SemiBold` maps to the
   Medium file rather than being left to synthesis -- the type scale asks for
   SemiBold in several places and there is no such cut.

4. Verified two ways. `FontCoverageTest` reads the real files and asserts every
   bundled weight covers `ټ ډ ړ ږ ښ ګ ڼ ې ۍ`, that bold is not a relabelled copy
   of regular, and that the licence ships. The font directory is declared as a
   test input, without which Gradle considered the task up to date after a font
   was swapped and the guard passed on a file it never opened. The Pashto UI was
   then rendered on a device with no boxes.

## Why Vazirmatn and not Noto Naskh

Six freely licensed candidates were compared: Noto Naskh Arabic, Noto Sans
Arabic, Noto Kufi Arabic, IBM Plex Sans Arabic, Scheherazade New, Lateef and
Vazirmatn. All seven are OFL and all seven cover the nine Pashto letters, the
Persian letters and the Eastern digits -- coverage did not decide it.

Two things did.

**Drawn for screens, not for books.** Noto Naskh is a calligraphic text face
with fine strokes and traditional proportions. Vazirmatn has sturdier stems and
more open counters, which is what survives a cheap phone held in daylight. The
audience reads with difficulty on hardware chosen for price.

**Already familiar.** Vazirmatn is the face most Persian and Dari interfaces
use. It reads as ordinary rather than foreign, which for an app being handed to
someone at a station matters more than typographic novelty.

It is also smaller: 123 KB a weight against 196 KB, so 370 KB per APK rather
than 588 KB.

A caution worth recording: the first comparison was rendered with Pillow and
`arabic-reshaper`, which showed Vazirmatn dropping Pashto letters and
Scheherazade New collapsing entirely. Both were artefacts of a naive shaper.
Re-run through HarfBuzz -- which is what Android actually uses -- every
candidate shaped the Pashto string with no missing glyph. **Do not judge an
Arabic-script font with a renderer that does not do real OpenType shaping.**

The same comparison found that only IBM Plex Sans Arabic carries U+2190, the
leftwards arrow. Three screens were joining place names with " ← ", which on
every other face falls back to whatever the handset has. Those now read
"از X به Y" instead: words, not a symbol that needs a font, a convention and a
direction to be understood.

## Consequences
370 KB added to each APK, well under the estimate because the instanced statics
are smaller than the hinted originals. Worth it: the alternative is a
product unreadable in one of its two primary languages on an unknown share of
devices, failing invisibly on a developer's phone.

Latin stays on the system sans. It is well covered everywhere, and a second
bundled family would cost as much again for no legibility gained.
