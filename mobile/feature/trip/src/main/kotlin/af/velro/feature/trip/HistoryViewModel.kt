package af.velro.feature.trip

import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import af.velro.data.repository.BookingRepository
import af.velro.domain.Booking
import af.velro.domain.BookingStatus
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Booking history, section 73.
 *
 * Split the way a passenger thinks about it: a journey still to come, which
 * they may need to board or cancel, and one already taken, which they only want
 * a record of. Which statuses fall on which side is the server's answer, so the
 * two surfaces cannot drift apart.
 */
enum class HistoryScope(val wire: String, val statuses: List<BookingStatus>) {
    // The same split the server applies, so the cached view cannot put a
    // booking under a different tab than the fresh one does.
    UPCOMING(
        "upcoming",
        listOf(
            BookingStatus.PENDING,
            BookingStatus.CONFIRMED,
            BookingStatus.DRIVER_ASSIGNED,
            BookingStatus.READY,
            BookingStatus.ONBOARD,
        ),
    ),
    PAST(
        "past",
        listOf(BookingStatus.COMPLETED, BookingStatus.CANCELLED, BookingStatus.NO_SHOW),
    ),
}

data class HistoryUiState(
    val scope: HistoryScope = HistoryScope.UPCOMING,
    val bookings: List<Booking> = emptyList(),
    val isLoading: Boolean = true,
    val isLoadingMore: Boolean = false,
    val hasMore: Boolean = false,
    val nextOffset: Int = 0,
    val isStale: Boolean = false,
    /**
     * A refresh the passenger pulled for, not a tab change.
     *
     * Distinct from [isLoading] because the two want opposite things on
     * screen: switching tabs must clear the list, or finished journeys sit
     * under "upcoming"; pulling to refresh must keep it, or the receipt she
     * was reading vanishes under a spinner she asked for.
     */
    val isRefreshing: Boolean = false,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
)

sealed interface HistoryEvent {
    data object Refresh : HistoryEvent
    data object LoadMore : HistoryEvent
    data class ScopeChanged(val scope: HistoryScope) : HistoryEvent
}

private const val PAGE = 15

@HiltViewModel
class HistoryViewModel @Inject constructor(
    private val bookings: BookingRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(HistoryUiState())
    val state: StateFlow<HistoryUiState> = _state.asStateFlow()

    init { load(HistoryScope.UPCOMING) }

    fun onEvent(event: HistoryEvent) {
        when (event) {
            HistoryEvent.Refresh -> refresh()
            HistoryEvent.LoadMore -> loadMore()
            is HistoryEvent.ScopeChanged ->
                if (event.scope != _state.value.scope) load(event.scope)
        }
    }

    /**
     * Re-fetch the current tab without emptying it.
     *
     * Shares [load]'s network path deliberately -- two ways of asking the
     * server for the same page would drift -- but not its opening `update`,
     * which is the part that clears the list.
     */
    private fun refresh() {
        val scope = _state.value.scope
        _state.update { it.copy(isRefreshing = true, errorCode = null) }
        viewModelScope.launch {
            when (val page = bookings.history(limit = PAGE, offset = 0, scope = scope.wire)) {
                is ApiResult.Success -> _state.update {
                    if (it.scope != scope) return@update it
                    it.copy(
                        bookings = page.value.bookings,
                        hasMore = page.value.hasMore,
                        nextOffset = page.value.nextOffset,
                        isStale = false,
                        errorCode = null,
                    )
                }
                // The cached list stays. A failed refresh has not deleted her
                // journeys, and withError marks the list stale so the screen
                // says so.
                is ApiResult.Failure -> _state.update {
                    if (it.scope != scope) it else it.withError(page.error)
                }
            }
            // Cleared whatever happened, or the indicator spins forever on a
            // phone with no signal -- the case this app is built for.
            _state.update { it.copy(isRefreshing = false) }
        }
    }

    private fun load(scope: HistoryScope) {
        _state.update {
            // The list is cleared with the tab. Leaving the previous tab's
            // bookings on screen while the new ones load shows a passenger
            // finished journeys under "upcoming", which is worse than a spinner.
            it.copy(scope = scope, bookings = emptyList(), isLoading = true, errorCode = null)
        }
        viewModelScope.launch {
            // Cache first, then the network. In Ghorband the cached answer is
            // often the only one that arrives, and a receipt the passenger
            // already downloaded should never be behind an error page.
            val cached = bookings.cachedHistory(scope.statuses)
            if (cached.isNotEmpty()) {
                _state.update {
                    if (it.scope == scope) it.copy(bookings = cached, isLoading = false)
                    else it
                }
            }

            when (val page = bookings.history(limit = PAGE, offset = 0, scope = scope.wire)) {
                is ApiResult.Success -> _state.update {
                    if (it.scope != scope) return@update it
                    it.copy(
                        bookings = page.value.bookings,
                        hasMore = page.value.hasMore,
                        nextOffset = page.value.nextOffset,
                        isLoading = false,
                        isStale = false,
                        errorCode = null,
                    )
                }
                is ApiResult.Failure -> _state.update {
                    if (it.scope != scope) it else it.withError(page.error)
                }
            }
        }
    }

    private fun loadMore() {
        val current = _state.value
        if (current.isLoadingMore || !current.hasMore) return
        _state.update { it.copy(isLoadingMore = true) }
        viewModelScope.launch {
            val page = bookings.history(
                limit = PAGE, offset = current.nextOffset, scope = current.scope.wire
            )
            when (page) {
                is ApiResult.Success -> _state.update {
                    // A booking made while the passenger reads page one shifts
                    // every later row; without this the shifted booking appears
                    // on both pages.
                    val seen = it.bookings.mapTo(mutableSetOf()) { b -> b.id }
                    it.copy(
                        bookings = it.bookings + page.value.bookings.filter { b -> b.id !in seen },
                        hasMore = page.value.hasMore,
                        nextOffset = page.value.nextOffset,
                        isLoadingMore = false,
                    )
                }
                is ApiResult.Failure ->
                    _state.update { it.copy(isLoadingMore = false).withError(page.error) }
            }
        }
    }
}

private fun HistoryUiState.withError(error: ApiException) = copy(
    isLoading = false,
    isLoadingMore = false,
    // Offline with nothing cached is still an error; offline with rows on
    // screen is a staleness marker, not a failure.
    isStale = error.code == ApiException.OFFLINE && bookings.isNotEmpty(),
    errorCode = if (error.code == ApiException.OFFLINE && bookings.isNotEmpty()) null
    else error.code,
    errorContext = error.context,
)
