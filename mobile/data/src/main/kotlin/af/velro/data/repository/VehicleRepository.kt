package af.velro.data.repository

import af.velro.data.api.ApiResult
import af.velro.data.api.RegisterVehicleRequest
import af.velro.data.api.ResponseMapper
import af.velro.data.api.VelroApi
import af.velro.domain.Vehicle
import af.velro.domain.VehicleType
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class VehicleRepository @Inject constructor(
    private val api: VelroApi,
    private val mapper: ResponseMapper,
) {

    /**
     * The types an operator has configured, section 105.
     *
     * Read from the server rather than an enum in the app: adding "Hiace" must
     * not require every driver to update the app before they can pick it.
     */
    suspend fun types(): ApiResult<List<VehicleType>> =
        mapper.call { api.vehicleTypes() }.map { list ->
            list.map { VehicleType(it.code, it.name_key, it.default_seat_capacity) }
        }

    suspend fun current(): ApiResult<Vehicle?> =
        mapper.call { api.currentVehicle() }.map { dto -> dto?.toDomain() }

    suspend fun register(
        vehicleTypeCode: String,
        plateNumber: String,
        seatCapacity: Int?,
        brand: String?,
        model: String?,
        year: Int?,
        colour: String?,
    ): ApiResult<Unit> =
        mapper.call {
            api.registerVehicle(
                RegisterVehicleRequest(
                    vehicle_type_code = vehicleTypeCode,
                    plate_number = plateNumber,
                    seat_capacity = seatCapacity,
                    // Blank is not the same as absent: an empty box means the
                    // driver left it alone, and sending "" would store one.
                    brand = brand?.trim()?.ifBlank { null },
                    model = model?.trim()?.ifBlank { null },
                    year = year,
                    colour = colour?.trim()?.ifBlank { null },
                )
            )
        }.map { }
}
