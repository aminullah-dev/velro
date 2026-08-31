package af.velro.core.ui.theme

import af.velro.core.i18n.Strings
import af.velro.domain.Locale
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.text.TextStyle
import af.velro.core.ui.R
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.sp

/** The active locale, so any composable can format a number or a date correctly. */
val LocalVelroStrings = staticCompositionLocalOf<Strings> {
    error("no Strings provided; wrap the screen in VelroTheme")
}

val LocalVelroLocale = staticCompositionLocalOf { Locale.DARI }

/**
 * Whether the dark scheme is the one in force.
 *
 * Read rather than recomputed: `isSystemInDarkTheme()` is what VelroTheme
 * *defaults* to, not necessarily what it was given, and a component that asked
 * the system directly would disagree with the theme around it the moment a
 * caller overrode it. Components that must pick a colour pair themselves --
 * the status chips, which have five tones and no matching set of scheme roles
 * -- ask this.
 */
val LocalVelroDarkTheme = staticCompositionLocalOf { false }

private val LightScheme = lightColorScheme(
    primary = VelroColors.Green700,
    onPrimary = VelroColors.White,
    primaryContainer = VelroColors.Green50,
    onPrimaryContainer = VelroColors.Green900,
    secondary = VelroColors.Amber600,
    onSecondary = VelroColors.White,
    secondaryContainer = VelroColors.Amber100,
    onSecondaryContainer = VelroColors.Neutral900,
    error = VelroColors.Red700,
    onError = VelroColors.White,
    errorContainer = VelroColors.Red100,
    onErrorContainer = VelroColors.Red700,
    // The page is a shade off white so that a white card sits *on* it. Both
    // were white, which left a hairline border doing all the work of saying
    // where a card began -- the flatness the design read as.
    background = VelroColors.Neutral50,
    onBackground = VelroColors.Neutral900,
    surface = VelroColors.White,
    onSurface = VelroColors.Neutral900,
    surfaceVariant = VelroColors.Neutral100,
    onSurfaceVariant = VelroColors.Neutral700,
    // outline carries meaning -- it is the edge of a control -- so it owes 3:1.
    // outlineVariant is a decorative divider and does not.
    outline = VelroColors.Neutral400,
    outlineVariant = VelroColors.Neutral200,
)

private val DarkScheme = darkColorScheme(
    primary = VelroColors.Green200,
    onPrimary = VelroColors.Green900,
    primaryContainer = VelroColors.Green800,
    onPrimaryContainer = VelroColors.Green100,
    secondary = VelroColors.Amber500,
    onSecondary = VelroColors.Neutral900,
    // Five roles used to be left to Material here, and Material's dark
    // defaults are purple. secondaryContainer is what a selected FilterChip
    // fills itself with, and there are nine of them -- every day, hour,
    // passenger-count and language chip in the product turned lilac after
    // dark. outlineVariant is the border of every card in both apps.
    secondaryContainer = VelroColors.DarkAmberContainer,
    onSecondaryContainer = VelroColors.Amber200,
    error = VelroColors.Red500,
    onError = VelroColors.White,
    errorContainer = VelroColors.DarkRedContainer,
    onErrorContainer = VelroColors.Red200,
    // Same relationship after dark, where a shadow is invisible and lightness
    // is the only thing that can lift a card off its page.
    background = VelroColors.DarkBackground,
    onBackground = VelroColors.DarkOnSurface,
    surface = VelroColors.DarkSurface,
    onSurface = VelroColors.DarkOnSurface,
    surfaceVariant = VelroColors.DarkSurfaceRaised,
    onSurfaceVariant = VelroColors.Neutral300,
    // Neutral700 was 1.70:1 on the dark surface -- the same invisible-border
    // problem as light mode, and worse at night with headlights behind you.
    outline = VelroColors.Neutral500,
    outlineVariant = VelroColors.DarkSurfaceRaised,
)

/**
 * Typography, built per script.
 *
 * Perso-Arabic sits differently on the line and needs more leading than Latin
 * at the same size. Setting one global ratio makes Dari look cramped or English
 * look airy; this sets it from the active locale instead.
 *
 * Bold weights are shipped, never synthesised: faking bold on Perso-Arabic
 * smears the joins.
 */
fun velroTypography(locale: Locale): Typography {
    val family = VelroFonts.familyFor(locale)
    val ratio =
        if (locale == Locale.ENGLISH) TypeScale.LATIN_LINE_RATIO
        else TypeScale.PERSO_ARABIC_LINE_RATIO

    fun style(size: androidx.compose.ui.unit.TextUnit, weight: FontWeight) = TextStyle(
        fontFamily = family,
        fontSize = size,
        fontWeight = weight,
        lineHeight = (size.value * ratio).sp,
        lineHeightStyle = LineHeightStyle(
            alignment = LineHeightStyle.Alignment.Center,
            trim = LineHeightStyle.Trim.None,
        ),
    )

    // Every slot, not the seven that happened to be reached for first.
    //
    // Material fills an unset slot with its own default: FontFamily.Default
    // and a Latin line height. That is not a neutral fallback here -- it is
    // the system font instead of the bundled Vazirmatn, and 1.35 leading
    // instead of the 1.60 Perso-Arabic needs. Five slots were never defined
    // and were in use 31 times: every fare figure in the product
    // (headlineSmall), the driver's balance (headlineMedium), and six lines of
    // the emergency help sheet. A Pashto driver reading 119 at night was
    // reading it in whatever face the handset happened to substitute, with the
    // descenders of ټ ډ ړ ږ ښ ګ ڼ clipped by Latin leading.
    //
    // TypographyCoverageTest fails if a slot is ever left to Material again.
    return Typography(
        displayLarge = style(TypeScale.displaySize, FontWeight.Bold),
        displayMedium = style(TypeScale.displaySize, FontWeight.SemiBold),
        displaySmall = style(TypeScale.displaySize, FontWeight.SemiBold),
        headlineLarge = style(TypeScale.headlineSize, FontWeight.Bold),
        headlineMedium = style(TypeScale.headlineSize, FontWeight.SemiBold),
        headlineSmall = style(TypeScale.subheadlineSize, FontWeight.SemiBold),
        titleLarge = style(TypeScale.titleSize, FontWeight.SemiBold),
        titleMedium = style(TypeScale.headingSize, FontWeight.Medium),
        titleSmall = style(TypeScale.labelSize, FontWeight.Medium),
        bodyLarge = style(TypeScale.bodySize, FontWeight.Normal),
        bodyMedium = style(TypeScale.labelSize, FontWeight.Normal),
        bodySmall = style(TypeScale.captionSize, FontWeight.Normal),
        labelLarge = style(TypeScale.labelSize, FontWeight.Medium),
        labelMedium = style(TypeScale.captionSize, FontWeight.Medium),
        labelSmall = style(TypeScale.captionSize, FontWeight.Normal),
    )
}

/**
 * Fonts.
 *
 * Perso-Arabic is bundled rather than left to the system font. Android's
 * Arabic face varies by manufacturer, and several inexpensive handsets common
 * in this market ship one covering Persian and Arabic but not Pashto -- so
 * `ټ ډ ړ ږ ښ ګ ڼ ې ۍ`, exactly the letters that tell one word from another,
 * render as empty boxes. The failure is invisible on a developer's phone.
 *
 * Real weights, never synthesised: faking bold on Perso-Arabic smears the joins
 * where letters connect.
 *
 * Vazirmatn, SIL Open Font License 1.1. Chosen over Noto Naskh because it is
 * drawn for screens rather than for books -- sturdier strokes and more open
 * counters, which survive a cheap phone in daylight -- and because it is the
 * face most Persian and Dari interfaces already use, so it reads as ordinary
 * rather than foreign. Verified to keep all nine Pashto letters at every
 * weight. The licence ships in `assets/licences/` as it requires.
 *
 * Latin stays on the system sans: it is well covered everywhere, and bundling a
 * second family would cost another megabyte for no legibility gained.
 */
object VelroFonts {
    private val persoArabic = FontFamily(
        Font(R.font.vazirmatn_regular, FontWeight.Normal),
        Font(R.font.vazirmatn_medium, FontWeight.Medium),
        Font(R.font.vazirmatn_medium, FontWeight.SemiBold),
        Font(R.font.vazirmatn_bold, FontWeight.Bold),
    )

    fun familyFor(locale: Locale): FontFamily =
        if (locale == Locale.ENGLISH) FontFamily.SansSerif else persoArabic
}

@Composable
fun VelroTheme(
    strings: Strings,
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val locale = strings.locale
    // Direction is driven by the active locale, not by the device setting: a
    // Dari speaker on an English handset must still get an RTL layout.
    val direction = if (locale.isRtl) LayoutDirection.Rtl else LayoutDirection.Ltr

    CompositionLocalProvider(
        LocalLayoutDirection provides direction,
        LocalVelroStrings provides strings,
        LocalVelroLocale provides locale,
        LocalVelroDarkTheme provides darkTheme,
    ) {
        MaterialTheme(
            colorScheme = if (darkTheme) DarkScheme else LightScheme,
            typography = velroTypography(locale),
            content = content,
        )
    }
}
