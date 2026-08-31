package af.velro.core.i18n

import android.content.Context
import af.velro.domain.Locale
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * Message keys, resolved at runtime from the same JSON the backend uses.
 *
 * Android string resources would be the ordinary choice. These are not, on
 * purpose: the server sends a `message_key` with every error, and the admin
 * panel resolves the same keys. One file set for three surfaces means a key
 * added on the server cannot be missing on the phone, and a sentence is never
 * written twice.
 *
 * No user-visible literal appears anywhere else in this codebase.
 */
class Strings private constructor(
    private val translations: Map<String, String>,
    private val fallback: Map<String, String>,
    val locale: Locale,
) {

    /**
     * Resolve a key, substituting `{named}` placeholders.
     *
     * An unknown key returns the key itself rather than an empty string: a
     * screen showing `booking.label.seat` is an obvious bug report, whereas a
     * blank space is a mystery.
     */
    operator fun get(key: String, params: Map<String, Any?> = emptyMap()): String {
        val template = translations[key] ?: fallback[key] ?: return key
        if (params.isEmpty()) return template
        val resolved = withMoney(params)
        return PLACEHOLDER.replace(template) { match ->
            val name = match.groupValues[1]
            resolved[name]?.let { format(it) } ?: match.value
        }
    }

    /**
     * Minor units in, money out.
     *
     * The server's error contexts and notification payloads carry amounts the
     * only way a machine should: `<name>_minor` plus a `currency`, locale-free
     * and exact. Three sentences spliced those raw integers straight into
     * prose -- "You need at least 5000 to request a payout" for a fifty-afghani
     * minimum, and no currency anywhere -- because substitution has no idea
     * what a number means.
     *
     * So the pairs are rendered here, in the locale actually being read, and
     * both `{amount}` and `{<name>}` become real money. A sentence that
     * genuinely wants the integer can still ask for `{<name>_minor}`.
     */
    private fun withMoney(params: Map<String, Any?>): Map<String, Any?> {
        val currency = params["currency"] as? String ?: return params
        val minors = params.keys.filter { it.endsWith(MINOR_SUFFIX) }
        if (minors.isEmpty()) return params
        val out = params.toMutableMap()
        for (key in minors) {
            val minor = (params[key] as? Number)?.toLong() ?: continue
            val money = MoneyFormatter.format(minor, currency, this)
            out[key.removeSuffix(MINOR_SUFFIX)] = money
            // The commonest shape: one amount in the sentence, called `amount`
            // whatever the context calls it.
            if (minors.size == 1) out.putIfAbsent("amount", money)
        }
        return out
    }

    operator fun get(key: String, vararg params: Pair<String, Any?>): String =
        get(key, params.toMap())

    fun has(key: String): Boolean = key in translations || key in fallback

    /**
     * The sentence for a server error code.
     *
     * The code is the contract; the wording is not. An unregistered code falls
     * back to a general message rather than showing the code to a passenger.
     */
    fun forErrorCode(code: String, context: Map<String, Any?> = emptyMap()): String {
        val key = "error." + code.lowercase()
        return if (has(key)) get(key, context) else get("error.internal_error")
    }

    private fun format(value: Any?): String = when (value) {
        null -> ""
        is Number -> Numerals.format(value, locale)
        else -> value.toString()
    }

    companion object {
        // Both braces escaped. An unescaped closing brace is accepted by the
        // JVM's regex engine and rejected by Android's ICU one, so the
        // difference only shows up on a device -- never in a JVM unit test.
        private const val MINOR_SUFFIX = "_minor"
        private val PLACEHOLDER = Regex("""\{(\w+)\}""")
        private val json = Json { ignoreUnknownKeys = true }

        /** English is the fallback because it is the only file guaranteed complete. */
        private const val FALLBACK_TAG = "en"

        /**
         * A Strings built from a literal map, for tests.
         *
         * The real one reads JSON out of the APK's assets, which needs a
         * Context and therefore an instrumented test. The substitution rules
         * -- money rendering, numerals, missing keys -- are pure, and should be
         * provable without a device.
         */
        @JvmStatic
        fun of(locale: Locale, translations: Map<String, String>): Strings =
            Strings(translations, translations, locale)

        fun load(context: Context, locale: Locale): Strings {
            val fallback = read(context, FALLBACK_TAG)
            val translations =
                if (locale.tag == FALLBACK_TAG) fallback else read(context, locale.tag)
            return Strings(translations, fallback, locale)
        }

        private fun read(context: Context, tag: String): Map<String, String> =
            runCatching {
                context.assets.open("locales/$tag.json").bufferedReader().use { reader ->
                    json.parseToJsonElement(reader.readText()).jsonObject
                        .mapValues { it.value.jsonPrimitive.content }
                }
            }.getOrDefault(emptyMap())
    }
}
