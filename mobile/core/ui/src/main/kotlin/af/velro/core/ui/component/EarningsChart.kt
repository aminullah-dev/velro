package af.velro.core.ui.component

import af.velro.core.i18n.MoneyFormatter
import af.velro.core.i18n.Numerals
import af.velro.core.ui.theme.LocalAnimationsEnabled
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Motion
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Spacing
import af.velro.domain.EarningsBucket
import af.velro.domain.EarningsSummary
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

/**
 * A driver's take, one bar per day, week or month.
 *
 * Drawn with layout rather than pulled in as a charting library. The two
 * common ones add roughly a megabyte to the APK, and this is a market where
 * the download is metered and the handset is cheap -- the same reason the
 * sign-in screen draws its texture instead of shipping a photograph. A bar
 * chart is a Row of Boxes; it does not need a dependency.
 *
 * Net, not gross. A driver comparing Tuesday against Monday wants what he
 * keeps, and a gross bar that ignores commission is the number he will feel
 * cheated by when the balance does not match it.
 *
 * Bars are never invisible: a period with earnings gets at least a hairline,
 * so "a small day" and "a day I did not work" are distinguishable. A zero
 * bucket gets the track and nothing else.
 */
@Composable
fun EarningsChart(
    summary: EarningsSummary,
    labelFor: (EarningsBucket) -> String,
    modifier: Modifier = Modifier,
    height: androidx.compose.ui.unit.Dp = 140.dp,
) {
    val strings = LocalVelroStrings.current
    val peak = summary.peakNetMinor

    // The whole chart carries one description. Fourteen separately-labelled
    // bars is not something a screen reader user can hold in their head, and
    // TalkBack would read the axis before the point of it.
    val spoken = strings[
        "driver.earnings.chart_summary",
        "total" to MoneyFormatter.format(
            af.velro.domain.MoneyValue(summary.totalNetMinor), strings,
        ),
        "trips" to Numerals.localise(summary.totalTrips.toString(), strings.locale),
    ]

    Row(
        modifier
            .fillMaxWidth()
            .height(height)
            .semantics { contentDescription = spoken },
        horizontalArrangement = Arrangement.spacedBy(Spacing.xs),
        verticalAlignment = Alignment.Bottom,
    ) {
        for (bucket in summary.buckets) {
            Bar(
                bucket = bucket,
                peakMinor = peak,
                label = labelFor(bucket),
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun Bar(
    bucket: EarningsBucket,
    peakMinor: Long,
    label: String,
    modifier: Modifier = Modifier,
) {
    val animate = LocalAnimationsEnabled.current
    val target =
        if (peakMinor <= 0L) 0f
        // Negative nets are possible -- a cancellation fee on a day with no
        // fares -- and a bar cannot be shorter than nothing. The figure is
        // still in the row beneath; this is the shape of the good days.
        else (bucket.net.amountMinor.coerceAtLeast(0L).toFloat() / peakMinor.toFloat())

    val fraction by animateFloatAsState(
        targetValue = target,
        animationSpec =
            if (animate) tween(Motion.WITHIN_MS, easing = Motion.easing) else snap(),
        label = "bar-${bucket.startsOn}",
    )

    Column(
        modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Bottom,
    ) {
        // The track, so an empty period still occupies its share of the width
        // and the axis stays evenly spaced.
        Box(
            Modifier
                .weight(1f)
                .fillMaxWidth()
                .padding(horizontal = Spacing.xxs),
            contentAlignment = Alignment.BottomCenter,
        ) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .fillMaxHeight()
                    .background(
                        MaterialTheme.colorScheme.surfaceVariant,
                        RoundedCornerShape(Radius.sm),
                    ),
            )
            if (bucket.net.amountMinor > 0L) {
                Box(
                    Modifier
                        .fillMaxWidth()
                        // At least a sliver, so a thin day is still a day.
                        .fillMaxHeight(fraction.coerceIn(0.02f, 1f))
                        .background(
                            MaterialTheme.colorScheme.primary,
                            RoundedCornerShape(Radius.sm),
                        ),
                )
            }
        }

        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            maxLines = 1,
            modifier = Modifier.padding(top = Spacing.xs),
        )
    }
}