# ADR 0002 — Perso-Arabic typography

## Status
Closed, 29 August 2026. Noto Naskh Arabic is bundled in Regular, Medium and
Bold, and both APKs carry it.

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

## Consequences
588 KB added to each APK, at the low end of the estimate because the instanced
statics are smaller than the hinted originals. Worth it: the alternative is a
product unreadable in one of its two primary languages on an unknown share of
devices, failing invisibly on a developer's phone.

Latin stays on the system sans. It is well covered everywhere, and a second
bundled family would cost as much again for no legibility gained.
