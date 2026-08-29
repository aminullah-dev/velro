package af.velro.domain

/**
 * Matching place names the way people type them.
 *
 * Mirrors the server's `domain/text.py`. The same village is written with an
 * Arabic yeh or a Persian one, with or without a zero-width non-joiner, with
 * heh or teh marbuta -- and a passenger looking for their own village should
 * not have to guess which spelling was entered by whoever compiled the list.
 *
 * Pashto's own letters are deliberately left alone: ټ ډ ړ ږ ښ ګ ڼ ې ۍ
 * distinguish real words, and folding them into their Persian lookalikes would
 * merge places that are not the same.
 */
object PlaceNames {

    private val folded = mapOf(
        'ي' to 'ی', 'ﻯ' to 'ی', 'ﻰ' to 'ی',   // Arabic yeh forms
        'ك' to 'ک',                             // Arabic kaf
        'ة' to 'ه',                             // teh marbuta
        'أ' to 'ا', 'إ' to 'ا', 'آ' to 'ا',     // alef with hamza
        'ؤ' to 'و',
    )

    /** Zero-width joiners, tatweel, and the harakat that are rarely typed. */
    private val dropped = setOf(
        '‌', '‍', '‎', '‏', 'ـ',
        'ً', 'ٌ', 'ٍ', 'َ', 'ُ',
        'ِ', 'ّ', 'ْ', 'ٔ', 'ٰ',
    )

    private val easternDigits = mapOf(
        '۰' to '0', '۱' to '1', '۲' to '2', '۳' to '3', '۴' to '4',
        '۵' to '5', '۶' to '6', '۷' to '7', '۸' to '8', '۹' to '9',
        '٠' to '0', '١' to '1', '٢' to '2', '٣' to '3', '٤' to '4',
        '٥' to '5', '٦' to '6', '٧' to '7', '٨' to '8', '٩' to '9',
    )

    /** The form two names are compared in. Never stored, never displayed. */
    fun comparisonKey(text: String): String = buildString(text.length) {
        for (ch in text.lowercase()) {
            when {
                ch in dropped -> Unit
                ch.isWhitespace() -> Unit
                else -> append(easternDigits[ch] ?: folded[ch] ?: ch)
            }
        }
    }

    /** Whether a name should appear for what the passenger has typed so far. */
    fun matches(name: String, query: String): Boolean {
        val key = comparisonKey(query)
        return key.isEmpty() || comparisonKey(name).contains(key)
    }
}
