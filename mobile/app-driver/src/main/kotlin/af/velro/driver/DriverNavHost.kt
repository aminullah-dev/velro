package af.velro.driver

import af.velro.feature.auth.SignInRoute
import af.velro.feature.driver.DocumentsRoute
import af.velro.feature.safety.ReportsRoute
import af.velro.feature.driver.BoardRoute
import af.velro.feature.driver.DriverHomeRoute
import af.velro.feature.driver.EarningsRoute
import af.velro.feature.driver.VehicleRoute
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController

private object Routes {
    const val SIGN_IN = "sign-in"
    const val HOME = "home"
    const val DOCUMENTS = "documents"
    const val VEHICLE = "vehicle"
    const val EARNINGS = "earnings"
    const val BOARD = "board"
    const val REPORTS = "reports"
}

/**
 * The driver app has one screen that matters.
 *
 * Section 74: online/offline, the current trip, requests, earnings. A driver
 * uses this between passengers and often while moving, so navigation depth is
 * the enemy -- everything operational lives on one screen.
 */
@Composable
fun DriverNavHost(
    isSignedIn: Boolean,
    navController: NavHostController = rememberNavController(),
) {
    LaunchedEffect(isSignedIn) {
        if (!isSignedIn) {
            navController.navigate(Routes.SIGN_IN) { popUpTo(0) { inclusive = true } }
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
            DriverHomeRoute(
                onOpenDocuments = { navController.navigate(Routes.DOCUMENTS) },
                onOpenVehicle = { navController.navigate(Routes.VEHICLE) },
                onOpenEarnings = { navController.navigate(Routes.EARNINGS) },
                onOpenBoard = { navController.navigate(Routes.BOARD) },
                onOpenReports = { navController.navigate(Routes.REPORTS) },
            )
        }
        // Every pushed destination is given a way back. Until now none of
        // them had one: no bar, no arrow, and BackHandler appeared nowhere in
        // the codebase, so the only route out was a system gesture many people
        // on a cheap handset do not use.
        val back: () -> Unit = { navController.popBackStack() }

        composable(Routes.DOCUMENTS) { DocumentsRoute(onBack = back) }
        composable(Routes.VEHICLE) { VehicleRoute(onBack = back) }
        composable(Routes.EARNINGS) { EarningsRoute(onBack = back) }
        composable(Routes.REPORTS) { ReportsRoute(onBack = back) }
        composable(Routes.BOARD) { BoardRoute(onBack = back) }
    }
}
