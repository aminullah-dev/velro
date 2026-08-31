package af.velro.core.ui.component

import af.velro.core.i18n.Calendars
import af.velro.core.i18n.MoneyFormatter
import af.velro.core.i18n.Numerals
import af.velro.core.ui.theme.LocalVelroDarkTheme
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import af.velro.core.ui.theme.VelroColors
import af.velro.domain.Booking
import af.velro.domain.BookingStatus
import af.velro.domain.DriverProfile
import af.velro.domain.MoneyValue
import af.velro.domain.RideKind
import af.velro.domain.Station
import af.velro.domain.TripOption
import af.velro.domain.TripStatus
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * Where the journey starts and where it ends.
 *
 * A dot, a line, a square -- the shape every transport product uses, because a
 * journey is two places and the space between them, and that reads without any
 * words at all. That matters more here than in Kabul or London: a passenger who
 * cannot read the station names can still see two ends and a line.
 *
 * VELRO already fetched both names, cached them in Room, mapped them into the
 * domain and then showed them to nobody -- the only reader was the emergency
 * help sheet. A booking card said "BKG-000014", "seat 3" and a fare, and never
 * said the trip went from Siahgird to Charikar.
 *
 * No map is involved, and deliberately so: the booking flow must work on a
 * handset that has never successfully loaded a tile. This is the whole visual
 * of a route, in two text rows and eight pixels of line.
 *
 * The rail sits at the start edge, so it moves to the right in Dari and Pashto
 * and to the left in English without a mirrored asset -- Row already resolves
 * start against the layout direction.
 */
@Composable
fun JourneyLine(
    origin: String?,
    destination: String?,
    modifier: Modifier = Modifier,
    style: androidx.compose.ui.text.TextStyle? = null,
) {
    val strings = LocalVelroStrings.current
    // Nothing to draw rather than a line between two blanks. A booking made
    // before the names were being sent still renders, just without this.
    if (origin.isNullOrBlank() && destination.isNullOrBlank()) return

    val text = style ?: MaterialTheme.typography.bodyLarge
    val faded = MaterialTheme.colorScheme.onSurfaceVariant

    Row(modifier = modifier.fillMaxWidth()) {
        // The rail. Fixed height per row so the dots line up with the first
        // line of each name even when a long name wraps.
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(end = Spacing.md),
        ) {
            Box(
                Modifier
                    .padding(top = Spacing.sm)
                    .size(RAIL_DOT)
                    .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(50)),
            )
            Box(
                Modifier
                    .padding(vertical = Spacing.xxs)
                    .size(width = RAIL_WIDTH, height = RAIL_GAP)
                    .background(MaterialTheme.colorScheme.outline),
            )
            // A square, not a second dot: the two ends of a journey are not
            // interchangeable, and shape distinguishes them for someone who
            // cannot rely on colour.
            Box(
                Modifier
                    .size(RAIL_DOT)
                    .background(MaterialTheme.colorScheme.secondary, RoundedCornerShape(Radius.sm / 4)),
            )
        }

        Column(Modifier.fillMaxWidth()) {
            Text(
                origin?.takeIf { it.isNotBlank() } ?: strings["location.label.origin"],
                style = text,
                color = if (origin.isNullOrBlank()) faded else MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.size(Spacing.sm))
            Text(
                destination?.takeIf { it.isNotBlank() } ?: strings["location.label.destination"],
                style = text,
                color = if (destination.isNullOrBlank()) faded else MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

private val RAIL_DOT = 10.dp
private val RAIL_WIDTH = 2.dp
private val RAIL_GAP = 18.dp

/** A station in a browse or search list. */
@Composable
fun StationRow(
    station: Station,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    VelroCard(modifier = modifier, onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                Icons.Filled.LocationOn,
                contentDescription = null,
                modifier = Modifier.size(Sizing.iconMd),
                tint = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.size(Spacing.md))
            Column(Modifier.weight(1f)) {
                Text(station.name, style = MaterialTheme.typography.bodyLarge)
                val subtitle = station.description
                    ?: station.distanceMetres?.let { distance ->
                        if (distance >= 1000) {
                            strings[
                                "location.distance.kilometres",
                                "distance" to (distance / 1000),
                            ]
                        } else {
                            strings["location.distance.metres", "distance" to distance]
                        }
                    }
                if (subtitle != null) {
                    Text(
                        subtitle,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

/**
 * One search result: a vehicle a passenger can actually take.
 *
 * Departure time, seats left and the fare are the three things that decide the
 * choice, so they are the three things shown. The fare always comes from the
 * server -- nothing here computes a price.
 */
@Composable
fun TripOptionCard(
    option: TripOption,
    seatCount: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    val locale = strings.locale

    VelroCard(modifier = modifier, onClick = onClick) {
        Column {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    Calendars.time(option.scheduledDepartureAt, locale),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.SemiBold,
                )
                RideKindChip(option.rideKind)
            }

            Spacer(Modifier.size(Spacing.sm))

            Text(
                Calendars.date(option.scheduledDepartureAt, locale),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.size(Spacing.md))

            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Bottom,
            ) {
                SeatAvailability(option.seatsAvailable, option.seatCapacity)
                if (option.fareTotal != null) {
                    Column(horizontalAlignment = Alignment.End) {
                        Text(
                            MoneyFormatter.format(option.fareTotal!!, strings),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        if (seatCount > 1 && option.farePerSeat != null) {
                            Text(
                                strings["ride.label.fare_per_seat"] + ": " +
                                    MoneyFormatter.format(option.farePerSeat!!, strings),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }
}

/**
 * How many seats are left.
 *
 * Turns amber below three, because "2 left" is what makes someone book now
 * rather than close the app and lose the seat.
 */
@Composable
fun SeatAvailability(available: Int, capacity: Int, modifier: Modifier = Modifier) {
    val strings = LocalVelroStrings.current
    val scarce = available in 1..2
    Text(
        strings["ride.label.seats_available", "count" to available, "capacity" to capacity],
        style = MaterialTheme.typography.bodyMedium,
        // The scheme's accent, not the light palette's. Amber600 is 3.55:1 on
        // the dark card -- below the 4.5:1 a sentence owes -- and this is the
        // one line written to make somebody book before the seat is gone.
        color = if (scarce) MaterialTheme.colorScheme.secondary
        else MaterialTheme.colorScheme.onSurfaceVariant,
        fontWeight = if (scarce) FontWeight.Medium else FontWeight.Normal,
        modifier = modifier,
    )
}

@Composable
fun RideKindChip(kind: RideKind, modifier: Modifier = Modifier) {
    val strings = LocalVelroStrings.current
    val key = when (kind) {
        RideKind.PRIVATE -> "ride.kind.private"
        RideKind.SHARED -> "ride.kind.shared"
    }
    Chip(text = strings[key], modifier = modifier)
}

/**
 * A status, rendered from its key.
 *
 * Colour alone never carries the meaning -- the word is always present, which
 * is both an accessibility requirement and a practical one in bright sun.
 */
@Composable
fun StatusChip(statusKey: String, tone: StatusTone, modifier: Modifier = Modifier) {
    val strings = LocalVelroStrings.current
    // One pair per tone per theme.
    //
    // These were five hardcoded light pairs, so after dark every status chip
    // was a near-white pill glowing off a dark card at 16:1 against it -- the
    // brightest thing on a screen a driver reads at night. Each dark pair is
    // measured against the dark card rather than picked to look right on a
    // laptop; ContrastTest holds all ten.
    val dark = LocalVelroDarkTheme.current
    val (background, foreground) = when (tone) {
        StatusTone.NEUTRAL ->
            if (dark) VelroColors.DarkSurfaceRaised to VelroColors.Neutral300
            else VelroColors.Neutral100 to VelroColors.Neutral700
        StatusTone.ACTIVE ->
            if (dark) VelroColors.DarkGreenContainer to VelroColors.Green200
            else VelroColors.Green50 to VelroColors.Green700
        StatusTone.ATTENTION ->
            if (dark) VelroColors.DarkAmberContainer to VelroColors.Amber200
            else VelroColors.Amber100 to VelroColors.Amber600
        StatusTone.ENDED ->
            if (dark) VelroColors.DarkSurfaceRaised to VelroColors.Neutral350
            else VelroColors.Neutral100 to VelroColors.Neutral500
        StatusTone.FAILED ->
            if (dark) VelroColors.DarkRedContainer to VelroColors.Red200
            else VelroColors.Red100 to VelroColors.Red700
    }
    Chip(strings[statusKey], background, foreground, modifier)
}

enum class StatusTone { NEUTRAL, ACTIVE, ATTENTION, ENDED, FAILED }

@Composable
private fun Chip(
    text: String,
    // Defaults follow the theme rather than the light palette: a plain Chip
    // (the ride-kind label) had the same near-white problem as the status ones.
    background: Color = MaterialTheme.colorScheme.surfaceVariant,
    foreground: Color = MaterialTheme.colorScheme.onSurfaceVariant,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier
            .background(background, RoundedCornerShape(Radius.pill))
            .padding(horizontal = Spacing.md, vertical = Spacing.xs)
    ) {
        Text(text, style = MaterialTheme.typography.labelSmall, color = foreground)
    }
}

fun BookingStatus.messageKey(): String = "booking.status." + name.lowercase()

fun BookingStatus.tone(): StatusTone = when (this) {
    BookingStatus.PENDING -> StatusTone.NEUTRAL
    BookingStatus.CONFIRMED, BookingStatus.DRIVER_ASSIGNED -> StatusTone.ACTIVE
    BookingStatus.READY, BookingStatus.ONBOARD -> StatusTone.ATTENTION
    BookingStatus.COMPLETED -> StatusTone.ENDED
    BookingStatus.CANCELLED, BookingStatus.NO_SHOW -> StatusTone.FAILED
}

fun TripStatus.messageKey(): String = "trip.status." + name.lowercase()

fun TripStatus.tone(): StatusTone = when (this) {
    TripStatus.SCHEDULED, TripStatus.REQUESTED -> StatusTone.NEUTRAL
    TripStatus.DRIVER_ASSIGNED, TripStatus.DRIVER_ARRIVING,
    TripStatus.ARRIVED_AT_PICKUP, TripStatus.BOARDING, TripStatus.IN_TRANSIT,
    TripStatus.ARRIVED -> StatusTone.ACTIVE
    TripStatus.COMPLETED -> StatusTone.ENDED
    TripStatus.CANCELLED, TripStatus.EXPIRED,
    TripStatus.NO_DRIVER_AVAILABLE -> StatusTone.FAILED
}

/** A booking in a list. The boarding code is the thing the passenger needs. */
@Composable
fun BookingCard(
    booking: Booking,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    VelroCard(modifier = modifier, onClick = onClick) {
        Column {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    // A booking number is quoted to an operator and typed into
                    // a search box. Localising its digits makes the passenger's
                    // copy differ from the one the office is looking at, so it
                    // stays Latin and LTR -- like a plate, for the same reason.
                    booking.number,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                StatusChip(booking.status.messageKey(), booking.status.tone())
            }

            Spacer(Modifier.size(Spacing.md))

            // The journey itself, above the reference number and the seat.
            // This card used to lead with "BKG-000014" -- the one thing on it
            // the passenger never chose and cannot use to recognise their own
            // trip in a list of four.
            JourneyLine(
                origin = booking.pickupStationName,
                destination = booking.dropoffDestinationName,
                style = MaterialTheme.typography.bodyMedium,
            )

            Spacer(Modifier.size(Spacing.md))

            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Column {
                    Text(
                        strings["booking.label.seat"] + " " +
                            Numerals.localise(
                                booking.seatNumbers.joinToString(", "), strings.locale
                            ),
                        style = MaterialTheme.typography.bodyLarge,
                    )
                    if (booking.createdAt != null) {
                        Text(
                            Calendars.date(booking.createdAt!!, strings.locale),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                Text(
                    MoneyFormatter.format(booking.fareTotal, strings),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
}

/**
 * The boarding code, shown large.
 *
 * A driver reads this across a vehicle in daylight, so it is the biggest thing
 * on the screen and always in Latin digits -- it is compared character by
 * character, and Eastern digits would invite a transcription mistake.
 */
@Composable
fun BoardingCode(code: String, modifier: Modifier = Modifier) {
    val strings = LocalVelroStrings.current
    Column(
        modifier = modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            strings["booking.label.code"],
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.size(Spacing.sm))
        Box(
            Modifier
                .background(
                    MaterialTheme.colorScheme.primaryContainer,
                    RoundedCornerShape(Radius.lg),
                )
                .padding(horizontal = Spacing.xl, vertical = Spacing.lg)
        ) {
            Text(
                code,
                style = MaterialTheme.typography.displaySmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onPrimaryContainer,
                letterSpacing = 8.dp.value.let { androidx.compose.ui.unit.TextUnit(
                    it, androidx.compose.ui.unit.TextUnitType.Sp
                ) },
            )
        }
        Spacer(Modifier.size(Spacing.sm))
        Text(
            strings["booking.hint.code"],
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/** The driver's own summary: vehicle, rating, and whether they may work. */
@Composable
fun DriverSummary(profile: DriverProfile, modifier: Modifier = Modifier) {
    val strings = LocalVelroStrings.current
    // The greeting used to open this card. It now opens the screen, inside the
    // brand header, which is where a greeting belongs -- and having it in both
    // places said the driver's name to him twice in the space of one screen.
    // What is left is the thing the card is actually for: the vehicle he is
    // signed in with, which is what a passenger will be looking for.
    VelroCard(modifier) {
        Column {
            val vehicle = profile.vehicle
            if (vehicle != null) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val description = listOfNotNull(vehicle.brand, vehicle.model)
                        .joinToString(" ")
                    if (description.isNotBlank()) {
                        Text(
                            description,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Spacer(Modifier.size(Spacing.sm))
                    }
                    // The plate, in its own box and never mirrored.
                    //
                    // It was concatenated into this Dari line with a bullet,
                    // which puts a Latin registration inside an RTL paragraph
                    // and lets bidi reorder its parts. A plate is matched
                    // against the metal on a car at a station; the one thing
                    // it may never do is read differently on screen than it
                    // does on the vehicle.
                    CompositionLocalProvider(
                        LocalLayoutDirection provides LayoutDirection.Ltr
                    ) {
                        Text(
                            vehicle.plateNumber,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier
                                .background(
                                    MaterialTheme.colorScheme.surfaceVariant,
                                    RoundedCornerShape(Radius.sm),
                                )
                                .padding(horizontal = Spacing.sm, vertical = Spacing.xxs),
                        )
                    }
                }
            }
            if (profile.ratingAverage != null) {
                Spacer(Modifier.size(Spacing.xs))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    // A vector, not the ★ character. That glyph renders as a
                    // different shape on every handset that lacks it, and on
                    // some it renders as nothing at all -- which would leave a
                    // bare number with no indication it is a rating.
                    Icon(
                        Icons.Filled.Star,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.secondary,
                        modifier = Modifier.size(Sizing.iconSm),
                    )
                    Spacer(Modifier.size(Spacing.xs))
                    Text(
                        Numerals.localise(
                            String.format("%.1f", profile.ratingAverage), strings.locale
                        ) + "  (" + Numerals.localise(
                            profile.ratingCount.toString(), strings.locale
                        ) + ")",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
fun FareRow(label: String, amount: MoneyValue, modifier: Modifier = Modifier, bold: Boolean = false) {
    val strings = LocalVelroStrings.current
    Row(
        modifier.fillMaxWidth().padding(vertical = Spacing.xs),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium,
            color = if (bold) MaterialTheme.colorScheme.onSurface
            else MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            MoneyFormatter.format(amount, strings),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = if (bold) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}
