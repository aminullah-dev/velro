package af.velro.data.duty

import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * The channel between the duty service and the driver's screen.
 *
 * The service owns the truth (it runs with the screen off); the screen
 * merely renders whatever is current when it happens to be looking. Neither
 * side may call the other -- a service holding a ViewModel, or a ViewModel
 * holding a service, is a leak wearing a collar.
 */
@Singleton
class DutySignals @Inject constructor() {

    private val _roadAlertKey = MutableStateFlow<String?>(null)
    /** The advisory zone the driver is inside right now, as a message key. */
    val roadAlertKey: StateFlow<String?> = _roadAlertKey.asStateFlow()

    fun roadAlert(key: String?) {
        _roadAlertKey.value = key
    }
}

/**
 * How the ViewModel asks for the service without knowing it exists.
 *
 * The service class lives in the app module (services are an application's
 * business); the ViewModel lives in a feature module that must not depend on
 * the app. This interface is the one hand reaching across, bound by Hilt in
 * the app module.
 */
interface DutyController {
    /** Idempotent: running stays running. */
    fun ensureRunning()
    fun stop()
}
