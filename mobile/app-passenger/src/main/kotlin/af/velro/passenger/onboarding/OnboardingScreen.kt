package af.velro.passenger.onboarding

import af.velro.core.ui.component.ChoiceChip
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SideCar
import af.velro.core.ui.component.glassFill
import af.velro.core.ui.component.glassRim
import af.velro.core.ui.component.glassShadow
import af.velro.core.ui.theme.LocalAnimationsEnabled
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import af.velro.domain.Locale
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Payments
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.VerifiedUser
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

/**
 * Three pages before the first sign-in: what VELRO is, in the order a
 * passenger meets it -- she names the fare, drivers answer and she chooses,
 * and the ride is watched over.
 *
 * Shown once per handset, never again (see OnboardingStore). Skippable from
 * the first page, because somebody who was shown the app by a neighbour knows
 * all three already and should not have to tap through them.
 *
 * Each page is a sentence, not a feature list: a large green headline, one
 * line under it, and a picture. The pictures are drawn rather than shipped --
 * a car, its shadow, and one small thing floating beside it -- so the pages
 * cost nothing to download and nothing in the APK, and say nothing a real
 * screen later contradicts: no fare is shown, because VELRO does not suggest
 * one, and no driver has a name.
 *
 * Language is on the first row, because these are the first words the app
 * says and a Pashto or English reader handed a phone in Dari should not have
 * to guess their way to the sign-in screen to change it.
 */
@Composable
fun OnboardingScreen(
    locale: Locale,
    onLocaleChanged: (Locale) -> Unit,
    onDone: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    val animate = LocalAnimationsEnabled.current
    val pages = PAGES
    val pager = rememberPagerState { pages.size }
    val scope = rememberCoroutineScope()
    val last = pager.currentPage == pages.lastIndex

    fun go(page: Int) {
        scope.launch {
            // With animation off the page simply changes; the car on the track
            // jumps with it rather than driving.
            if (animate) pager.animateScrollToPage(page) else pager.scrollToPage(page)
        }
    }

    // The system back steps back through the pages before it leaves the app,
    // the same as the chevron beside the track.
    BackHandler(enabled = pager.currentPage > 0) { go(pager.currentPage - 1) }

    // A Surface for the theme's foreground as well as its ground: uncoloured
    // text otherwise falls back to black, which vanishes after dark.
    Surface(
        modifier = modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
        contentColor = MaterialTheme.colorScheme.onBackground,
    ) {
        Column(
            Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .navigationBarsPadding(),
        ) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = Spacing.gutter, vertical = Spacing.sm),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(
                    Modifier.weight(1f),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.xs),
                ) {
                    for (option in listOf(Locale.DARI, Locale.PASHTO, Locale.ENGLISH)) {
                        ChoiceChip(
                            selected = option == locale,
                            onClick = { onLocaleChanged(option) },
                            label = option.displayName(),
                        )
                    }
                }
                // Not on the last page, where "Get started" already is the way
                // out and a second one beside it would ask which to press.
                TextButton(
                    onClick = onDone,
                    enabled = !last,
                    modifier = Modifier
                        .alpha(if (last) 0f else 1f)
                        .height(Sizing.touchTarget),
                ) {
                    Text(
                        strings["common.action.skip"],
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }

            HorizontalPager(
                state = pager,
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
            ) { index ->
                Page(pages[index])
            }

            Column(Modifier.padding(horizontal = Spacing.gutter)) {
                ProgressTrack(
                    count = pages.size,
                    position = { pager.currentPage + pager.currentPageOffsetFraction },
                    current = pager.currentPage,
                    onBack = { go(pager.currentPage - 1) },
                )
                Spacer(Modifier.height(Spacing.lg))
                PrimaryAction(
                    label = if (last) strings["common.action.get_started"]
                    else strings["common.action.next"],
                    onClick = { if (last) onDone() else go(pager.currentPage + 1) },
                )
                Spacer(Modifier.height(Spacing.xl))
            }
        }
    }
}

/** The three pages, in the order a passenger meets what they describe. */
private enum class Hero { FARE, OFFERS, SAFE }

private val PAGES = Hero.entries.toList()

@Composable
private fun Page(hero: Hero) {
    val strings = LocalVelroStrings.current
    // Literal keys, so the localisation guard -- which reads source for the
    // keys the apps ask for -- can see every one of them.
    val title = when (hero) {
        Hero.FARE -> strings["onboarding.fare.title"]
        Hero.OFFERS -> strings["onboarding.offers.title"]
        Hero.SAFE -> strings["onboarding.safe.title"]
    }
    val body = when (hero) {
        Hero.FARE -> strings["onboarding.fare.body"]
        Hero.OFFERS -> strings["onboarding.offers.body"]
        Hero.SAFE -> strings["onboarding.safe.body"]
    }
    Column(
        Modifier
            .fillMaxSize()
            .padding(horizontal = Spacing.gutter),
    ) {
        Spacer(Modifier.height(Spacing.xl))
        Text(
            title,
            style = MaterialTheme.typography.displayLarge,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
        )
        Spacer(Modifier.height(Spacing.md))
        Text(
            body,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Box(
            Modifier
                .weight(1f)
                .fillMaxWidth(),
            contentAlignment = Alignment.Center,
        ) {
            HeroPicture(hero)
        }
    }
}

/**
 * The car, and the one thing floating beside it that is the page's point.
 *
 * The floating piece sits up and toward the end edge, over the bonnet, so it
 * reads as something the car is moving toward.
 */
@Composable
private fun HeroPicture(hero: Hero) {
    Box(
        Modifier
            .fillMaxWidth()
            .aspectRatio(1.25f),
    ) {
        SideCar(
            Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth(0.92f)
                .aspectRatio(2f)
                .padding(bottom = Spacing.lg),
        )
        Box(
            Modifier
                .align(Alignment.TopEnd)
                .padding(top = Spacing.lg),
        ) {
            when (hero) {
                Hero.FARE -> FareBubble()
                Hero.OFFERS -> OfferStack()
                Hero.SAFE -> CodeChip()
            }
        }
    }
}

/** A glass chip, the shape all three floating pieces share. */
@Composable
private fun FloatingChip(
    modifier: Modifier = Modifier,
    /** Null for a pill. */
    corner: Dp? = null,
    content: @Composable () -> Unit,
) {
    val shape = RoundedCornerShape(corner ?: Radius.pill)
    Surface(
        shape = shape,
        color = glassFill(),
        contentColor = MaterialTheme.colorScheme.onSurface,
        border = glassRim(),
        modifier = modifier.glassShadow(corner),
    ) { content() }
}

/** "How much will you pay?" -- the question the passenger answers, not a price. */
@Composable
private fun FareBubble() {
    val strings = LocalVelroStrings.current
    FloatingChip {
        Row(
            Modifier.padding(horizontal = Spacing.lg, vertical = Spacing.md),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Filled.Payments,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(Sizing.iconMd),
            )
            Spacer(Modifier.width(Spacing.sm))
            Text(
                strings["ride.ask.title"],
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

/**
 * Two answers, stacked: a face, a line, the stars. No names and no prices --
 * the picture of choosing, not a choice anybody could mistake for real.
 */
@Composable
private fun OfferStack() {
    Box(Modifier.width(196.dp).height(132.dp)) {
        MiniOffer(Modifier.align(Alignment.TopStart), stars = 4, highlighted = false)
        MiniOffer(
            Modifier
                .align(Alignment.BottomEnd),
            stars = 5,
            highlighted = true,
        )
    }
}

@Composable
private fun MiniOffer(modifier: Modifier, stars: Int, highlighted: Boolean) {
    val shape = RoundedCornerShape(Radius.lg)
    FloatingChip(
        modifier = modifier
            .width(176.dp)
            .then(
                if (highlighted) Modifier.border(2.dp, MaterialTheme.colorScheme.primary, shape)
                else Modifier,
            ),
        corner = Radius.lg,
    ) {
        Row(
            Modifier.padding(Spacing.md),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                Modifier
                    .size(36.dp)
                    .background(MaterialTheme.colorScheme.primaryContainer, CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    Icons.Filled.Person,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(Sizing.iconSm + 2.dp),
                )
            }
            Spacer(Modifier.width(Spacing.sm))
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                Box(
                    Modifier
                        .width(72.dp)
                        .height(8.dp)
                        .background(MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(Radius.pill)),
                )
                Row {
                    repeat(5) { i ->
                        Icon(
                            Icons.Filled.Star,
                            contentDescription = null,
                            tint = if (i < stars) MaterialTheme.colorScheme.secondary
                            else MaterialTheme.colorScheme.outlineVariant,
                            modifier = Modifier.size(14.dp),
                        )
                    }
                }
            }
        }
    }
}

/** The boarding code, as a shield and four dots -- never real digits. */
@Composable
private fun CodeChip() {
    val strings = LocalVelroStrings.current
    FloatingChip {
        Row(
            Modifier.padding(horizontal = Spacing.lg, vertical = Spacing.md),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Filled.VerifiedUser,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(Sizing.iconMd),
            )
            Spacer(Modifier.width(Spacing.sm))
            Column {
                Text(
                    strings["booking.label.code"],
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(top = Spacing.xs)) {
                    repeat(4) {
                        Box(
                            Modifier
                                .size(10.dp)
                                .background(MaterialTheme.colorScheme.primary, CircleShape),
                        )
                    }
                }
            }
        }
    }
}

/**
 * Where you are in the three pages: a thin line, a dot per page, and the car
 * driving along it to the page you are on.
 *
 * The car follows the pager's own position, fractions included, so a slow
 * swipe moves it by the same amount the page has moved -- the track is the
 * swipe, drawn. Offsets are layout-aware, so in Dari and Pashto the line runs
 * from the right and the car drives left, the same way the pages turn.
 *
 * The back chevron sits at the start of the line and is absent on the first
 * page, with its space kept so the line does not shift when it appears.
 */
@Composable
private fun ProgressTrack(
    count: Int,
    position: () -> Float,
    current: Int,
    onBack: () -> Unit,
) {
    val strings = LocalVelroStrings.current
    Row(
        Modifier
            .fillMaxWidth()
            .height(Sizing.touchTarget),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(Sizing.touchTarget), contentAlignment = Alignment.Center) {
            if (current > 0) {
                IconButton(onClick = onBack, modifier = Modifier.size(Sizing.touchTarget)) {
                    Icon(
                        Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = strings["common.action.back"],
                        tint = MaterialTheme.colorScheme.onSurface,
                    )
                }
            }
        }
        Spacer(Modifier.width(Spacing.sm))
        BoxWithConstraints(
            Modifier
                .weight(1f)
                .fillMaxHeight()
                .semantics {
                    contentDescription = strings[
                        "common.state.step",
                        "current" to current + 1,
                        "total" to count,
                    ]
                },
        ) {
            val inset = CAR_WIDTH / 2
            val span: Dp = maxWidth - CAR_WIDTH
            val progress by remember(count) {
                derivedStateOf { (position() / (count - 1)).coerceIn(0f, 1f) }
            }
            val line = MaterialTheme.colorScheme.outlineVariant
            val reached = MaterialTheme.colorScheme.primary

            // The road ahead, then the road already driven over it.
            Box(
                Modifier
                    .align(Alignment.CenterStart)
                    .padding(start = inset, end = inset)
                    .fillMaxWidth()
                    .height(2.dp)
                    .background(line, RoundedCornerShape(Radius.pill)),
            )
            Box(
                Modifier
                    .align(Alignment.CenterStart)
                    .padding(start = inset)
                    .width(span * progress)
                    .height(2.dp)
                    .background(reached, RoundedCornerShape(Radius.pill)),
            )
            for (i in 0 until count) {
                val at = span * (i / (count - 1).toFloat())
                Box(
                    Modifier
                        .align(Alignment.CenterStart)
                        .offset(x = inset + at - DOT / 2)
                        .size(DOT)
                        .background(
                            if (i <= current) reached else line,
                            CircleShape,
                        ),
                )
            }
            // The car, its wheels on the line.
            SideCar(
                Modifier
                    .align(Alignment.CenterStart)
                    .offset {
                        IntOffset(
                            x = (span * progress).roundToPx(),
                            y = (-CAR_HEIGHT / 2 + 2.dp).roundToPx(),
                        )
                    }
                    .size(width = CAR_WIDTH, height = CAR_HEIGHT),
                shadow = false,
            )
        }
    }
}

private val CAR_WIDTH = 40.dp
private val CAR_HEIGHT = 20.dp
private val DOT = 8.dp

/** Hardcoded, like the sign-in picker: each reads the same in every locale. */
private fun Locale.displayName(): String = when (this) {
    Locale.DARI -> "دری"
    Locale.PASHTO -> "پښتو"
    Locale.ENGLISH -> "English"
}
