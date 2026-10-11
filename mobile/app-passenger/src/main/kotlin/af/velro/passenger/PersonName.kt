package af.velro.passenger

/**
 * A passenger's name as two required parts, stored as one.
 *
 * The owner's rule (2026-10-10): a first name and a last name, both, before a
 * passenger reaches home -- a driver arriving at a station asks for somebody
 * by name, and "Ahmad" alone is half the men waiting there. The server keeps
 * a single `full_name`, so the app joins the two with one space to save and
 * splits on the first space to edit: first word the first name, the rest the
 * last name, which is how a two-word Dari name with a multi-word family name
 * reads back.
 *
 * Pure, so the rules are tested without a screen.
 */
object PersonName {

    /** Two characters: a single letter is an initial, not a name. */
    const val MIN_PART = 2

    fun isValidPart(part: String): Boolean = part.trim().length >= MIN_PART

    fun isValid(first: String, last: String): Boolean = isValidPart(first) && isValidPart(last)

    /**
     * Whether a stored name already has both parts: two words at least. An
     * older account saved as "Ahmad" alone is asked for the rest, as on iOS.
     */
    fun isFullName(full: String?): Boolean = split(full).let { (first, last) -> first.isNotEmpty() && last.isNotEmpty() }

    /**
     * What is saved: both parts trimmed, inner runs of spaces collapsed, one
     * space between them.
     */
    fun join(first: String, last: String): String =
        listOf(first, last).joinToString(" ") { it.trim().replace(SPACES, " ") }

    /** First word, and everything after it. A missing name is two blanks. */
    fun split(full: String?): Pair<String, String> {
        val words = full?.trim()?.split(SPACES)?.filter { it.isNotEmpty() }.orEmpty()
        return (words.firstOrNull() ?: "") to words.drop(1).joinToString(" ")
    }

    private val SPACES = Regex("\\s+")
}
