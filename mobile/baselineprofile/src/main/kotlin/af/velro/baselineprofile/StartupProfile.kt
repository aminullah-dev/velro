package af.velro.baselineprofile

import androidx.benchmark.macro.junit4.BaselineProfileRule
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import org.junit.Rule
import org.junit.Test

/**
 * Records what a cold start actually runs.
 *
 * Android ships app code as DEX and compiles it as it goes. The first run of
 * any method is interpreted, so the first screen a person sees is the slowest
 * it will ever be -- and on the handsets this product is aimed at, that is the
 * difference between an app that feels finished and one that feels broken. A
 * baseline profile is a list of the classes and methods worth compiling ahead
 * of time; Play applies it at install, so the first launch is already warm.
 *
 * This is the only genuinely mechanical slowness in the product. Everything
 * else in the redesign was layout and motion, which are perception. This one
 * is measurable milliseconds.
 *
 * The profile is *recorded*, not written by hand: whatever this test touches
 * is what gets compiled. So the journey below has to be the real one -- launch
 * the app cold and sit on the first screen a signed-out passenger meets, which
 * is sign-in. Driving further would need a backend and a signed-in session,
 * which a build machine does not have; the screens behind the gate warm
 * themselves from the classes this run already covers (the theme, the fonts,
 * the string loader, Compose itself, Hilt's graph, Retrofit's setup).
 */
class StartupProfile {

    @get:Rule
    val rule = BaselineProfileRule()

    @Test
    fun coldStartToSignIn() = rule.collect(
        packageName = PACKAGE,
        // Several passes, and the tooling keeps what is stable across them.
        // One pass would bake in whatever the machine happened to do that
        // time -- a garbage collection, a slow disk read.
        maxIterations = 8,
        stableIterations = 3,
    ) {
        pressHome()
        startActivityAndWait()

        // Wait for something the app itself drew, not merely for the window.
        // startActivityAndWait returns when the activity is up, which on a
        // Compose screen is before the first frame of content -- a profile
        // recorded to that point would miss the composition it is meant to
        // speed up.
        //
        // The language chip, not the brand: `app.name` is localised ("ولرو" in
        // Dari and Pashto, "VELRO" in English) and the app opens in Dari by
        // default regardless of the handset, so matching on "VELRO" would wait
        // ten seconds for a string that is never drawn. The chip labels are
        // hardcoded in Locale.displayName() and are the same three words in
        // every locale.
        //
        // It is also the last thing the sign-in screen composes, and it needs
        // the bundled Perso-Arabic face resolved to lay out at all -- so
        // waiting on it puts font loading on the recorded path too.
        device.wait(Until.hasObject(By.text(DARI)), READY_TIMEOUT_MS)
    }

    private companion object {
        /**
         * The release-shaped id, without `.debug`.
         *
         * The generator installs its own non-minified build of the target; the
         * suffix the developer's debug build carries is not part of it, and
         * naming that variant here would profile an app the user never runs.
         */
        const val PACKAGE = "af.velro.passenger"

        /**
         * The Dari chip on the language row.
         *
         * Hardcoded in the app rather than translated, which is what makes it
         * safe to match on: it reads the same whichever locale the app or the
         * handset is in.
         */
        const val DARI = "دری"

        const val READY_TIMEOUT_MS = 10_000L
    }
}
