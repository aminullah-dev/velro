package af.velro.baselineprofile

import androidx.benchmark.macro.BaselineProfileMode
import androidx.benchmark.macro.CompilationMode
import androidx.benchmark.macro.StartupMode
import androidx.benchmark.macro.StartupTimingMetric
import androidx.benchmark.macro.junit4.MacrobenchmarkRule
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import org.junit.Rule
import org.junit.Test

/**
 * What the baseline profile is actually worth, on this handset.
 *
 * The profile was generated and verified inside the release APK, but nobody
 * measured it. The usual "20-30% faster cold start" is an industry figure, and
 * quoting it as though it were VELRO's would be inventing a number.
 *
 * Two runs of the same journey: one with the app compiled as a device with no
 * profile would have it, one with the profile applied. The difference between
 * them is the answer.
 *
 * RUN THIS ON A REAL HANDSET, and preferably a cheap one. A macrobenchmark on
 * an emulator measures a desktop CPU pretending to be a phone: the absolute
 * milliseconds are far below anything in this market, and the gap the profile
 * closes is exactly the gap a slow processor makes wide. An emulator number is
 * a proof that the benchmark runs, not a measurement of the product.
 *
 *   ./gradlew :baselineprofile:connectedBenchmarkAndroidTest
 *
 * Locked clocks matter on a physical device -- a phone that thermally throttles
 * halfway through gives a difference that is the CPU governor, not the profile.
 */
class StartupBenchmark {

    @get:Rule
    val rule = MacrobenchmarkRule()

    /**
     * The app as a device that never received a profile runs it.
     *
     * None(), not Partial(Disable): Partial refuses to be constructed with
     * nothing to pre-compile and no warmup, because it would have no portion
     * to compile. None() is the honest floor -- nothing compiled ahead of
     * time, everything interpreted on first execution, which is exactly the
     * state a baseline profile exists to improve on.
     */
    @Test
    fun startupWithoutProfile() = measure(CompilationMode.None())

    /** The app as Play installs it. */
    @Test
    fun startupWithProfile() = measure(
        CompilationMode.Partial(baselineProfileMode = BaselineProfileMode.Require),
    )

    private fun measure(mode: CompilationMode) = rule.measureRepeated(
        packageName = PACKAGE,
        metrics = listOf(StartupTimingMetric()),
        compilationMode = mode,
        // COLD only. Warm and hot starts skip the work a profile exists to
        // remove, so including them would average the effect away.
        startupMode = StartupMode.COLD,
        iterations = ITERATIONS,
        setupBlock = { pressHome() },
    ) {
        startActivityAndWait()
        // The same finish line the profile generator uses: the activity being
        // up is not the screen being drawn, and timing to the earlier point
        // would measure less than a person waits for.
        device.wait(Until.hasObject(By.text(DARI)), READY_TIMEOUT_MS)
    }

    private companion object {
        const val PACKAGE = "af.velro.passenger"

        /** Hardcoded in the app, so it reads the same in every locale. */
        const val DARI = "دری"

        /**
         * Enough for the median to settle without making a full run tedious.
         * The tail on a cheap phone is wide; the median is the honest figure.
         */
        const val ITERATIONS = 10

        const val READY_TIMEOUT_MS = 10_000L
    }
}
