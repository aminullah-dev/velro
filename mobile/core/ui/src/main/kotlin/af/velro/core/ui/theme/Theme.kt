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
    background = VelroColors.White,
    onBackground = VelroColors.Neutral900,
    surface = VelroColors.White,
    onSurface = VelroColors.Neutral900,
    surfaceVariant = VelroColors.Neutral100,
    onSurfaceVariant = VelroColors.Neutral700,
    outline = VelroColors.Neutral300,
    outlineVariant = VelroColors.Neutral200,
)

private val DarkScheme = darkColorScheme(
    primary = VelroColors.Green200,
    onPrimary = VelroColors.Green900,
    primaryContainer = VelroColors.Green800,
    onPrimaryContainer = VelroColors.Green100,
    secondary = VelroColors.Amber500,
    onSecondary = VelroColors.Neutral900,
    error = VelroColors.Red500,
    onError = VelroColors.White,
    background = VelroColors.DarkSurface,
    onBackground = VelroColors.DarkOnSurface,
    surface = VelroColors.DarkSurface,
    onSurface = VelroColors.DarkOnSurface,
    surfaceVariant = VelroColors.DarkSurfaceRaised,
    onSurfaceVariant = VelroColors.Neutral300,
    outline = VelroColors.Neutral700,
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

    return Typography(
        displaySmall = style(TypeScale.displaySize, FontWeight.SemiBold),
        titleLarge = style(TypeScale.titleSize, FontWeight.SemiBold),
        titleMedium = style(TypeScale.headingSize, FontWeight.Medium),
        bodyLarge = style(TypeScale.bodySize, FontWeight.Normal),
        bodyMedium = style(TypeScale.labelSize, FontWeight.Normal),
        labelLarge = style(TypeScale.labelSize, FontWeight.Medium),
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
    ) {
        MaterialTheme(
            colorScheme = if (darkTheme) DarkScheme else LightScheme,
            typography = velroTypography(locale),
            content = content,
        )
    }
}
