package af.velro.core.ui

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The bundled face must cover Pashto.
 *
 * Android's Arabic font varies by manufacturer and several handsets common in
 * this market drop exactly these letters, so the family is bundled -- but a
 * bundled font is only worth its megabyte if it actually has the glyphs. This
 * reads the real files: a substituted or truncated font fails here rather than
 * on a driver's phone in Ghorband, where nobody would report it.
 */
class FontCoverageTest {

    private val pashtoOnly = "ټډړږښګڼېۍ"
    private val persian = "پچژگک"
    private val easternDigits = "۰۱۲۳۴۵۶۷۸۹"

    /**
     * Plates, booking numbers and trip numbers are Latin.
     *
     * A Perso-Arabic face without them is not a smaller problem than one
     * without Pashto: every plate and every booking number would fall back to
     * whatever the handset happens to have, and the receipt would be set in two
     * typefaces at once.
     */
    private val latin = "ABCPRWKGVLSTNabc0123456789-"

    @Test
    fun `every bundled weight covers Pashto Persian and Eastern digits`() {
        val fonts = File("src/main/res/font").listFiles { f -> f.extension == "ttf" }
        assertTrue("no bundled fonts found -- see docs/adr/0002-fonts.md", !fonts.isNullOrEmpty())

        for (file in fonts!!) {
            val covered = codepointsIn(file)
            for (text in listOf(pashtoOnly, persian, easternDigits, latin)) {
                val missing = text.filterNot { covered.contains(it.code) }
                assertTrue("${file.name} is missing: $missing", missing.isEmpty())
            }
        }
    }

    @Test
    fun `the weights are real files, not one face relabelled`() {
        val dir = File("src/main/res/font")
        val regular = File(dir, "vazirmatn_regular.ttf")
        val bold = File(dir, "vazirmatn_bold.ttf")
        assertTrue("regular missing", regular.exists())
        assertTrue("bold missing", bold.exists())
        // Synthesised bold smears the joins in Naskh, so the two must differ.
        assertTrue(
            "bold is byte-identical to regular -- the weight was not shipped",
            !regular.readBytes().contentEquals(bold.readBytes()),
        )
    }

    @Test
    fun `the open font licence ships with the app`() {
        val licence = File("src/main/assets/licences/vazirmatn-OFL.txt")
        assertTrue("OFL 1.1 requires the notice to ship", licence.exists())
        assertTrue(licence.readText().contains("SIL OPEN FONT LICENSE"))
    }

    /** Minimal cmap reader: formats 4 and 12 are all a TTF needs here. */
    private fun codepointsIn(file: File): Set<Int> {
        val d = file.readBytes()
        fun u8(i: Int) = d[i].toInt() and 0xFF
        fun u16(i: Int) = (u8(i) shl 8) or u8(i + 1)
        fun u32(i: Int) = (u16(i) shl 16) or u16(i + 2)

        var cmap = -1
        for (i in 0 until u16(4)) {
            val off = 12 + i * 16
            if (String(d, off, 4, Charsets.ISO_8859_1) == "cmap") cmap = u32(off + 8)
        }
        require(cmap >= 0) { "${file.name} has no cmap table" }

        val out = mutableSetOf<Int>()
        for (i in 0 until u16(cmap + 2)) {
            val rec = cmap + 4 + i * 8
            val sub = cmap + u32(rec + 4)
            when (u16(sub)) {
                4 -> {
                    val segX2 = u16(sub + 6)
                    val ends = sub + 14
                    val starts = ends + segX2 + 2
                    for (s in 0 until segX2 / 2) {
                        for (c in u16(starts + s * 2)..u16(ends + s * 2)) out.add(c)
                    }
                }
                12 -> {
                    for (g in 0 until u32(sub + 12)) {
                        val grp = sub + 16 + g * 12
                        val start = u32(grp)
                        val end = u32(grp + 4)
                        if (end - start in 0..5000) for (c in start..end) out.add(c)
                    }
                }
            }
        }
        return out
    }
}
