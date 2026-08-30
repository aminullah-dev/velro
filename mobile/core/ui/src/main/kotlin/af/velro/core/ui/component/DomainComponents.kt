package af.velro.core.ui.component

import af.velro.core.i18n.Calendars
import af.velro.core.i18n.MoneyFormatter
import af.velro.core.i18n.Numerals
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
        color = if (scarce) VelroColors.Amber600 else MaterialTheme.colorScheme.onSurfaceVariant,
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
    val (background, foreground) = when (tone) {
        StatusTone.NEUTRAL -> VelroColors.Neutral100 to VelroColors.Neutral700
        StatusTone.ACTIVE -> VelroColors.Green50 to VelroColors.Green700
        StatusTone.ATTENTION -> VelroColors.Amber100 to VelroColors.Amber600
        StatusTone.ENDED -> VelroColors.Neutral100 to VelroColors.Neutral500
        StatusTone.FAILED -> VelroColors.Red100 to VelroColors.Red700
    }
    Chip(strings[statusKey], background, foreground, modifier)
}

enum class StatusTone { NEUTRAL, ACTIVE, ATTENTION, ENDED, FAILED }

@Composable
private fun Chip(
    text: String,
    background: Color = VelroColors.Neutral100,
    foreground: Color = VelroColors.Neutral700,
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
    VelroCard(modifier) {
        Column {
            // Substitution accepts "" happily, so the null name rendered as
            // "Hello, " -- a greeting with the person cut off the end.
            Text(
                if (profile.fullName != null)
                    strings["driver.greeting", "name" to profile.fullName]
                else strings["driver.greeting_no_name"],
                style = MaterialTheme.typography.titleMedium,
            )
            Spacer(Modifier.size(Spacing.sm))
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
