package af.velro.passenger

import af.velro.core.i18n.Calendars
import af.velro.core.ui.component.BookingRow
import af.velro.core.ui.component.DrawnMap
import af.velro.core.ui.component.EmptyState
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.GlassIconButton
import af.velro.core.ui.component.GlassPillButton
import af.velro.core.ui.component.IconRow
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.glassFill
import af.velro.core.ui.component.glassRim
import af.velro.core.ui.component.glassShadow
import af.velro.core.ui.component.softShadow
import af.velro.core.ui.theme.Elevation
import af.velro.core.ui.theme.Glass
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import af.velro.data.api.PublicPages
import af.velro.data.db.OperationKind
import af.velro.data.db.PendingOperationEntity
import af.velro.domain.RideRequest
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.Flag
import androidx.compose.material.icons.filled.Groups
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.PrivacyTip
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.launch

/**
 * Home, section 72.
 *
 * One action and a list of what the passenger already has. Nothing else: a home
 * screen that tries to show everything is the fastest way to make a first-time
 * user close the app.
 *
 * Laid out the way the ride apps a passenger may have seen are: a map behind
 * everything, a few round glass controls floating over it, and a sheet that
 * rides up from the bottom holding "Where to?" and her trips. The map is
 * drawn, not loaded (see DrawnMap) -- there are no cars on it, because VELRO
 * has no live cars to show at home and a picture of some would be a promise.
 *
 * Everything that is not the one action lives in the side drawer: her
 * account, her journeys, help, her reports, the privacy page.
 */
@Composable
internal fun HomeScreen(
    onBook: () -> Unit,
    onOpenBooking: (String) -> Unit,
    onOpenHistory: () -> Unit,
    onGetHelp: () -> Unit,
    onOpenAccount: () -> Unit,
    onOpenOffers: () -> Unit,
    onOpenReports: () -> Unit,
    @Suppress("UNUSED_PARAMETER") onSignOut: () -> Unit,
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val strings = LocalVelroStrings.current
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()

    // Back closes the drawer before it does anything else -- the drawer is a
    // layer over home, and a back that left the app from under it would take
    // the screen away along with the menu.
    BackHandler(enabled = drawer.isOpen) { scope.launch { drawer.close() } }

    // Fresh each time home comes back into view -- from a booking, from the
    // offers, from another app -- now that there is no pull to refresh. Not on
    // the first appearance: the view model has just loaded, and asking twice
    // in the same second is data a metered bundle pays for twice.
    val firstResume = remember { mutableStateOf(true) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        if (firstResume.value) firstResume.value = false else viewModel.refresh()
    }

    // The drawer slides away, then the row's door opens: a destination that
    // appeared while the menu was still on screen would arrive under it.
    val fromDrawer: (() -> Unit) -> Unit = { action ->
        scope.launch {
            drawer.close()
            action()
        }
    }

    ModalNavigationDrawer(
        drawerState = drawer,
        // Opened by the menu button only. An edge swipe on a screen that is
        // mostly map and sheet opens it by accident far more often than on
        // purpose; once open, a swipe closes it as expected.
        gesturesEnabled = drawer.isOpen,
        scrimColor = Color.Black.copy(alpha = SCRIM),
        drawerContent = {
            HomeDrawer(
                onClose = { scope.launch { drawer.close() } },
                onAccount = { fromDrawer(onOpenAccount) },
                onTrips = { fromDrawer(onOpenHistory) },
                onHelp = { fromDrawer(onGetHelp) },
                onReports = { fromDrawer(onOpenReports) },
                onPrivacy = {
                    fromDrawer {
                        // A handset with no browser is rare, not impossible,
                        // and a tap that throws takes the whole app down.
                        runCatching {
                            context.startActivity(
                                Intent(Intent.ACTION_VIEW, Uri.parse(PublicPages.privacyPolicyUrl))
                            )
                        }
                    }
                },
            )
        },
    ) {
        HomeBody(
            state = state,
            onBook = onBook,
            onOpenBooking = onOpenBooking,
            onOpenHistory = onOpenHistory,
            onGetHelp = onGetHelp,
            onOpenAccount = onOpenAccount,
            onOpenOffers = onOpenOffers,
            onOpenMenu = { scope.launch { drawer.open() } },
            onRefresh = viewModel::refresh,
            onDismissSyncFailure = viewModel::dismissSyncFailure,
        )
    }
}

/** Light enough that home is still there behind the menu, not blacked out. */
private const val SCRIM = 0.24f

/** The sheet's shadow reaches further than a button's: it is a bigger thing. */
private val SHEET_SPREAD = 20.dp

/**
 * How much of the screen the sheet holds, fixed.
 *
 * Enough for "Where to?", the recent-trips line and three trips at an ordinary
 * font size on a small phone, and the map keeps the rest. Fixed rather than
 * scrolled up over the map: the owner's word on the first build was that home
 * scrolled and must not -- a home screen is a place to stand, not a page to
 * move through.
 */
private const val SHEET_SHARE = 0.56f

/** At this width and above the panel stands beside the map instead of under it. */
private val WIDE = 700.dp

/** The side panel's width on a wide screen: a phone's width, not half a tablet. */
private val PANEL_WIDTH = 420.dp

/** Home shows this many trips; the rest, and the receipts, are behind History. */
private const val RECENT_LIMIT = 3

@Composable
private fun HomeBody(
    state: HomeUiState,
    onBook: () -> Unit,
    onOpenBooking: (String) -> Unit,
    onOpenHistory: () -> Unit,
    onGetHelp: () -> Unit,
    onOpenAccount: () -> Unit,
    onOpenOffers: () -> Unit,
    onOpenMenu: () -> Unit,
    onRefresh: () -> Unit,
    onDismissSyncFailure: (String) -> Unit,
) {
    val strings = LocalVelroStrings.current

    // A Surface, not a bare Box: it is what hands every Text below the
    // theme's foreground. Without one, text with no colour of its own falls
    // back to black -- invisible on the dark sheet after sunset.
    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
        contentColor = MaterialTheme.colorScheme.onSurface,
    ) {
        BoxWithConstraints(Modifier.fillMaxSize()) {
            // The map never moves: it is the ground, and nothing slides over
            // it.
            DrawnMap(Modifier.fillMaxSize())

            val wide = maxWidth >= WIDE
            if (wide) {
                // Beside the map, at the start edge, below the floating
                // controls: on a tablet a sheet the width of the screen would
                // be a wall of glass with three rows in it.
                val shape = RoundedCornerShape(Radius.sheet)
                HomeSheet(
                    state = state,
                    shape = shape,
                    onBook = onBook,
                    onOpenBooking = onOpenBooking,
                    onOpenHistory = onOpenHistory,
                    onOpenOffers = onOpenOffers,
                    onRefresh = onRefresh,
                    onDismissSyncFailure = onDismissSyncFailure,
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .statusBarsPadding()
                        .navigationBarsPadding()
                        .padding(
                            start = Spacing.lg,
                            end = Spacing.lg,
                            top = Sizing.touchTarget + Spacing.xl,
                            bottom = Spacing.lg,
                        )
                        .width(minOf(PANEL_WIDTH, maxWidth * 0.45f))
                        .fillMaxHeight(),
                )
            } else {
                HomeSheet(
                    state = state,
                    shape = RoundedCornerShape(topStart = Radius.sheet, topEnd = Radius.sheet),
                    onBook = onBook,
                    onOpenBooking = onOpenBooking,
                    onOpenHistory = onOpenHistory,
                    onOpenOffers = onOpenOffers,
                    onRefresh = onRefresh,
                    onDismissSyncFailure = onDismissSyncFailure,
                    bottomInset = true,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .height(maxHeight * SHEET_SHARE),
                )
            }

            // The controls that float over the map.
            Row(
                Modifier
                    .fillMaxWidth()
                    .statusBarsPadding()
                    .padding(horizontal = Spacing.lg, vertical = Spacing.sm),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                GlassIconButton(
                    icon = Icons.Filled.Menu,
                    contentDescription = strings["common.action.menu"],
                    onClick = onOpenMenu,
                )
                Spacer(Modifier.weight(1f))
                // Help stays on the face of home, not only in the drawer: it is on
                // screen whatever the sheet below is doing -- loading, empty, or
                // failed -- and it is the one door that must never be a menu away.
                //
                // It used to exist only inside `if (booking.isActive)` on booking
                // detail, so it vanished the moment a ride was cancelled or
                // completed -- and an expired session offline is still "signed
                // in", so the sign-in copy was unreachable too. A woman harassed
                // during a ride had no way to tell VELRO once she was out of the
                // car.
                GlassPillButton(
                    label = strings["safety.title"],
                    icon = Icons.Filled.Shield,
                    onClick = onGetHelp,
                )
                Spacer(Modifier.width(Spacing.sm))
                // Her own account, where the driver app puts its profile. This is
                // also the only way to change the language once signed in, so it
                // has to be reachable without reading anything -- which is why it
                // is an icon, with its name for a screen reader.
                GlassIconButton(
                    icon = Icons.Filled.Person,
                    contentDescription = strings["passenger.profile.title"],
                    onClick = onOpenAccount,
                )
            }
        }
    }
}

/**
 * The glass panel: the one action, and the last few trips.
 *
 * Fixed in place, with no grab bar -- a handle promises a drag, and this sheet
 * does not move. Its content scrolls only when it genuinely cannot fit, at the
 * largest font sizes or on the smallest screens; at an ordinary size the
 * scroll has nothing to do and the sheet is still.
 *
 * Pull to refresh went with the scrolling: a refresh gesture on a screen that
 * does not scroll is a gesture nobody finds. Home refreshes itself instead --
 * when it opens, each time it comes back into view, every ten seconds while an
 * ask is open, and from the retry on a failure.
 */
@Composable
private fun HomeSheet(
    state: HomeUiState,
    shape: RoundedCornerShape,
    onBook: () -> Unit,
    onOpenBooking: (String) -> Unit,
    onOpenHistory: () -> Unit,
    onOpenOffers: () -> Unit,
    onRefresh: () -> Unit,
    onDismissSyncFailure: (String) -> Unit,
    modifier: Modifier = Modifier,
    /** Pad for the navigation bar: the sheet runs to the bottom of the screen. */
    bottomInset: Boolean = false,
) {
    val strings = LocalVelroStrings.current
    Column(
        modifier
            .glassShadow(Radius.sheet, spread = SHEET_SPREAD)
            .background(glassFill(Glass.PANEL), shape)
            .border(glassRim(), shape)
            .verticalScroll(rememberScrollState())
            .then(if (bottomInset) Modifier.navigationBarsPadding() else Modifier)
            .padding(top = Spacing.xl, bottom = Spacing.lg),
    ) {
        Column(Modifier.padding(horizontal = Spacing.gutter)) {
            // While a request is live the sheet points at it, not at a new
            // search.
            //
            // The server allows one open request at a time, so the "Where to?"
            // bar -- the screen's one action -- was aimed at the one thing it
            // would refuse, while the way back to her own negotiation sat lower
            // down. She would tap it, be told no, and have learnt nothing about
            // where her drivers went. Now the card with its clock takes the
            // bar's place, and its button is the screen's primary action.
            val open = state.openRequest
            if (open != null) {
                OpenRequestCard(request = open, onOpen = onOpenOffers)
            } else {
                WhereToBar(onClick = onBook)
            }

            // A newer build on the server. One quiet card, tap to fetch --
            // the only update channel a sideloaded app has.
            state.updateUrl?.let { url ->
                Spacer(Modifier.height(Spacing.md))
                UpdateCard(url)
            }

            // The offline queue, made visible. A refused operation is a card
            // she must dismiss herself; work still waiting is one quiet line.
            for (failure in state.syncFailures) {
                Spacer(Modifier.height(Spacing.md))
                SyncFailureCard(
                    failure = failure,
                    onDismiss = { onDismissSyncFailure(failure.id) },
                )
            }
            if (state.pendingSync > 0) {
                Spacer(Modifier.height(Spacing.sm))
                Text(
                    strings["sync.pending.count", "count" to state.pendingSync],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        Spacer(Modifier.height(Spacing.md))
        Row(
            Modifier
                .fillMaxWidth()
                .padding(start = Spacing.gutter, end = Spacing.sm),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                strings["home.section.recent_trips"],
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            // Home shows the last three; everything else, and the receipts,
            // live behind this.
            TextButton(onClick = onOpenHistory) {
                Text(strings["history.title"], fontWeight = FontWeight.SemiBold)
            }
        }

        // Cached data, honestly labelled -- the same line every other screen
        // that caches uses.
        if (state.isStale && state.bookings.isNotEmpty()) {
            Text(
                strings["common.state.offline"],
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = Spacing.gutter),
            )
        }

        // The three states, compact: inside a scroll their full-screen frames
        // shrink to their content, so each is a few lines tall rather than a
        // page.
        when {
            state.isLoading -> LoadingState()
            // A failure is not an empty list.
            //
            // With nothing cached, this branch used to fall through to "No
            // bookings yet" -- an assertion about her own journeys that the
            // app had never managed to check, with nothing to retry and no
            // hint that anything had gone wrong.
            state.errorCode != null && state.bookings.isEmpty() -> ErrorState(
                errorCode = state.errorCode,
                context = state.errorContext,
                onRetry = onRefresh,
            )
            // No action here on purpose. "Where to?" is already the screen's
            // one action, just above -- repeating it in the empty state gives
            // one screen two primary actions and makes the second look like a
            // different, unexplained one.
            state.bookings.isEmpty() -> EmptyState(
                messageKey = "empty.bookings",
                icon = Icons.AutoMirrored.Filled.ReceiptLong,
            )
            else -> Column(Modifier.padding(horizontal = Spacing.xs)) {
                state.bookings.take(RECENT_LIMIT).forEachIndexed { index, booking ->
                    // Keyed, so a trip whose status changes while she looks
                    // keeps its own row rather than borrowing its neighbour's.
                    key(booking.id) {
                        if (index > 0) {
                            HorizontalDivider(
                                Modifier.padding(start = Spacing.xxxl + Spacing.xl, end = Spacing.lg),
                                color = MaterialTheme.colorScheme.outlineVariant,
                            )
                        }
                        BookingRow(
                            booking = booking,
                            onClick = { onOpenBooking(booking.id) },
                            contained = false,
                        )
                    }
                }
            }
        }
    }
}

/**
 * "Where to?" -- the bar every ride app a passenger may have used opens on.
 *
 * Shaped like a search field because that is what it is to her: tap, and say
 * where. The green disc at its end is the car she is about to ask for. The
 * line under it says the flow begins where she is standing, so the first thing
 * she sees after the tap -- her own position already found -- is what she was
 * told would happen.
 */
@Composable
private fun WhereToBar(onClick: () -> Unit) {
    val strings = LocalVelroStrings.current
    val shape = RoundedCornerShape(Radius.pill)
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        Surface(
            onClick = onClick,
            shape = shape,
            color = MaterialTheme.colorScheme.surface,
            contentColor = MaterialTheme.colorScheme.onSurface,
            border = glassRim(),
            modifier = Modifier
                .fillMaxWidth()
                .softShadow(shape, Elevation.floating)
                .height(WHERE_TO_HEIGHT)
                .testTag("home.search"),
        ) {
            Row(
                Modifier.padding(start = Spacing.xl, end = Spacing.sm),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    Icons.Filled.Search,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.size(Spacing.md))
                Text(
                    strings["home.search.where_to"],
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                )
                Box(
                    Modifier
                        .size(Sizing.avatar)
                        .background(MaterialTheme.colorScheme.primary, CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        Icons.Filled.DirectionsCar,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onPrimary,
                        modifier = Modifier.size(Sizing.iconMd),
                    )
                }
            }
        }
        Row(
            Modifier.padding(horizontal = Spacing.lg),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Filled.MyLocation,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(16.dp),
            )
            Spacer(Modifier.size(Spacing.xs))
            Text(
                strings["home.search.from_here"],
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private val WHERE_TO_HEIGHT = 60.dp

/**
 * Her open ask, with a clock on it.
 *
 * The countdown matters more than it looks: a request expires on its own, and
 * without a visible deadline the only two states she can tell apart are
 * "something is happening" and "nothing is happening" — which are the same
 * picture. Rendered from expiresAt, which the server already sends.
 */
@Composable
private fun OpenRequestCard(request: RideRequest, onOpen: () -> Unit) {
    val strings = LocalVelroStrings.current
    val offers = request.liveOffers.size

    VelroCard {
        Column(Modifier.fillMaxWidth()) {
            Text(
                strings["home.open_request.title"],
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(Spacing.xs))
            Text(
                if (offers > 0) {
                    strings["home.open_request.offers", "count" to offers]
                } else {
                    strings["home.open_request.waiting"]
                },
                style = MaterialTheme.typography.bodyMedium,
            )

            request.expiresAt?.let { deadline ->
                // Recomputed on every recomposition against the real clock, so
                // it cannot show a number that stopped being true while the
                // screen was in the background.
                val minutes = Calendars.minutesUntil(deadline, java.time.Instant.now())
                Spacer(Modifier.height(Spacing.xs))
                Text(
                    if (minutes >= 1) {
                        strings["home.open_request.expires_in", "minutes" to minutes]
                    } else {
                        strings["home.open_request.expiring"]
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            Spacer(Modifier.height(Spacing.lg))
            // Primary: with the request open, this is the screen's one action,
            // standing where "Where to?" stands the rest of the time. There is
            // no second button to the same place anywhere on home.
            PrimaryAction(
                label = strings["home.open_request.open"],
                onClick = onOpen,
                icon = Icons.Filled.Groups,
            )
        }
    }
}

/**
 * The side drawer: everything on home that is not the one action.
 *
 * Frosted glass over a light scrim, like the controls it is opened from. A
 * row per door, each with its icon in a pale circle and the chevron that says
 * it goes somewhere, a hairline between them.
 */
@Composable
private fun HomeDrawer(
    onClose: () -> Unit,
    onAccount: () -> Unit,
    onTrips: () -> Unit,
    onHelp: () -> Unit,
    onReports: () -> Unit,
    onPrivacy: () -> Unit,
) {
    val strings = LocalVelroStrings.current
    // Rounded on the end edge only, the one that faces the screen: the start
    // edge is the side of the display, and a curve there would float the
    // panel off it.
    val shape = RoundedCornerShape(topEnd = Radius.sheet, bottomEnd = Radius.sheet)
    ModalDrawerSheet(
        drawerShape = shape,
        drawerContainerColor = glassFill(Glass.DRAWER),
        drawerContentColor = MaterialTheme.colorScheme.onSurface,
        drawerTonalElevation = 0.dp,
        modifier = Modifier
            .fillMaxWidth(DRAWER_SHARE)
            .border(glassRim(), shape),
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(start = Spacing.xl, end = Spacing.sm, top = Spacing.lg, bottom = Spacing.lg),
            verticalAlignment = Alignment.Top,
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    strings["app.name"],
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                )
                Spacer(Modifier.height(Spacing.xxs))
                Text(
                    strings["app.tagline"],
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            IconButton(onClick = onClose, modifier = Modifier.size(Sizing.touchTarget)) {
                Icon(Icons.Filled.Close, contentDescription = strings["common.action.close"])
            }
        }

        val rows = listOf(
            Triple(Icons.Filled.Person, strings["passenger.profile.title"], onAccount),
            Triple(Icons.AutoMirrored.Filled.ReceiptLong, strings["history.title"], onTrips),
            Triple(Icons.Filled.Shield, strings["safety.title"], onHelp),
            Triple(Icons.Filled.Flag, strings["safety.my_reports"], onReports),
            Triple(Icons.Filled.PrivacyTip, strings["account.privacy"], onPrivacy),
        )
        rows.forEachIndexed { index, (icon, label, onClick) ->
            if (index > 0) {
                HorizontalDivider(
                    Modifier.padding(start = Spacing.xxxl + Spacing.xl, end = Spacing.lg),
                    color = MaterialTheme.colorScheme.outlineVariant,
                )
            }
            IconRow(
                title = label,
                onClick = onClick,
                icon = icon,
                contained = false,
                modifier = Modifier.padding(horizontal = Spacing.xs),
            )
        }
    }
}

/** Most of the width, so home stays visible at the edge and reads as underneath. */
private const val DRAWER_SHARE = 0.8f

/**
 * A queued operation the server refused, in the person's own words.
 *
 * The kind line says what it was; the second line is the server's actual
 * reason rendered through the same translations every error uses, so a seat
 * that ran out while she was offline reads as exactly that.
 */
@Composable
private fun SyncFailureCard(
    failure: PendingOperationEntity,
    onDismiss: () -> Unit,
) {
    val strings = LocalVelroStrings.current
    VelroCard {
        Column {
            // A literal key per kind, not a concatenation: the localisation
            // guard test reads these files for every key the apps ask for,
            // and a key assembled at runtime is invisible to it -- which is
            // exactly how a missing translation would ship unnoticed.
            val kindKey = when (failure.kind) {
                OperationKind.BOOK_SEATS -> "sync.kind.book_seats"
                OperationKind.CANCEL_BOOKING -> "sync.kind.cancel_booking"
                else -> "sync.kind.rate_trip"
            }
            Text(
                strings["sync.failed.title"] + " — " + strings[kindKey],
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.error,
            )
            failure.lastError?.let { code ->
                Spacer(Modifier.height(Spacing.xs))
                Text(
                    strings.forErrorCode(code, emptyMap()),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            Spacer(Modifier.height(Spacing.md))
            SecondaryAction(
                label = strings["common.action.close"],
                onClick = onDismiss,
            )
        }
    }
}

/** The sideload world's whole update mechanism: a card and a browser. */
@Composable
private fun UpdateCard(url: String) {
    val strings = LocalVelroStrings.current
    val context = LocalContext.current
    VelroCard(
        onClick = {
            runCatching {
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
            }
        },
    ) {
        Text(
            strings["app.update.body"],
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.primary,
        )
    }
}
