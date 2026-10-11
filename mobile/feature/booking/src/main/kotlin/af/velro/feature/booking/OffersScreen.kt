package af.velro.feature.booking

import af.velro.core.i18n.MoneyFormatter
import af.velro.core.i18n.Numerals
import af.velro.core.map.JourneyMap
import af.velro.core.ui.component.DrawnMap
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.GlassIconButton
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PhotoAvatar
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.SheetHandle
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.glassRim
import af.velro.core.ui.component.glassShadow
import af.velro.core.ui.component.softShadow
import af.velro.core.ui.theme.Elevation
import af.velro.core.ui.theme.LocalAnimationsEnabled
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import af.velro.core.ui.theme.VelroColors
import af.velro.domain.FareOffer
import af.velro.domain.MoneyValue
import af.velro.domain.RideRequest
import af.velro.domain.RideRequestStatus
import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.StarHalf
import androidx.compose.material.icons.filled.ArrowDownward
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.StarBorder
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun OffersRoute(
    onRideAgreed: (String) -> Unit,
    onFinished: () -> Unit,
    viewModel: OffersViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    // The moment a price is agreed the journey exists, so the passenger is
    // taken to it rather than left on a list of prices that no longer matter.
    LaunchedEffect(state.accepted) {
        state.accepted?.let { onRideAgreed(it.bookingId) }
    }
    // The same destination, reached the other way: a request read back as
    // MATCHED with a booking already on it. This is what a passenger whose
    // accept succeeded but whose response never arrived sees on the next
    // poll or the next time this screen opens -- her tap worked, the server
    // just never got to say so, and she must land on her booking exactly as
    // if the reply had come back the first time, not on a screen calling her
    // request cancelled.
    LaunchedEffect(state.request?.let { if (!it.isOpen) it.bookingId else null }) {
        state.request?.takeIf { !it.isOpen }?.bookingId?.let(onRideAgreed)
    }
    LaunchedEffect(state.cancelled) {
        if (state.cancelled) onFinished()
    }

    OffersScreen(state, viewModel::onEvent, onAskAgain = onFinished)
}

@Composable
fun OffersScreen(
    state: OffersUiState,
    onEvent: (OffersEvent) -> Unit,
    /** Back to where a ride is asked for. The way out of a closed request. */
    onAskAgain: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    val request = state.request

    if (state.isLoading && request == null) {
        LoadingState(modifier.fillMaxSize())
        return
    }
    if (request == null) {
        ErrorState(
            errorCode = state.errorCode ?: "RIDE_REQUEST_NOT_FOUND",
            context = state.errorContext,
            onRetry = { onEvent(OffersEvent.Refresh) },
            modifier = modifier.fillMaxSize(),
        )
        return
    }

    // Back leaves the request open on the server rather than cancelling it:
    // a passenger who glances at the home screen has not withdrawn her ask,
    // and drivers are still bidding on it. The gesture and the arrow are the
    // same door, as VelroScreen makes them everywhere else.
    BackHandler(onBack = onAskAgain)

    // A Surface for the theme's foreground as well as its ground: the sheet's
    // headings carry no colour of their own, and uncoloured text otherwise
    // falls back to black, which vanishes after dark.
    Surface(
        modifier = modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
        contentColor = MaterialTheme.colorScheme.onSurface,
    ) {
        BoxWithConstraints(Modifier.fillMaxSize()) {
            val mapHeight = maxHeight * MAP_SHARE
            val sheetShape = RoundedCornerShape(topStart = Radius.sheet, topEnd = Radius.sheet)

            // The road first, edge to edge, as inDrive and its kind open: the
            // journey she is pricing, drawn, so the prices below land on a place
            // rather than on a line of text. When the server cannot draw it the
            // space keeps a drawn street plan -- no route on it, since there is
            // no road to show -- rather than collapsing and moving every card.
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(mapHeight + Radius.sheet),
            ) {
                val drawn = state.journeyMap
                if (drawn != null) {
                    JourneyMap(
                        drawn,
                        modifier = Modifier.fillMaxSize(),
                        fullBleed = true,
                        bottomInset = Radius.sheet,
                    )
                } else {
                    DrawnMap(Modifier.fillMaxSize())
                }
            }

            // The sheet rides up over the map's lower edge, so it reads as lying
            // on it rather than starting after it.
            //
            // Solid, unlike home's glass sheet. Here the map stops where the sheet
            // begins, so glass would show a seam at the map's foot and the page
            // under the rest; and this is the screen where a fare is agreed, read
            // card by card. It keeps the glass family's rim and soft shadow.
            Column(
                Modifier
                    .padding(top = mapHeight)
                    .fillMaxSize()
                    .glassShadow(Radius.sheet, spread = 20.dp)
                    .background(MaterialTheme.colorScheme.surface, sheetShape)
                    .border(glassRim(), sheetShape)
                    .navigationBarsPadding(),
            ) {
                SheetHandle()
                Journey(request)

                if (state.errorCode != null) {
                    Box(Modifier.padding(horizontal = Spacing.gutter)) {
                        InlineError(state.errorCode!!, context = state.errorContext)
                    }
                }

                val offers = request.liveOffers
                // The status decides, not the emptiness of the list. The server closes
                // a stale request on this very read, so once the TTL passes the reply
                // is EXPIRED with no live offers -- and a screen branching on the list
                // alone draws a spinner over "waiting for drivers" forever, while the
                // view model stops polling because the request is no longer open. The
                // passenger is left watching an animation for something that already
                // finished without them.
                Box(Modifier.weight(1f).fillMaxWidth()) {
                    if (!request.isOpen && request.bookingId == null) {
                        Box(
                            Modifier.fillMaxSize().padding(horizontal = Spacing.gutter),
                            contentAlignment = Alignment.Center,
                        ) {
                            RequestClosed(status = request.status, onAskAgain = onAskAgain)
                        }
                    } else if (!request.isOpen) {
                        // Matched, with a booking already made: the accept succeeded,
                        // whether in this session or discovered on reopen. This must
                        // never fall into RequestClosed and read as "cancelled" -- the
                        // LaunchedEffect above is already carrying the passenger to her
                        // booking, and this is only ever on screen for the instant that
                        // takes.
                        LoadingState(Modifier.fillMaxSize())
                    } else if (offers.isEmpty()) {
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            Waiting()
                        }
                    } else {
                        // Worth pointing at only in a crowd: with one reply there is no
                        // "cheapest", and a badge on the only card is noise. The list is
                        // cheapest-first, so the best price is its head.
                        val bestId = if (offers.size > 1) offers.first().id else null
                        LazyColumn(
                            verticalArrangement = Arrangement.spacedBy(Spacing.md),
                            contentPadding = PaddingValues(
                                start = Spacing.gutter,
                                end = Spacing.gutter,
                                top = Spacing.sm,
                                bottom = Spacing.lg,
                            ),
                            modifier = Modifier.fillMaxSize(),
                        ) {
                            items(offers, key = { it.id }) { offer ->
                                OfferCard(
                                    // This list changes under the passenger's finger.
                                    //
                                    // Drivers bid while the screen is open, so a reply can
                                    // arrive in the moment somebody is reaching for
                                    // "accept" -- and without animation the row they aimed
                                    // at is simply somewhere else by the time the tap
                                    // lands. That is not a polish problem: it is agreeing
                                    // a fare with the wrong driver.
                                    //
                                    // The insert is animated so the shift is something the
                                    // eye can follow, and `key` above is what lets Compose
                                    // tell an inserted offer from a moved one.
                                    modifier = Modifier.animateItem(),
                                    offer = offer,
                                    best = offer.id == bestId,
                                    photo = state.driverPhotos[offer.driverId],
                                    // The whole journey, not the outbound leg: on a
                                    // round trip `offeredFare` is half the ask, and
                                    // every reply would look expensive against it.
                                    asking = request.askingTotal,
                                    accepting = state.acceptingOfferId == offer.id,
                                    // One action in flight at a time: two taps on a slow
                                    // connection must not agree two fares.
                                    enabled = state.acceptingOfferId == null,
                                    onAccept = { onEvent(OffersEvent.Accept(offer.id)) },
                                )
                            }
                        }
                    }
                }

                // Only while there is something to cancel.
                //
                // This rendered after every branch, so a passenger whose ask had
                // expired -- the common ending -- was shown "ask again" and "cancel
                // the request" together: two opposite exits from the same dead end,
                // and the one carrying the word she was looking for pointed at a
                // request the server had already closed.
                if (request.isOpen) {
                    SecondaryAction(
                        label = strings["ride.action.cancel"],
                        onClick = { onEvent(OffersEvent.Cancel) },
                        enabled = !state.isCancelling && state.acceptingOfferId == null,
                        modifier = Modifier.padding(
                            start = Spacing.gutter,
                            end = Spacing.gutter,
                            top = Spacing.sm,
                            bottom = Spacing.lg,
                        ),
                    )
                }
            }

            // The way back, floating over the map where the app bar used to be.
            GlassIconButton(
                // AutoMirrored: the arrow points the other way in Dari and Pashto.
                icon = Icons.AutoMirrored.Filled.ArrowBack,
                contentDescription = strings["common.action.back"],
                onClick = onAskAgain,
                modifier = Modifier
                    .statusBarsPadding()
                    .padding(Spacing.lg),
            )
        }
    }
}

/** The map's share of the screen above the sheet. */
private const val MAP_SHARE = 0.40f

/**
 * The head of the sheet: what this screen is, the journey, and the ask.
 *
 * The title the app bar used to carry stays, at the top of the sheet: a screen
 * with no name is one nobody can describe in a bug report, and "drivers who
 * answered" is what is about to appear under it.
 */
@Composable
private fun Journey(request: RideRequest) {
    val strings = LocalVelroStrings.current
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = Spacing.gutter, vertical = Spacing.sm),
        verticalArrangement = Arrangement.spacedBy(Spacing.xxs),
    ) {
        Text(
            strings["ride.offers.title"],
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(Spacing.xs))
        Text(
            strings[
                "ride.journey.from_to",
                "origin" to (request.originStationName ?: strings["common.value.unknown"]),
                "destination" to (request.destinationName ?: strings["common.value.unknown"]),
            ],
            style = MaterialTheme.typography.bodyLarge,
            fontWeight = FontWeight.SemiBold,
        )
        request.originPlaceName?.let { place ->
            Text(
                strings["ride.journey.from_place", "place" to place],
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.primary,
            )
        }
        Text(
            strings[
                "ride.offers.you_asked",
                // The whole journey. Showing the outbound leg here
                // told a passenger who had offered 300 out and 250
                // back that they had offered 300.
                "amount" to MoneyFormatter.format(request.askingTotal, strings),
            ],
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * Drivers are being shown this request now.
 *
 * A calm radar rather than a spinner: rings that widen and fade around a car,
 * slowly, because something really is coming and the wait is minutes, not a
 * second -- a spinner says "loading" and invites a tap on retry. An empty
 * state would say the opposite of the truth. With animation off the rings
 * stand still and say the same thing.
 */
@Composable
private fun Waiting() {
    val strings = LocalVelroStrings.current
    Column(
        Modifier.fillMaxWidth().padding(vertical = Spacing.lg),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        Radar(Modifier.size(RADAR))
        Text(
            strings["ride.offers.waiting"],
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun Radar(modifier: Modifier = Modifier) {
    val animate = LocalAnimationsEnabled.current
    val ring = MaterialTheme.colorScheme.primary
    // Read in the draw phase, so the rings redraw without recomposing.
    val sweep = if (animate) {
        rememberInfiniteTransition(label = "radar").animateFloat(
            initialValue = 0f,
            targetValue = 1f,
            animationSpec = infiniteRepeatable(
                tween(RADAR_PERIOD_MS, easing = LinearEasing),
                RepeatMode.Restart,
            ),
            label = "radar-sweep",
        )
    } else null

    Box(modifier, contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val outer = size.minDimension / 2f
            val t = sweep?.value ?: 0f
            for (i in 0 until RINGS) {
                // Moving: each ring is a third of a period behind the last.
                // Still: three rings at fixed widths, fading outward.
                val phase = if (sweep != null) (t + i / RINGS.toFloat()) % 1f
                else (i + 1) / (RINGS + 0.5f)
                val radius = outer * (0.32f + 0.68f * phase)
                val alpha = (1f - phase) * 0.45f
                drawCircle(ring.copy(alpha = alpha * 0.18f), radius = radius)
                drawCircle(ring.copy(alpha = alpha), radius = radius, style = Stroke(1.5.dp.toPx()))
            }
        }
        val disc = CircleShape
        Box(
            Modifier
                .size(RADAR_CORE)
                .softShadow(disc, Elevation.floating)
                .background(MaterialTheme.colorScheme.surface, disc),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                Icons.Filled.DirectionsCar,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(Sizing.iconLg),
            )
        }
    }
}

private val RADAR = 168.dp
private val RADAR_CORE = 72.dp
private const val RADAR_PERIOD_MS = 2400
private const val RINGS = 3

/**
 * One driver's answer.
 *
 * The price leads, at the top start, large: it is what is being chosen
 * between. Under it, how it compares with what she asked, so nobody has to
 * subtract at a roadside. His face sits large at the top end -- she is about
 * to get into his car on a road with nobody else on it -- with his name, his
 * stars and his trips under the price. Then the car to look for, his note, and
 * the one button.
 */
@Composable
private fun OfferCard(
    offer: FareOffer,
    /** Null while it loads, or when the server declined to show it. */
    photo: ByteArray?,
    asking: MoneyValue,
    accepting: Boolean,
    enabled: Boolean,
    onAccept: () -> Unit,
    modifier: Modifier = Modifier,
    /** The cheapest reply in a crowd: it wears the green edge and a badge. */
    best: Boolean = false,
) {
    val strings = LocalVelroStrings.current
    val agrees = offer.agreesWith(asking)
    val difference = offer.differenceFrom(asking)
    val primary = MaterialTheme.colorScheme.primary
    val cardShape = RoundedCornerShape(Radius.surface)

    Box(modifier.padding(top = if (best) BADGE_HEIGHT / 2 else 0.dp)) {
        VelroCard(
            modifier = if (best) Modifier.border(2.dp, primary, cardShape) else Modifier,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
                    Column(Modifier.weight(1f)) {
                        if (best) Spacer(Modifier.height(Spacing.xs))
                        Text(
                            MoneyFormatter.format(offer.total, strings),
                            style = MaterialTheme.typography.headlineMedium,
                            fontWeight = FontWeight.Bold,
                        )
                        // The two legs under the total, because the total is what
                        // is being chosen between and the split is what was
                        // argued. Only on a round trip: on a one-way journey the
                        // total is the only number there is.
                        offer.returnAmount?.let { back ->
                            Text(
                                strings["ride.offers.leg_out"] + " " +
                                    MoneyFormatter.format(offer.amount, strings) + "  ·  " +
                                    strings["ride.offers.leg_back"] + " " +
                                    MoneyFormatter.format(back, strings),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        // How it compares with what was asked, so nobody has to
                        // subtract one number from another at a roadside.
                        Text(
                            if (agrees) strings["ride.offers.same_as_asked"]
                            // Signed by the formatter, sign and digits in one
                            // isolate. Glued on in front, the "+" drifted to the
                            // far side of Eastern digits in a Dari line ("۵۰+"),
                            // and the "−" would have done the same.
                            else MoneyFormatter.format(difference, strings, showPlus = true),
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Medium,
                            color = if (agrees || difference.amountMinor < 0) primary
                            else MaterialTheme.colorScheme.onSurfaceVariant,
                        )

                        Spacer(Modifier.height(Spacing.md))
                        Text(
                            offer.driverName ?: strings["common.value.no_name"],
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                        )
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(Spacing.xs),
                        ) {
                            offer.driverRating?.let { rating ->
                                Stars(rating)
                                Text(
                                    Numerals.localise(rating.toString(), strings.locale),
                                    style = MaterialTheme.typography.labelMedium,
                                )
                            }
                            Text(
                                strings["ride.offers.trips", "count" to offer.driverTrips],
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    Spacer(Modifier.width(Spacing.md))
                    // The face, large.
                    //
                    // A passenger choosing between bids read a name, a number of
                    // stars and a fare. The driver had already sent a photograph
                    // and had it verified by the office, and she -- the person
                    // about to get into his car on a road with nobody else on it
                    // -- was the one person never shown it.
                    PhotoAvatar(
                        bytes = photo,
                        size = PHOTO,
                        shape = RoundedCornerShape(Radius.lg),
                    )
                }

                offer.vehiclePlate?.let { plate ->
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            Icons.Filled.DirectionsCar,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.size(Sizing.iconSm),
                        )
                        // Read off a physical car: never mirrored, never in
                        // Eastern digits.
                        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                            Text(
                                plate,
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier
                                    .clip(RoundedCornerShape(Radius.sm))
                                    .background(MaterialTheme.colorScheme.surfaceVariant)
                                    .padding(horizontal = Spacing.sm, vertical = Spacing.xxs),
                            )
                        }
                        offer.vehicleDescription?.let {
                            Text(
                                it,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }

                offer.note?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }

                Spacer(Modifier.height(Spacing.xs))
                PrimaryAction(
                    label = strings["ride.offers.accept"],
                    onClick = onAccept,
                    enabled = enabled,
                    loading = accepting,
                    // Comfortably above the 48dp Android minimum: this is the one
                    // tap on the screen that costs money.
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }

        // The cheapest reply, named. A ride app does not make her compare
        // numbers on a roadside: it points. The badge straddles the card's top
        // edge, in the brand field's constant green, so it reads as a tag on
        // the card rather than a line inside it.
        if (best) {
            Surface(
                shape = RoundedCornerShape(Radius.pill),
                color = VelroColors.BrandField,
                contentColor = VelroColors.OnBrandField,
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(start = Spacing.lg)
                    .height(BADGE_HEIGHT)
                    .offset(y = -BADGE_HEIGHT / 2),
            ) {
                Row(
                    Modifier.padding(horizontal = Spacing.md),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(Spacing.xs),
                ) {
                    Icon(
                        Icons.Filled.ArrowDownward,
                        contentDescription = null,
                        modifier = Modifier.size(Sizing.iconSm - 2.dp),
                    )
                    Text(
                        strings["ride.offers.best_price"],
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
    }
}

private val PHOTO = 64.dp
private val BADGE_HEIGHT = 26.dp

/**
 * Five small stars, filled to the rating.
 *
 * Decoration beside the number, which is what a screen reader reads: the
 * stars give the eye the shape of a rating at a glance, the figure gives the
 * value. Only drawn when there is a rating -- a new driver gets none, rather
 * than five empty stars that would read as a bad score.
 */
@Composable
private fun Stars(rating: Double) {
    Row {
        for (i in 0 until 5) {
            val icon = when {
                rating >= i + 1 -> Icons.Filled.Star
                rating >= i + 0.5 -> Icons.AutoMirrored.Filled.StarHalf
                else -> Icons.Filled.StarBorder
            }
            Icon(
                icon,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.secondary,
                modifier = Modifier.size(STAR),
            )
        }
    }
}

private val STAR = 14.dp

/**
 * The request ended without a ride.
 *
 * Expired, or cancelled from another device. Either way there is nothing left
 * to wait for, and the passenger needs a way back to asking rather than a
 * spinner and a dead end.
 */
@Composable
private fun RequestClosed(status: RideRequestStatus, onAskAgain: () -> Unit) {
    val strings = LocalVelroStrings.current
    val expired = status == RideRequestStatus.EXPIRED
    Column(
        Modifier.fillMaxWidth().padding(vertical = Spacing.xl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.md),
    ) {
        Text(
            strings[
                if (expired) "ride.offers.expired_title"
                else "ride.offers.cancelled_title"
            ],
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            strings[
                if (expired) "ride.offers.expired_body"
                else "ride.offers.cancelled_body"
            ],
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        PrimaryAction(
            label = strings["ride.offers.ask_again"],
            onClick = onAskAgain,
        )
    }
}
