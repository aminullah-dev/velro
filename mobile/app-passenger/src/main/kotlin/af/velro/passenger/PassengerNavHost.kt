package af.velro.passenger

import androidx.compose.ui.platform.LocalContext
import af.velro.data.db.OperationKind
import af.velro.data.db.PendingOperationEntity
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import af.velro.core.ui.theme.NavMotion
import af.velro.core.ui.theme.LocalAnimationsEnabled
import af.velro.core.i18n.Calendars
import af.velro.domain.RideRequest
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.ConfirmDialog
import af.velro.core.ui.component.BookingCard
import af.velro.core.ui.component.BrandHeader
import af.velro.core.ui.theme.VelroColors
import af.velro.core.ui.component.OnBrandAction
import af.velro.core.ui.component.EmptyState
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.feature.auth.SignInRoute
import af.velro.feature.booking.BookingFlowRoute
import af.velro.feature.booking.OffersRoute
import af.velro.feature.trip.BookingDetailRoute
import af.velro.feature.trip.HistoryRoute
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.Groups
import androidx.compose.material.icons.filled.ReceiptLong
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Scaffold
import androidx.compose.material3.TextButton
import androidx.compose.ui.Alignment
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import af.velro.feature.safety.HelpSheet
import af.velro.feature.safety.ReportsRoute
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController

private object Routes {
    const val SIGN_IN = "sign-in"
    const val HOME = "home"
    const val BOOK = "book"
    const val BOOKING_DETAIL = "booking/{bookingId}"
    const val HISTORY = "history"
    const val REPORTS = "reports"
    const val OFFERS = "offers"
    const val ACCOUNT = "account"

    fun bookingDetail(id: String) = "booking/$id"
}

@Composable
fun PassengerNavHost(
    isSignedIn: Boolean,
    onSignOut: () -> Unit = {},
    navController: NavHostController = rememberNavController(),
) {
    LaunchedEffect(isSignedIn) {
        // A session that ended -- a revoked refresh token, or signing out --
        // returns to sign-in and clears the back stack, so pressing back cannot
        // land on a screen that needs a token.
        if (!isSignedIn) {
            navController.navigate(Routes.SIGN_IN) {
                popUpTo(0) { inclusive = true }
            }
        }
    }

    // One motion spec for both apps, and honoured only when the person has
    // left system animation on -- see LocalAnimationsEnabled.
    val animate = LocalAnimationsEnabled.current

    NavHost(
        navController = navController,
        startDestination = if (isSignedIn) Routes.HOME else Routes.SIGN_IN,
        enterTransition = { NavMotion.enter(this, animate) },
        exitTransition = { NavMotion.exit(this, animate) },
        popEnterTransition = { NavMotion.popEnter(this, animate) },
        popExitTransition = { NavMotion.popExit(this, animate) },
    ) {
        composable(Routes.SIGN_IN) {
            SignInRoute(
                taglineKey = "app.tagline",
                onSignedIn = { _, _ ->
                    navController.navigate(Routes.HOME) {
                        popUpTo(Routes.SIGN_IN) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.HOME) {
            // Get help, on the screen a passenger is on when they are not
            // mid-journey.
            //
            // It used to exist only inside `if (booking.isActive)` on booking
            // detail, so it vanished the moment a ride was cancelled or
            // completed -- and an expired session offline is still "signed in"
            // (TokenStore reads DataStore; nothing produces a 401 without a
            // server), so the sign-in copy was unreachable too. A woman
            // harassed during a ride had no way to tell VELRO once she was out
            // of the car.
            var helpOpen by remember { mutableStateOf(false) }
            Box(Modifier.fillMaxSize()) {
                HomeScreen(
                    onBook = { navController.navigate(Routes.BOOK) },
                    onOpenBooking = { navController.navigate(Routes.bookingDetail(it)) },
                    onOpenHistory = { navController.navigate(Routes.HISTORY) },
                    onGetHelp = { helpOpen = true },
                    onOpenAccount = { navController.navigate(Routes.ACCOUNT) },
                    onOpenOffers = { navController.navigate(Routes.OFFERS) },
                    onSignOut = onSignOut,
                )
                if (helpOpen) {
                    HelpSheet(
                        ride = null,
                        onOpenReports = {
                            helpOpen = false
                            navController.navigate(Routes.REPORTS)
                        },
                        onDismiss = { helpOpen = false },
                    )
                }
            }
        }

        composable(Routes.REPORTS) {
            ReportsRoute(onBack = { navController.popBackStack() })
        }

        composable(Routes.BOOK) {
            BookingFlowRoute(
                onFinished = { bookingId ->
                    navController.navigate(Routes.bookingDetail(bookingId)) {
                        popUpTo(Routes.HOME)
                    }
                },
                onAsked = {
                    navController.navigate(Routes.OFFERS) {
                        popUpTo(Routes.HOME)
                    }
                },
                onExit = { navController.popBackStack() },
            )
        }

        composable(Routes.BOOKING_DETAIL) {
            BookingDetailRoute(onBack = { navController.popBackStack() })
        }

        composable(Routes.OFFERS) {
            OffersRoute(
                onRideAgreed = { bookingId ->
                    navController.navigate(Routes.bookingDetail(bookingId)) {
                        popUpTo(Routes.HOME)
                    }
                },
                onFinished = { navController.popBackStack() },
            )
        }

        composable(Routes.ACCOUNT) {
            AccountRoute(
                onSignOut = onSignOut,
                onBack = { navController.popBackStack() },
            )
        }
        composable(Routes.HISTORY) {
            HistoryRoute(
                onBack = { navController.popBackStack() },
                onOpenBooking = { navController.navigate(Routes.bookingDetail(it)) },
                onBook = { navController.navigate(Routes.BOOK) },
            )
        }
    }
}

/**
 * Home, section 72.
 *
 * One action and a list of what the passenger already has. Nothing else: a home
 * screen that tries to show everything is the fastest way to make a first-time
 * user close the app.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun HomeScreen(
    onBook: () -> Unit,
    onOpenBooking: (String) -> Unit,
    onOpenHistory: () -> Unit,
    onGetHelp: () -> Unit,
    onOpenAccount: () -> Unit,
    onOpenOffers: () -> Unit,
    onSignOut: () -> Unit,
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val strings = LocalVelroStrings.current
    val state by viewModel.state.collectAsStateWithLifecycle()

    // Confirmed, because it wipes the local cache: on a handset shared between
    // a household this is the right behaviour, and it is also unrecoverable
    // without a working connection to sign back in.

    Scaffold { padding ->
        Column(
            Modifier
                .padding(bottom = padding.calculateBottomPadding())
                .fillMaxSize()
        ) {
            // The brand owns the top of the screen, and the one action the
            // screen exists for sits inside it. Previously this was a white
            // Material app bar with the word VELRO in it, above a white page
            // with a green rectangle floating on it.
            BrandHeader(
                title = strings["app.name"],
                actions = {
                    // In the header, so it is on screen whatever the list
                    // below is doing -- loading, empty, or failed.
                    TextButton(
                        onClick = onGetHelp,
                        colors = ButtonDefaults.textButtonColors(
                            // The field these sit on is constant, so
                            // its foreground is too. onPrimary is the
                            // near-black Green900 after dark: 1.91:1
                            // on the header, which is a help button
                            // nobody can find in the dark.
                            contentColor = VelroColors.OnBrandField,
                        ),
                    ) {
                        Text(strings["safety.title"])
                    }
                    // Icon rather than a second label: two words of Dari in a
                    // bar leaves nothing for the title. The description is what
                    // a screen reader announces.
                    // Her own account, where the driver app puts its profile.
                    // This is also the only way to change the language once
                    // signed in, so it has to be reachable without reading
                    // anything -- which is why it is an icon.
                    IconButton(onClick = onOpenAccount) {
                        Icon(
                            Icons.Filled.AccountCircle,
                            contentDescription = strings["passenger.profile.title"],
                            tint = VelroColors.OnBrandField,
                        )
                    }
                },
            ) {
                Spacer(Modifier.height(Spacing.lg))
                // While a request is live the header points at it, not at a
                // new search.
                //
                // The server allows one open request at a time, so the hero
                // slot -- the white-on-green button the header exists to
                // spotlight -- was aimed at the one action it would refuse,
                // while the way back to her own negotiation sat lower down the
                // page in a card. She would tap the big button, be told no,
                // and have learnt nothing about where her drivers went.
                val open = state.openRequest
                if (open != null) {
                    OnBrandAction(
                        label = strings["home.open_request.open"],
                        onClick = onOpenOffers,
                        icon = Icons.Filled.Groups,
                    )
                } else {
                    OnBrandAction(
                        label = strings["home.action.search"],
                        onClick = onBook,
                        icon = Icons.Filled.DirectionsCar,
                    )
                }
            }

            Column(Modifier.fillMaxSize().padding(horizontal = Spacing.gutter)) {
            Spacer(Modifier.height(Spacing.lg))

            // The ask she has open right now, above everything.
            //
            // Home showed only bookings, so a woman who closed the app while
            // drivers were bidding had no route back to her own request — and
            // A newer build on the server. One quiet card, tap to fetch --
            // the only update channel a sideloaded app has.
            state.updateUrl?.let { url -> UpdateCard(url) }

            // the server refuses a second one while the first is alive, so she
            // was locked out of the journey she had started, by her own app,
            // with no way to see why.
            // The offline queue, made visible. A refused operation is a card
            // she must dismiss herself; work still waiting is one quiet line.
            for (failure in state.syncFailures) {
                SyncFailureCard(
                    failure = failure,
                    onDismiss = { viewModel.dismissSyncFailure(failure.id) },
                )
                Spacer(Modifier.height(Spacing.sm))
            }
            if (state.pendingSync > 0) {
                Text(
                    strings["sync.pending.count", "count" to state.pendingSync],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(Spacing.sm))
            }

            state.openRequest?.let { request ->
                OpenRequestCard(request = request, onOpen = onOpenOffers)
                Spacer(Modifier.height(Spacing.lg))
            }

            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    strings["home.section.recent_trips"],
                    style = MaterialTheme.typography.titleMedium,
                )
                // Home shows the few most recent; everything else, and the
                // receipts, live behind this.
                TextButton(onClick = onOpenHistory) { Text(strings["history.title"]) }
            }
            Spacer(Modifier.height(Spacing.sm))

            // Cached data, honestly labelled -- the same line every other
            // screen that caches uses.
            if (state.isStale && state.bookings.isNotEmpty()) {
                Text(
                    strings["common.state.offline"],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(Spacing.xs))
            }

            // Pull to refresh.
            //
            // `refresh()` existed and was reachable from exactly one place: the
            // retry button on the error state. So a passenger looking at the
            // "showing saved data" line -- the offline case this app is built
            // around -- could read that her list was old and do nothing about
            // it but leave the screen and come back.
            PullToRefreshBox(
                isRefreshing = state.isRefreshing,
                onRefresh = { viewModel.refresh() },
                modifier = Modifier.fillMaxSize(),
            ) {
            when {
                state.isLoading -> LoadingState()
                // A failure is not an empty list.
                //
                // With nothing cached, this branch used to fall through to
                // "No bookings yet" -- an assertion about her own journeys
                // that the app had never managed to check, with nothing to
                // retry and no hint that anything had gone wrong.
                state.errorCode != null && state.bookings.isEmpty() -> ErrorState(
                    errorCode = state.errorCode!!,
                    context = state.errorContext,
                    onRetry = { viewModel.refresh() },
                )
                // No action here on purpose. "Search for a car" is already the
                // screen's primary button, forty pixels up -- repeating it in
                // the empty state gives one screen two primary actions and
                // makes the second look like a different, unexplained one.
                state.bookings.isEmpty() -> EmptyState(
                    messageKey = "empty.bookings",
                    icon = Icons.Filled.ReceiptLong,
                )
                else -> LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                    modifier = Modifier.fillMaxSize(),
                ) {
                    items(state.bookings, key = { it.id }) { booking ->
                        BookingCard(
                            booking = booking,
                            onClick = { onOpenBooking(booking.id) },
                            // A booking whose status changes while she is
                            // looking at it -- a driver assigned, a trip
                            // finished -- moves in the list rather than
                            // teleporting.
                            modifier = Modifier.animateItem(),
                        )
                    }
                }
            }
            }
            }
        }
    }
}


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
                fontWeight = FontWeight.SemiBold,
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

            Spacer(Modifier.height(Spacing.md))
            // Secondary, because the header above now carries this same
            // destination as the screen's one primary action. Two full-width
            // green buttons opening the same screen is not emphasis, it is a
            // question about whether they do different things.
            SecondaryAction(
                label = strings["home.open_request.open"],
                onClick = onOpen,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}


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
                context.startActivity(
                    android.content.Intent(
                        android.content.Intent.ACTION_VIEW,
                        android.net.Uri.parse(url),
                    )
                )
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
