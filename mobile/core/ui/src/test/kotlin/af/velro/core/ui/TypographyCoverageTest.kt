package af.velro.core.ui

import af.velro.core.ui.theme.TypeScale
import af.velro.core.ui.theme.velroTypography
import af.velro.domain.Locale
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Every slot in the type scale, built by us.
 *
 * Material fills any slot the theme leaves unset with its own default, and
 * that default is not neutral here: FontFamily.Default is the handset's font
 * rather than the bundled Vazirmatn, and Material's leading is Latin leading
 * rather than the 1.60 Perso-Arabic script needs.
 *
 * Seven of the fifteen slots were defined. The other eight were reachable, and
 * five of them were in use 31 times -- every fare in the product drew at
 * `headlineSmall`, the driver's balance at `headlineMedium`, and six lines of
 * the emergency help sheet at `headlineSmall`/`bodySmall`. None of it was
 * visibly broken on a Latin test device, which is exactly why nobody caught it.
 *
 * This test does not care what the sizes are. It cares that no slot is left to
 * Material, because the next person to reach for `titleSmall` should get the
 * product's font without having to know this happened.
 */
class TypographyCoverageTest {

    private fun slots(locale: Locale): Map<String, TextStyle> {
        val t = velroTypography(locale)
        return mapOf(
            "displayLarge" to t.displayLarge,
            "displayMedium" to t.displayMedium,
            "displaySmall" to t.displaySmall,
            "headlineLarge" to t.headlineLarge,
            "headlineMedium" to t.headlineMedium,
            "headlineSmall" to t.headlineSmall,
            "titleLarge" to t.titleLarge,
            "titleMedium" to t.titleMedium,
            "titleSmall" to t.titleSmall,
            "bodyLarge" to t.bodyLarge,
            "bodyMedium" to t.bodyMedium,
            "bodySmall" to t.bodySmall,
            "labelLarge" to t.labelLarge,
            "labelMedium" to t.labelMedium,
            "labelSmall" to t.labelSmall,
        )
    }

    @Test
    fun `every slot carries a font family we chose`() {
        for (locale in Locale.entries) {
            for ((name, style) in slots(locale)) {
                assertNotNull("$name has no family in $locale", style.fontFamily)
                assertTrue(
                    "$name in $locale falls back to the system font",
                    style.fontFamily != FontFamily.Default,
                )
            }
        }
    }

    @Test
    fun `every slot carries the line height its script needs`() {
        for (locale in Locale.entries) {
            val ratio =
                if (locale == Locale.ENGLISH) TypeScale.LATIN_LINE_RATIO
                else TypeScale.PERSO_ARABIC_LINE_RATIO
            for ((name, style) in slots(locale)) {
                val expected = style.fontSize.value * ratio
                assertEquals(
                    "$name in $locale does not use the $ratio leading for its script",
                    expected.toDouble(),
                    style.lineHeight.value.toDouble(),
                    0.01,
                )
            }
        }
    }

    @Test
    fun `Perso-Arabic is given more leading than Latin at the same size`() {
        // The reason the ratio is per-script at all. If these ever converge,
        // one of the two languages is being set with the other's leading.
        val dari = velroTypography(Locale.DARI).bodyLarge
        val english = velroTypography(Locale.ENGLISH).bodyLarge
        assertEquals(dari.fontSize.value, english.fontSize.value, 0.01f)
        assertTrue(
            "Dari body text must breathe more than English at the same size",
            dari.lineHeight.value > english.lineHeight.value,
        )
    }
}
