package af.velro.data.api

import af.velro.data.BuildConfig
import java.net.URI

/**
 * Pages the backend serves to a browser, beside the API rather than inside it.
 *
 * Derived from the base URL this build already carries, so a debug build
 * pointed at a laptop opens the laptop's copy of the page and a release opens
 * production's -- the text a person reads is always the text of the server
 * holding their data, never a hardcoded address that disagrees with it.
 */
object PublicPages {

    /** What VELRO keeps about a person, and for how long. */
    val privacyPolicyUrl: String = privacyPolicyUrl(BuildConfig.API_BASE_URL)

    /**
     * Scheme, host and port of the API, and `/privacy` at the root of it.
     *
     * The backend serves the page at its root, not under `/api/v1/`, so this
     * resolves a root-relative path rather than appending to the base. Pure,
     * so a test can hold the seam still -- the same seam ReleaseUrlTest holds
     * for the update link.
     */
    fun privacyPolicyUrl(apiBase: String): String =
        URI(apiBase).resolve("/privacy").toString()
}
