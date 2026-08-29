package af.velro.passenger

import af.velro.core.ui.component.BookingCard
import af.velro.core.ui.component.EmptyState
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.feature.auth.SignInRoute
import af.velro.feature.booking.BookingFlowRoute
import af.velro.feature.trip.BookingDetailRoute
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
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
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

    fun bookingDetail(id: String) = "booking/$id"
}

@Composable
fun PassengerNavHost(isSignedIn: Boolean, navController: NavHostController = rememberNavController()) {
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
            HomeScreen(
                onBook = { navController.navigate(Routes.BOOK) },
                onOpenBooking = { navController.navigate(Routes.bookingDetail(it)) },
            )
        }

        composable(Routes.BOOK) {
            BookingFlowRoute(
                onFinished = { bookingId ->
                    navController.navigate(Routes.bookingDetail(bookingId)) {
                        popUpTo(Routes.HOME)
                    }
                },
                onExit = { navController.popBackStack() },
            )
        }

        composable(Routes.BOOKING_DETAIL) {
            BookingDetailRoute()
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
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val strings = LocalVelroStrings.current
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        topBar = { TopAppBar(title = { Text(strings["app.name"]) }) },
    ) { padding ->
        Column(
            Modifier
                .padding(padding)
                .fillMaxSize()
                .padding(horizontal = Spacing.gutter)
        ) {
            Spacer(Modifier.height(Spacing.lg))
            PrimaryAction(
                label = strings["home.action.search"],
                onClick = onBook,
                icon = Icons.Filled.DirectionsCar,
            )
            Spacer(Modifier.height(Spacing.xl))

            Text(
                strings["home.section.recent_trips"],
                style = MaterialTheme.typography.titleMedium,
            )
            Spacer(Modifier.height(Spacing.sm))

            when {
                state.isLoading -> LoadingState()
                state.bookings.isEmpty() -> EmptyState(
                    messageKey = "empty.bookings",
                    actionKey = "home.action.search",
                    onAction = onBook,
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
