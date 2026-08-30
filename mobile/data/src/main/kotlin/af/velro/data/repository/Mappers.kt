package af.velro.data.repository

import af.velro.data.api.BookingDto
import af.velro.data.api.DestinationDto
import af.velro.data.api.DestinationGroupDto
import af.velro.data.api.DistrictDto
import af.velro.data.api.DriverProfileDto
import af.velro.data.api.EarningsDto
import af.velro.data.api.FareComponentDto
import af.velro.data.api.MoneyDto
import af.velro.data.api.SessionDto
import af.velro.data.api.StationDto
import af.velro.data.api.TripOptionDto
import af.velro.data.api.TripSummaryDto
import af.velro.data.api.VehicleDto
import af.velro.data.api.VillageDto
import af.velro.data.db.BookingEntity
import af.velro.data.db.DestinationEntity
import af.velro.data.db.DistrictEntity
import af.velro.data.db.StationEntity
import af.velro.data.db.SyncState
import af.velro.data.db.TripEntity
import af.velro.data.db.VillageEntity
import af.velro.domain.Booking
import af.velro.domain.BookingStatus
import af.velro.domain.Destination
import af.velro.domain.DestinationGroup
import af.velro.domain.District
import af.velro.domain.DriverApprovalStatus
import af.velro.domain.DriverAvailability
import af.velro.domain.DriverProfile
import af.velro.domain.Earnings
import af.velro.domain.FareComponent
import af.velro.domain.MoneyValue
import af.velro.domain.PaymentMethod
import af.velro.domain.RideKind
import af.velro.domain.Session
import af.velro.domain.Station
import af.velro.domain.TripOption
import af.velro.domain.TripStatus
import af.velro.domain.TripSummary
import af.velro.domain.Vehicle
import af.velro.domain.VehicleStatus
import af.velro.domain.Village
import af.velro.domain.enumOrNull
import java.time.Instant
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

/**
 * Wire and storage shapes onto domain entities.
 *
 * Every unknown enum value falls back rather than throwing: a server that adds
 * a status must not crash an app that has not been updated, which in this
 * market may be most of them for a long time.
 */

fun MoneyDto.toDomain() = MoneyValue(amount_minor, currency)

private fun String?.toInstantOrNull(): Instant? =
    this?.let { runCatching { Instant.parse(it) }.getOrNull() }

// -- geography ----------------------------------------------------------

fun DistrictDto.toEntity() = DistrictEntity(
    id = id, code = code, name = name, alternativeName = alternative_name,
    provinceId = province_id,
    latitude = latitude, longitude = longitude,
)

fun DistrictEntity.toDomain() = District(
    id = id, code = code, name = name, alternativeName = alternativeName,
    latitude = latitude, longitude = longitude,
)

fun VillageDto.toEntity() = VillageEntity(
    id = id, code = code, name = name, districtId = district_id,
    // Newline-separated: no Afghan place name contains one, and Room has no
    // list type.
    alternativeNames = alternative_names.joinToString("\n"),
    latitude = latitude, longitude = longitude,
)

fun VillageEntity.toDomain() = Village(
    id = id, code = code, name = name, districtId = districtId,
    alternativeNames = alternativeNames.split("\n").filter { it.isNotBlank() },
    latitude = latitude, longitude = longitude,
)

fun VillageDto.toDomain() = Village(
    id = id, code = code, name = name, districtId = district_id,
    alternativeNames = alternative_names,
    latitude = latitude, longitude = longitude,
)

fun StationDto.toEntity() = StationEntity(
    id = id, code = code, name = name, villageId = village_id, districtId = district_id,
    isPrimary = is_primary, description = description,
    latitude = latitude, longitude = longitude,
)

fun StationDto.toDomain() = Station(
    id = id, code = code, name = name, villageId = village_id, districtId = district_id,
    isPrimary = is_primary, description = description,
    latitude = latitude, longitude = longitude,
    distanceMetres = distance_m,
)

fun StationEntity.toDomain() = Station(
    id = id, code = code, name = name, villageId = villageId, districtId = districtId,
    isPrimary = isPrimary, description = description,
    latitude = latitude, longitude = longitude,
)

fun DestinationDto.toEntity() = DestinationEntity(
    id = id, code = code, name = name, kind = kind, parentId = parent_id,
    districtId = district_id, stationId = station_id, sortOrder = sort_order,
)

fun DestinationDto.toDomain() = Destination(
    id = id, code = code, name = name, kind = kind,
    parentId = parent_id, sortOrder = sort_order,
)

fun DestinationEntity.toDomain() = Destination(
    id = id, code = code, name = name, kind = kind,
    parentId = parentId, sortOrder = sortOrder,
)

fun DestinationGroupDto.toDomain() = DestinationGroup(
    id = id, code = code, name = name, kind = kind,
    children = children.map { it.toDomain() },
)

// -- trips and bookings -------------------------------------------------

fun TripOptionDto.toDomain() = TripOption(
    tripId = trip_id,
    number = number,
    routeId = route_id,
    rideKind = enumOrNull<RideKind>(ride_kind) ?: RideKind.SHARED,
    scheduledDepartureAt = scheduled_departure_at.toInstantOrNull() ?: Instant.EPOCH,
    seatsAvailable = seats_available,
    seatCapacity = seat_capacity,
    fareTotal = fare_total?.toDomain(),
    farePerSeat = fare_per_seat?.toDomain(),
    status = enumOrNull<TripStatus>(status) ?: TripStatus.SCHEDULED,
    hasDriver = has_driver,
)

fun BookingDto.toDomain() = Booking(
    id = id,
    number = number,
    tripId = trip_id,
    status = enumOrNull<BookingStatus>(status) ?: BookingStatus.PENDING,
    rideKind = enumOrNull<RideKind>(ride_kind) ?: RideKind.SHARED,
    seatCount = seat_count,
    seatNumbers = seat_numbers,
    pickupStationId = pickup_station_id,
    dropoffDestinationId = dropoff_destination_id,
    fareTotal = fare_total.toDomain(),
    paymentMethod = enumOrNull<PaymentMethod>(payment_method) ?: PaymentMethod.CASH,
    verificationCode = verification_code,
    createdAt = created_at.toInstantOrNull(),
    fareBreakdown = fare_breakdown.map { it.toDomain() },
    pickupStationName = pickup_station_name,
    dropoffDestinationName = dropoff_destination_name,
    tripNumber = trip_number,
    scheduledDepartureAt = scheduled_departure_at.toInstantOrNull(),
    driverName = driver_name,
    vehiclePlate = vehicle_plate,
    vehicleDescription = vehicle_description,
    completedAt = completed_at.toInstantOrNull(),
    cancelledAt = cancelled_at.toInstantOrNull(),
    cancellationReasonCode = cancellation_reason_code,
    cancellationFee = cancellation_fee?.toDomain(),
)

fun FareComponentDto.toDomain() = FareComponent(
    key = key,
    amount = amount.toDomain(),
    quantity = quantity,
)

fun BookingDto.toEntity(syncState: String = SyncState.SYNCED) = BookingEntity(
    id = id,
    number = number,
    tripId = trip_id,
    status = status,
    rideKind = ride_kind,
    seatCount = seat_count,
    seatNumbers = seat_numbers.joinToString(","),
    pickupStationId = pickup_station_id,
    dropoffDestinationId = dropoff_destination_id,
    fareTotalMinor = fare_total.amount_minor,
    fareTotalCurrency = fare_total.currency,
    fareBreakdown = encodeBreakdown(fare_breakdown),
    pickupStationName = pickup_station_name,
    dropoffDestinationName = dropoff_destination_name,
    paymentMethod = payment_method,
    tripNumber = trip_number,
    scheduledDepartureAt = scheduled_departure_at.toInstantOrNull()?.toEpochMilli(),
    driverName = driver_name,
    vehiclePlate = vehicle_plate,
    vehicleDescription = vehicle_description,
    completedAt = completed_at.toInstantOrNull()?.toEpochMilli(),
    cancelledAt = cancelled_at.toInstantOrNull()?.toEpochMilli(),
    cancellationReasonCode = cancellation_reason_code,
    cancellationFeeMinor = cancellation_fee?.amount_minor,
    verificationCode = verification_code,
    createdAt = created_at.toInstantOrNull()?.toEpochMilli(),
    syncState = syncState,
)

private val breakdownJson = Json { ignoreUnknownKeys = true }

private fun encodeBreakdown(components: List<FareComponentDto>): String =
    runCatching {
        breakdownJson.encodeToString(ListSerializer(FareComponentDto.serializer()), components)
    }.getOrDefault("[]")

/**
 * A cached receipt that cannot be read is not an error worth surfacing: the
 * total is still right, and the screen already hides a breakdown that does not
 * account for it.
 */
private fun decodeBreakdown(raw: String, currency: String): List<FareComponent> =
    runCatching {
        breakdownJson.decodeFromString(ListSerializer(FareComponentDto.serializer()), raw).map {
            FareComponent(
                key = it.key,
                amount = MoneyValue(it.amount.amount_minor, it.amount.currency),
                quantity = it.quantity,
            )
        }
    }.getOrDefault(emptyList())

fun BookingEntity.toDomain() = Booking(
    id = id,
    number = number,
    tripId = tripId,
    status = enumOrNull<BookingStatus>(status) ?: BookingStatus.PENDING,
    rideKind = enumOrNull<RideKind>(rideKind) ?: RideKind.SHARED,
    seatCount = seatCount,
    seatNumbers = seatNumbers.split(",").mapNotNull(String::toIntOrNull),
    pickupStationId = pickupStationId,
    dropoffDestinationId = dropoffDestinationId,
    fareTotal = MoneyValue(fareTotalMinor, fareTotalCurrency),
    paymentMethod = enumOrNull<PaymentMethod>(paymentMethod) ?: PaymentMethod.CASH,
    verificationCode = verificationCode,
    createdAt = createdAt?.let(Instant::ofEpochMilli),
    fareBreakdown = decodeBreakdown(fareBreakdown, fareTotalCurrency),
    pickupStationName = pickupStationName,
    dropoffDestinationName = dropoffDestinationName,
    tripNumber = tripNumber,
    scheduledDepartureAt = scheduledDepartureAt?.let(Instant::ofEpochMilli),
    driverName = driverName,
    vehiclePlate = vehiclePlate,
    vehicleDescription = vehicleDescription,
    completedAt = completedAt?.let(Instant::ofEpochMilli),
    cancelledAt = cancelledAt?.let(Instant::ofEpochMilli),
    cancellationReasonCode = cancellationReasonCode,
    cancellationFee = cancellationFeeMinor?.let { MoneyValue(it, fareTotalCurrency) },
)

fun TripSummaryDto.toDomain() = TripSummary(
    id = id,
    number = number,
    status = enumOrNull<TripStatus>(status) ?: TripStatus.SCHEDULED,
    rideKind = enumOrNull<RideKind>(ride_kind) ?: RideKind.SHARED,
    scheduledDepartureAt = scheduled_departure_at.toInstantOrNull() ?: Instant.EPOCH,
    originStationId = origin_station_id,
    originStationName = origin_station_name,
    destinationId = destination_id,
    destinationName = destination_name,
    seatCapacity = seat_capacity,
    seatsAvailable = seats_available,
    driverId = driver_id,
    vehicleId = vehicle_id,
)

fun TripSummaryDto.toEntity(now: Long) = TripEntity(
    id = id, number = number, status = status, rideKind = ride_kind,
    scheduledDepartureAt = scheduled_departure_at.toInstantOrNull()?.toEpochMilli() ?: 0L,
    originStationId = origin_station_id, destinationId = destination_id,
    seatCapacity = seat_capacity, seatsAvailable = seats_available,
    driverId = driver_id, vehicleId = vehicle_id, updatedAt = now,
)

fun TripEntity.toDomain() = TripSummary(
    id = id,
    number = number,
    status = enumOrNull<TripStatus>(status) ?: TripStatus.SCHEDULED,
    rideKind = enumOrNull<RideKind>(rideKind) ?: RideKind.SHARED,
    scheduledDepartureAt = Instant.ofEpochMilli(scheduledDepartureAt),
    originStationId = originStationId,
    destinationId = destinationId,
    seatCapacity = seatCapacity,
    seatsAvailable = seatsAvailable,
    driverId = driverId,
    vehicleId = vehicleId,
)

// -- driver and identity ------------------------------------------------

fun VehicleDto.toDomain() = Vehicle(
    id = id, vehicleTypeCode = vehicle_type_code, plateNumber = plate_number,
    seatCapacity = seat_capacity, brand = brand, model = model, year = year,
    colour = colour, status = enumOrNull<VehicleStatus>(status) ?: VehicleStatus.PENDING,
)

fun DriverProfileDto.toDomain() = DriverProfile(
    id = id,
    userId = user_id,
    fullName = full_name,
    approvalStatus = enumOrNull<DriverApprovalStatus>(approval_status)
        ?: DriverApprovalStatus.PENDING,
    availability = enumOrNull<DriverAvailability>(availability) ?: DriverAvailability.OFFLINE,
    ratingAverage = rating_average,
    ratingCount = rating_count,
    completedTrips = completed_trips,
    vehicle = vehicle?.toDomain(),
    missingDocuments = missing_documents,
)

fun EarningsDto.toDomain() = Earnings(
    available = available.toDomain(),
    pending = pending.toDomain(),
    lifetimeEarned = lifetime_earned.toDomain(),
    lifetimeCommission = lifetime_commission.toDomain(),
    lifetimePaid = lifetime_paid?.toDomain() ?: MoneyValue(0, available.currency),
    completedTrips = completed_trips,
)

fun SessionDto.toDomain() = Session(
    userId = user_id,
    accessToken = access_token,
    refreshToken = refresh_token,
    roles = roles,
    isNewUser = is_new_user,
    expiresInSeconds = expires_in_seconds,
)
