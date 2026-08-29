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
 * OUTSTANDING: a Perso-Arabic family with complete Pashto coverage
 * (ټ ډ ړ ږ ښ ګ ڼ ې ۍ) must be dropped into `core/ui/src/main/res/font/` and
 * wired here. Until then this falls back to the system font, which varies by
 * manufacturer and is known to drop Pashto glyphs on several devices common in
 * this market -- so Pashto will render with tofu boxes on some handsets.
 * See `docs/adr/0002-fonts.md`.
 */
object VelroFonts {
    fun familyFor(locale: Locale): FontFamily =
        if (locale == Locale.ENGLISH) FontFamily.SansSerif else FontFamily.Default
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
