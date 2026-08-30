package af.velro.passenger

import af.velro.core.i18n.Calendars
import af.velro.domain.RideRequest
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.ConfirmDialog
import af.velro.core.ui.component.BookingCard
import af.velro.core.ui.component.EmptyState
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
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

    NavHost(
        navController = navController,
        startDestination = if (isSignedIn) Routes.HOME else Routes.SIGN_IN,
    ) {
        composable(Routes.SIGN_IN) {
            SignInRoute(
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
    onOpenOffers: () -> Unit,
    onSignOut: () -> Unit,
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val strings = LocalVelroStrings.current
    val state by viewModel.state.collectAsStateWithLifecycle()
    var signingOut by remember { mutableStateOf(false) }

    // Confirmed, because it wipes the local cache: on a handset shared between
    // a household this is the right behaviour, and it is also unrecoverable
    // without a working connection to sign back in.
    if (signingOut) {
        ConfirmDialog(
            titleKey = "auth.action.sign_out",
            bodyKey = "auth.sign_out_warning",
            confirmKey = "auth.action.sign_out",
            onConfirm = { signingOut = false; onSignOut() },
            onDismiss = { signingOut = false },
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(strings["app.name"]) },
                // In the bar, so it is on screen whatever the list below is
                // doing -- loading, empty, or failed.
                actions = {
                    TextButton(onClick = onGetHelp) {
                        Text(strings["safety.title"])
                    }
                    // Icon rather than a second label: two words of Dari in a
                    // bar leaves nothing for the title. The description is what
                    // a screen reader announces.
                    IconButton(onClick = { signingOut = true }) {
                        Icon(
                            Icons.AutoMirrored.Filled.Logout,
                            contentDescription = strings["auth.action.sign_out"],
                        )
                    }
                },
            )
        },
    ) { padding ->
        Column(
            Modifier
                .padding(padding)
                .fillMaxSize()
                .padding(horizontal = Spacing.gutter)
        ) {
            Spacer(Modifier.height(Spacing.lg))

            // The ask she has open right now, above everything.
            //
            // Home showed only bookings, so a woman who closed the app while
            // drivers were bidding had no route back to her own request — and
            // the server refuses a second one while the first is alive, so she
            // was locked out of the journey she had started, by her own app,
            // with no way to see why.
            state.openRequest?.let { request ->
                OpenRequestCard(request = request, onOpen = onOpenOffers)
                Spacer(Modifier.height(Spacing.lg))
            }

            PrimaryAction(
                label = strings["home.action.search"],
                onClick = onBook,
                icon = Icons.Filled.DirectionsCar,
            )
            Spacer(Modifier.height(Spacing.xl))

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

            when {
                state.isLoading -> LoadingState()
                // No action here on purpose. "Search for a car" is already the
                // screen's primary button, forty pixels up -- repeating it in
                // the empty state gives one screen two primary actions and
                // makes the second look like a different, unexplained one.
                state.bookings.isEmpty() -> EmptyState(
                    messageKey = "empty.bookings",
                    icon = Icons.Filled.ReceiptLong,
                )
                else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                    items(state.bookings, key = { it.id }) { booking ->
                        BookingCard(booking = booking, onClick = { onOpenBooking(booking.id) })
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
            PrimaryAction(
                label = strings["home.open_request.open"],
                onClick = onOpen,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}
