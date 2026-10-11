package af.velro.passenger

import af.velro.core.i18n.Strings
import af.velro.core.ui.theme.VelroTheme
import af.velro.data.repository.AuthRepository
import af.velro.domain.Locale
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import af.velro.passenger.onboarding.OnboardingScreen
import af.velro.passenger.onboarding.OnboardingStore
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.Composable
import kotlinx.coroutines.flow.map
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
    @Inject lateinit var onboarding: OnboardingStore

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val locale by auth.locale.collectAsStateWithLifecycle(initialValue = Locale.DARI)
            // Null until the session store has actually been read. The nav host
            // still gets `false` for that moment, exactly as before; only the
            // onboarding decision below waits for the real answer.
            val session by remember { auth.isSignedIn.map<Boolean, Boolean?> { it } }
                .collectAsStateWithLifecycle(initialValue = null)
            val signedIn = session ?: false
            val seen by remember { onboarding.seen.map<Boolean, Boolean?> { it } }
                .collectAsStateWithLifecycle(initialValue = null)
            val scope = rememberCoroutineScope()

            // Strings are reloaded when the language changes, and the theme
            // derives its layout direction from the same value -- so switching
            // to English flips the whole app to LTR without a restart.
            val strings = rememberStrings(locale)
            if (strings != null) {
                VelroTheme(strings) {
                    when {
                        // A few milliseconds while the two stores are read.
                        // Nothing is drawn rather than a guess: guessing
                        // "not seen" would flash the pages at somebody who
                        // has used the app for a year, and guessing "seen"
                        // would skip them for the person they are for.
                        seen == null -> Unit
                        seen == false && session == null -> Unit

                        // First launch, signed out: the three pages, once.
                        seen == false && session == false -> OnboardingScreen(
                            locale = locale,
                            onLocaleChanged = { chosen -> scope.launch { auth.setLocale(chosen) } },
                            onDone = { scope.launch { onboarding.markSeen() } },
                        )

                        else -> {
                            // Somebody already signed in -- an update over an
                            // installed app -- has no use for an introduction
                            // to it, and should not get one after signing out
                            // either.
                            if (seen == false && session == true) {
                                LaunchedEffect(Unit) { onboarding.markSeen() }
                            }
                            PassengerNavHost(
                                isSignedIn = signedIn,
                                // Clears the local session and wipes the cache
                                // before telling the server. A shared handset
                                // is common here, and the next person must not
                                // see the last one's journeys. isSignedIn then
                                // flips and the nav host sends them to sign-in
                                // with the back stack cleared.
                                onSignOut = { scope.launch { auth.signOut() } },
                            )
                        }
                    }
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
