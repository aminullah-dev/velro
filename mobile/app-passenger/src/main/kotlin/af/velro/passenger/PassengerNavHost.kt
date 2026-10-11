package af.velro.passenger

import af.velro.core.ui.theme.LocalAnimationsEnabled
import af.velro.core.ui.theme.NavMotion
import af.velro.feature.auth.DeleteAccountRoute
import af.velro.feature.auth.SignInRoute
import af.velro.feature.booking.BookingFlowRoute
import af.velro.feature.booking.OffersRoute
import af.velro.feature.safety.HelpSheet
import af.velro.feature.safety.ReportsRoute
import af.velro.feature.trip.BookingDetailRoute
import af.velro.feature.trip.HistoryRoute
import af.velro.feature.trip.TrackRideRoute
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
    const val TRACK = "track/{bookingId}"
    const val HISTORY = "history"
    const val REPORTS = "reports"
    const val OFFERS = "offers"
    const val ACCOUNT = "account"
    const val DELETE_ACCOUNT = "account/delete"

    fun bookingDetail(id: String) = "booking/$id"
    fun track(id: String) = "track/$id"
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
                    // The drawer's door to her reports: the same screen the
                    // help sheet's "your reports" opens.
                    onOpenReports = { navController.navigate(Routes.REPORTS) },
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

        composable(Routes.BOOKING_DETAIL) { entry ->
            BookingDetailRoute(
                onBack = { navController.popBackStack() },
                onTrack = {
                    navController.navigate(
                        Routes.track(entry.arguments?.getString("bookingId") ?: return@BookingDetailRoute)
                    )
                },
            )
        }

        composable(Routes.TRACK) {
            TrackRideRoute(onBack = { navController.popBackStack() })
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
                onDeleteAccount = { navController.navigate(Routes.DELETE_ACCOUNT) },
                onBack = { navController.popBackStack() },
            )
        }
        // No success callback, on purpose: a deleted account is an ended
        // session, and the effect at the top of this host already takes an
        // ended session to sign-in with the back stack cleared.
        composable(Routes.DELETE_ACCOUNT) {
            DeleteAccountRoute(
                isDriverApp = false,
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
