package af.velro.feature.booking

import af.velro.core.i18n.MoneyFormatter
import af.velro.domain.DEFAULT_CURRENCY
import af.velro.domain.MoneyValue
import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.BoardingCode
import af.velro.core.ui.component.EmptyState
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.FareRow
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SeatAvailability
import af.velro.core.ui.component.StationRow
import af.velro.core.ui.component.TripOptionCard
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.domain.Destination
import af.velro.domain.DestinationGroup
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.OutlinedTextField
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun BookingFlowRoute(
    onFinished: (bookingId: String) -> Unit,
    onAsked: () -> Unit,
    onExit: () -> Unit,
    viewModel: BookingFlowViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    BookingFlowScreen(
        state = state,
        onEvent = viewModel::onEvent,
        onExit = onExit,
        onFinished = onFinished,
        onAsked = onAsked,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BookingFlowScreen(
    state: BookingFlowUiState,
    onEvent: (BookingEvent) -> Unit,
    onExit: () -> Unit,
    onFinished: (String) -> Unit,
    onAsked: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current

    LaunchedEffect(state.askedRequestId) {
        if (state.askedRequestId != null) onAsked()
    }

    Scaffold(
        modifier = modifier,
        topBar = {
            TopAppBar(
                title = { Text(strings[state.step.titleKey()]) },
                navigationIcon = {
                    IconButton(
                        onClick = {
                            if (state.step == BookingFlowUiState.Step.ORIGIN_DISTRICT) onExit()
                            else onEvent(BookingEvent.Back)
                        }
                    ) {
                        // AutoMirrored: the arrow points the other way in RTL.
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = strings["common.action.back"],
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
            when {
                state.isLoading -> LoadingState()
                state.errorCode != null && state.isEmptyForStep() ->
                    ErrorState(
                        errorCode = state.errorCode!!,
                        context = state.errorContext,
                        onRetry = { onEvent(BookingEvent.Retry) },
                    )
                else -> {
                    if (state.errorCode != null) {
                        InlineError(state.errorCode!!, context = state.errorContext)
                    }
                    when (state.step) {
                        BookingFlowUiState.Step.ORIGIN_DISTRICT -> DistrictList(state, onEvent)
                        BookingFlowUiState.Step.ORIGIN_VILLAGE -> VillageList(state, onEvent)
                        BookingFlowUiState.Step.ORIGIN_STATION -> StationList(state, onEvent)
                        BookingFlowUiState.Step.DESTINATION -> DestinationList(state, onEvent)
                        BookingFlowUiState.Step.ASK -> AskFare(state, onEvent)
                        BookingFlowUiState.Step.RESULTS -> ResultList(state, onEvent)
                        BookingFlowUiState.Step.CONFIRMED ->
                            Confirmation(state, onFinished)
                    }
                }
            }
        }
    }
}

private fun BookingFlowUiState.Step.titleKey(): String = when (this) {
    BookingFlowUiState.Step.ORIGIN_DISTRICT -> "location.label.district"
    BookingFlowUiState.Step.ORIGIN_VILLAGE -> "location.label.village"
    BookingFlowUiState.Step.ORIGIN_STATION -> "location.label.station"
    BookingFlowUiState.Step.DESTINATION -> "home.question.to"
    BookingFlowUiState.Step.ASK -> "ride.ask.title"
    BookingFlowUiState.Step.RESULTS -> "home.action.search"
    BookingFlowUiState.Step.CONFIRMED -> "booking.title"
}

private fun BookingFlowUiState.isEmptyForStep(): Boolean = when (step) {
    BookingFlowUiState.Step.ORIGIN_DISTRICT -> districts.isEmpty()
    BookingFlowUiState.Step.ORIGIN_VILLAGE -> villages.isEmpty()
    BookingFlowUiState.Step.ORIGIN_STATION -> stations.isEmpty()
    BookingFlowUiState.Step.DESTINATION -> destinationGroups.isEmpty()
    BookingFlowUiState.Step.ASK -> false
    BookingFlowUiState.Step.RESULTS -> options.isEmpty()
    BookingFlowUiState.Step.CONFIRMED -> false
}

@Composable
private fun DistrictList(state: BookingFlowUiState, onEvent: (BookingEvent) -> Unit) {
    LazyColumn(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        items(state.districts, key = { it.id }) { district ->
            VelroCard(onClick = { onEvent(BookingEvent.DistrictChosen(district)) }) {
                Column {
                    Text(district.name, style = MaterialTheme.typography.bodyLarge)
                    if (district.alternativeName != null) {
                        Text(
                            district.alternativeName!!,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun VillageList(state: BookingFlowUiState, onEvent: (BookingEvent) -> Unit) {
    val strings = LocalVelroStrings.current
    if (state.villages.isEmpty()) {
        EmptyState(messageKey = "empty.search_results")
        return
    }

    var filter by rememberSaveable(state.villages.size) { mutableStateOf("") }
    val shown = remember(state.villages, filter) {
        state.villages.filter { it.matches(filter) }
    }

    Column {
        // Siahgird alone has 189 villages. Scrolling to find your own is not a
        // way to start a journey, and the filter matches however the name was
        // typed -- an Arabic yeh, a missing ZWNJ -- because the passenger did
        // not choose the spelling in the list.
        if (state.villages.size > FILTER_THRESHOLD) {
            OutlinedTextField(
                value = filter,
                onValueChange = { filter = it },
                label = { Text(strings["geo.action.filter_villages"]) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(bottom = Spacing.sm),
            )
        }

        if (shown.isEmpty()) {
            EmptyState(messageKey = "empty.search_results")
            return@Column
        }

        LazyColumn(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            items(shown, key = { it.id }) { village ->
                VelroCard(onClick = { onEvent(BookingEvent.VillageChosen(village)) }) {
                    Text(village.name, style = MaterialTheme.typography.bodyLarge)
                }
            }
        }
    }
}

/** Below this a list is quicker to read than to filter. */
private const val FILTER_THRESHOLD = 12

@Composable
private fun StationList(state: BookingFlowUiState, onEvent: (BookingEvent) -> Unit) {
    LazyColumn(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        items(state.stations, key = { it.id }) { station ->
            StationRow(station = station, onClick = { onEvent(BookingEvent.StationChosen(station)) })
        }
    }
}

/**
 * Destination choice.
 *
 * Section 16: internal destinations, then external, and Kabul expands into
 * Khair Khana Mina and Jada rather than appearing as a single vague option.
 */
@Composable
private fun DestinationList(state: BookingFlowUiState, onEvent: (BookingEvent) -> Unit) {
    val strings = LocalVelroStrings.current

    if (state.destinationGroups.isEmpty()) {
        EmptyState(messageKey = "empty.search_results")
        return
    }

    LazyColumn(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        items(state.destinationGroups, key = { it.id }) { group ->
            DestinationGroupRow(
                group = group,
                expanded = state.expandedGroupId == group.id,
                selectedId = state.selectedDestination?.id,
                onGroupClick = {
                    if (group.children.isEmpty()) {
                        onEvent(
                            BookingEvent.DestinationChosen(
                                Destination(group.id, group.code, group.name, group.kind)
                            )
                        )
                    } else {
                        onEvent(BookingEvent.GroupToggled(group.id))
                    }
                },
                onChildClick = { onEvent(BookingEvent.DestinationChosen(it)) },
            )
        }

        item {
            Spacer(Modifier.height(Spacing.lg))
            SeatCountPicker(state.seatCount) { onEvent(BookingEvent.SeatCountChanged(it)) }
            Spacer(Modifier.height(Spacing.lg))
            PrimaryAction(
                label = strings["home.action.search"],
                onClick = { onEvent(BookingEvent.Search) },
                enabled = state.canSearch,
            )
            Spacer(Modifier.height(Spacing.xl))
        }
    }
}

@Composable
private fun DestinationGroupRow(
    group: DestinationGroup,
    expanded: Boolean,
    selectedId: String?,
    onGroupClick: () -> Unit,
    onChildClick: (Destination) -> Unit,
) {
    Column {
        VelroCard(onClick = onGroupClick) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    group.name,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = if (selectedId == group.id) FontWeight.SemiBold
                    else FontWeight.Normal,
                )
                if (group.children.isNotEmpty()) {
                    Text(
                        if (expanded) "−" else "+",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
        }
        if (expanded) {
            Column(Modifier.padding(start = Spacing.xl, top = Spacing.xs)) {
                for (child in group.children) {
                    VelroCard(onClick = { onChildClick(child) }) {
                        Text(
                            child.name,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = if (selectedId == child.id) FontWeight.SemiBold
                            else FontWeight.Normal,
                        )
                    }
                    Spacer(Modifier.height(Spacing.xs))
                }
            }
        }
    }
}

/**
 * When the journey is for.
 *
 * Every ride request VELRO has ever made meant "a car, right now" -- not by
 * decision, but because the API dropped the departure time the database, the
 * use case and the trip were all built to carry. That made a marketplace for
 * arranging journeys into a hail-a-cab app, and the journeys this is for
 * (Ghorband to Charikar, Ghorband to Kabul) are arranged the evening before,
 * because the car leaves at six and nobody negotiates a fare at six.
 *
 * Days and hours as chips, not a date picker. A Hijri Shamsi calendar inside
 * an RTL dialog is the wrong instrument for "tomorrow morning", and this is
 * chosen at a roadside by somebody who may not read well: four taps, no
 * keyboard, nothing to type.
 */
@Composable
private fun DeparturePicker(state: BookingFlowUiState, onEvent: (BookingEvent) -> Unit) {
    val strings = LocalVelroStrings.current

    Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        Text(
            strings["ride.ask.when"],
            style = MaterialTheme.typography.bodyMedium,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            val days = listOf(
                null to "ride.when.now",
                0 to "ride.when.today",
                1 to "ride.when.tomorrow",
                2 to "ride.when.day_after",
            )
            for ((day, key) in days) {
                FilterChip(
                    selected = state.departureDay == day,
                    onClick = { onEvent(BookingEvent.DepartureChanged(day, state.departureHour)) },
                    label = { Text(strings[key]) },
                )
            }
        }

        // Only once a day is chosen. "Now" has no hour, and showing a row of
        // hours beside it would suggest otherwise.
        if (state.departureDay != null) {
            val hours = state.departureHours
            if (hours.isEmpty()) {
                // Today is spent. Say so rather than showing an empty row.
                Text(
                    strings["ride.when.tomorrow"],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                // Opened at the chosen hour rather than at the start of the
                // list. The return defaults to two in the afternoon, which is
                // ten chips along: the row showed 04:00 onwards with nothing
                // apparently selected, and a picker that hides your own choice
                // reads as a picker you have not used yet.
                LazyRow(
                    state = rememberLazyListState(
                        initialFirstVisibleItemIndex =
                            hours.indexOf(state.departureHour).coerceAtLeast(0)
                    ),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    items(hours, key = { it }) { hour ->
                        FilterChip(
                            selected = state.departureHour == hour,
                            onClick = {
                                onEvent(BookingEvent.DepartureChanged(state.departureDay, hour))
                            },
                            label = {
                                Text(
                                    Numerals.localise(
                                        "%02d:00".format(hour), strings.locale
                                    )
                                )
                            },
                        )
                    }
                }
            }

            // The way back, offered only once there is a day to count it from.
            //
            // Ghorband returns are usually not the same day: a car to Kabul
            // goes today and comes back tomorrow or later. That is why the
            // return belongs in this ask rather than in a second negotiation
            // afterwards -- one car, one driver, one price argued once. A
            // passenger who agrees only the outbound has to find a car again
            // from a town that is not theirs.
            Spacer(Modifier.height(Spacing.xs))
            Text(
                strings["ride.ask.return"],
                style = MaterialTheme.typography.bodyMedium,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                val backs = listOf(
                    null to strings["ride.return.none"],
                    0 to strings["ride.return.same_day"],
                    1 to strings["ride.return.next_day"],
                    2 to strings["ride.return.in_days", "days" to 2],
                    3 to strings["ride.return.in_days", "days" to 3],
                )
                for ((after, label) in backs) {
                    FilterChip(
                        selected = state.returnAfterDays == after,
                        onClick = {
                            onEvent(BookingEvent.ReturnChanged(after, state.returnHour))
                        },
                        label = { Text(label) },
                    )
                }
            }

            if (state.returnAfterDays != null) {
                LazyRow(
                    state = rememberLazyListState(
                        initialFirstVisibleItemIndex =
                            state.returnHours.indexOf(state.returnHour).coerceAtLeast(0)
                    ),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    items(state.returnHours, key = { it }) { hour ->
                        FilterChip(
                            selected = state.returnHour == hour,
                            onClick = {
                                onEvent(
                                    BookingEvent.ReturnChanged(state.returnAfterDays, hour)
                                )
                            },
                            label = {
                                Text(
                                    Numerals.localise("%02d:00".format(hour), strings.locale)
                                )
                            },
                        )
                    }
                }
                // The second price. Two legs are argued as two numbers at a
                // roadside -- so much to Kabul, so much back -- so the app
                // asks for two, and adds them up itself rather than leaving
                // the passenger to.
                OutlinedTextField(
                    value = state.returnFare,
                    onValueChange = { onEvent(BookingEvent.ReturnFareChanged(it)) },
                    label = { Text(strings["ride.ask.fare_back"]) },
                    suffix = { Text(strings["common.label.currency_afn"]) },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    textStyle = MaterialTheme.typography.headlineSmall,
                    modifier = Modifier.fillMaxWidth(),
                )
                state.totalFareMinor?.let { total ->
                    Text(
                        strings[
                            "ride.ask.fare_total",
                            "amount" to MoneyFormatter.format(
                                MoneyValue(total, DEFAULT_CURRENCY), strings
                            ),
                        ],
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                Text(
                    strings["ride.return.hint"],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun SeatCountPicker(selected: Int, onSelect: (Int) -> Unit) {
    val strings = LocalVelroStrings.current
    Column {
        Text(
            strings["home.question.passengers"],
            style = MaterialTheme.typography.labelLarge,
        )
        Spacer(Modifier.height(Spacing.sm))
        Row(horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            for (count in 1..4) {
                FilterChip(
                    selected = count == selected,
                    onClick = { onSelect(count) },
                    label = {
                        Text(Numerals.localise(count.toString(), strings.locale))
                    },
                )
            }
        }
    }
}

@Composable
private fun ResultList(state: BookingFlowUiState, onEvent: (BookingEvent) -> Unit) {
    if (state.options.isEmpty()) {
        EmptyState(
            messageKey = "empty.search_results",
            actionKey = "empty.action.search_again",
            onAction = { onEvent(BookingEvent.Retry) },
        )
        return
    }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        items(state.options, key = { it.tripId }) { option ->
            TripOptionCard(
                option = option,
                seatCount = state.seatCount,
                onClick = { if (!state.isSubmitting) onEvent(BookingEvent.TripChosen(option)) },
            )
        }
        item { Spacer(Modifier.height(Spacing.xl)) }
    }
}

/**
 * The confirmation.
 *
 * The boarding code is the largest thing here: it is what the passenger will
 * hold up to a driver at a roadside, possibly in bright sun.
 */
@Composable
private fun LabelledValue(label: String, value: String) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun Confirmation(state: BookingFlowUiState, onFinished: (String) -> Unit) {
    val strings = LocalVelroStrings.current
    val booking = state.confirmedBooking ?: return

    Column(
        Modifier.fillMaxSize().padding(top = Spacing.xl),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            strings["booking.status.confirmed"],
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.primary,
        )
        Spacer(Modifier.height(Spacing.xl))

        BoardingCode(booking.verificationCode.orEmpty())

        Spacer(Modifier.height(Spacing.xl))

        VelroCard {
            Column {
                LabelledValue(
                    strings["booking.label.number"],
                    booking.number,
                )
                Spacer(Modifier.height(Spacing.sm))
                LabelledValue(
                    strings["booking.label.seat"],
                    Numerals.localise(booking.seatNumbers.joinToString(", "), strings.locale),
                )
                Spacer(Modifier.height(Spacing.md))
                FareRow(strings["ride.label.fare"], booking.fareTotal, bold = true)
            }
        }

        Spacer(Modifier.height(Spacing.xl))

        PrimaryAction(
            label = strings["common.action.confirm"],
            onClick = { onFinished(booking.id) },
        )
    }
}


/**
 * Naming a price, section 89.
 *
 * There is no suggested fare and no "typical price" hint, because VELRO does
 * not know one. Offering a number the platform invented would anchor every
 * negotiation in Ghorband to a guess made in a database.
 */
@Composable
private fun AskFare(state: BookingFlowUiState, onEvent: (BookingEvent) -> Unit) {
    val strings = LocalVelroStrings.current

    // Scrolls, because this step is a form and forms grow.
    //
    // The frame around it does not scroll -- the other steps are lazy lists
    // that scroll themselves -- so for as long as this one happened to fit on
    // screen, nobody noticed. Adding the departure and return pickers pushed
    // "request a car" past the bottom edge with no way to reach it, which is
    // the whole screen's only action: the passenger could choose a fare, a
    // day, an hour and a return, and then could not ask for the car.
    Column(
        Modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .imePadding(),
        verticalArrangement = Arrangement.spacedBy(Spacing.md),
    ) {
        VelroCard {
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                Text(
                    strings[
                        "ride.journey.from_to",
                        "origin" to (state.selectedStation?.name ?: strings["common.value.unknown"]),
                        "destination" to (state.selectedDestination?.name ?: strings["common.value.unknown"]),
                    ],
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    strings["ride.ask.hint"],
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        OutlinedTextField(
            value = state.offeredFare,
            onValueChange = { onEvent(BookingEvent.FareChanged(it)) },
            // Named "fare there" once there is a way back to distinguish it
            // from, and "how much will you pay?" when there is not.
            label = {
                Text(
                    if (state.returnAfterDays != null) strings["ride.ask.fare_out"]
                    else strings["ride.ask.title"]
                )
            },
            suffix = { Text(strings["common.label.currency_afn"]) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            // The one number on the screen, so it is the one large control.
            textStyle = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.fillMaxWidth(),
        )

        // Passenger count sits with the price because it is what the price is
        // for: four people is a different journey from one.
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                strings["ride.ask.passengers"],
                style = MaterialTheme.typography.bodyMedium,
            )
            (1..4).forEach { count ->
                FilterChip(
                    selected = state.seatCount == count,
                    onClick = { onEvent(BookingEvent.SeatCountChanged(count)) },
                    label = { Text(Numerals.localise(count.toString(), strings.locale)) },
                )
            }
        }

        DeparturePicker(state, onEvent)

        OutlinedTextField(
            value = state.note,
            onValueChange = { onEvent(BookingEvent.NoteChanged(it)) },
            label = { Text(strings["ride.ask.note"]) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        PrimaryAction(
            label = strings["ride.ask.action"],
            onClick = { onEvent(BookingEvent.AskForRide) },
            enabled = state.canAsk,
            loading = state.isSubmitting,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}
