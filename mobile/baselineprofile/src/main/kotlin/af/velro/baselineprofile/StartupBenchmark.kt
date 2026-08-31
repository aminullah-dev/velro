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
 * MEASURED, on a Samsung SM-A226B (Galaxy A22 5G, Dimensity 700, Android 13) --
 * a budget MediaTek handset of the class this product is built for:
 *
 *     without profile   median 439.9 ms   (387 - 522)
 *     with profile      median 433.2 ms   (400 - 623)
 *
 * 6.7 ms, or 1.5%. The ranges overlap almost entirely, so the honest reading is
 * that the profile is not measurably helping this app on this device. The 20-30%
 * figure quoted for baseline profiles is not what VELRO gets, and it should not
 * be repeated in anything describing this product.
 *
 * That is a fact about where this app's startup time goes, not a fault in the
 * profile. 440 ms of cold start on a phone like this is dominated by process
 * setup, resource loading and reading the locale JSON off disk -- work that
 * ahead-of-time compilation does not touch. Interpretation of app methods, the
 * only thing a profile removes, is evidently a small share of it.
 *
 * Two things worth knowing before acting on this. Clocks were not locked (the
 * run suppresses UNLOCKED, because the device is not rooted), which widens the
 * noise band and is most of why the maxima disagree. And the profile itself was
 * recorded on an emulator; regenerating it on a device of this class would
 * target it better and is the first thing to try if this is worth chasing.
 *
 * The profile costs about 6.6 KB in the APK, so it stays: it is not earning its
 * headline, but it is not costing anything either, and older or slower devices
 * than this one may still see more.
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
