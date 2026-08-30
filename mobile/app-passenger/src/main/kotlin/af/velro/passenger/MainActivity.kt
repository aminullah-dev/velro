package af.velro.passenger

import af.velro.core.i18n.Strings
import af.velro.core.ui.theme.VelroTheme
import af.velro.data.repository.AuthRepository
import af.velro.domain.Locale
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject lateinit var auth: AuthRepository

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val locale by auth.locale.collectAsStateWithLifecycle(initialValue = Locale.DARI)
            val signedIn by auth.isSignedIn.collectAsStateWithLifecycle(initialValue = false)
            val scope = rememberCoroutineScope()

            // Strings are reloaded when the language changes, and the theme
            // derives its layout direction from the same value -- so switching
            // to English flips the whole app to LTR without a restart.
            val strings = rememberStrings(locale)
            if (strings != null) {
                VelroTheme(strings) {
                    PassengerNavHost(
                        isSignedIn = signedIn,
                        // Clears the local session and wipes the cache before
                        // telling the server. A shared handset is common here,
                        // and the next person must not see the last one's
                        // journeys. isSignedIn then flips and the nav host
                        // sends them to sign-in with the back stack cleared.
                        onSignOut = { scope.launch { auth.signOut() } },
                    )
                }
            }
        }
    }
}

@Composable
private fun rememberStrings(locale: Locale): Strings? {
    val context = LocalContext.current
    val strings by produceState<Strings?>(initialValue = null, locale) {
        value = Strings.load(context, locale)
    }
    return strings
}
