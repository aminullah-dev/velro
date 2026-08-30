package af.velro.data.repository

import af.velro.data.api.ApiResult
import af.velro.data.api.RegisterDriverRequest
import af.velro.data.api.ResponseMapper
import af.velro.data.api.VelroApi
import af.velro.domain.DocumentChecklist
import af.velro.domain.DriverDocument
import af.velro.domain.DocumentStatus
import af.velro.domain.VehicleChecklist
import af.velro.domain.VehicleDocument
import af.velro.domain.enumOrNull
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

@Singleton
class DocumentRepository @Inject constructor(
    private val api: VelroApi,
    private val mapper: ResponseMapper,
) {

    suspend fun registerAsDriver(
        homeDistrictId: String? = null,
        fullName: String? = null,
    ): ApiResult<Unit> =
        mapper.call {
            api.registerAsDriver(RegisterDriverRequest(homeDistrictId, fullName))
        }.map { }

    suspend fun checklist(): ApiResult<DocumentChecklist> =
        mapper.call { api.documents() }.map { dto ->
            DocumentChecklist(
                required = dto.required,
                missing = dto.missing,
                approvalStatus = dto.approval_status,
                canWork = dto.can_work,
                documents = dto.documents.map { d ->
                    DriverDocument(
                        id = d.id,
                        documentTypeCode = d.document_type_code,
                        status = enumOrNull<DocumentStatus>(d.status) ?: DocumentStatus.PENDING,
                        expiresOn = d.expires_on,
                        rejectionReason = d.rejection_reason,
                        uploadedAt = runCatching { Instant.parse(d.uploaded_at) }
                            .getOrDefault(Instant.EPOCH),
                        isCurrent = d.is_current,
                    )
                },
            )
        }

    /**
     * Send one photograph.
     *
     * The bytes are read by the caller from the picker, so this layer never
     * touches a content URI or a file path -- the only thing it knows is a byte
     * array and what kind of document it is.
     */
    suspend fun upload(
        documentTypeCode: String,
        bytes: ByteArray,
        mimeType: String,
    ): ApiResult<Unit> {
        val body = bytes.toRequestBody(mimeType.toMediaTypeOrNull())
        // The filename is cosmetic: the server generates the storage key and
        // never uses what the client sends.
        val part = MultipartBody.Part.createFormData(
            "file", "${documentTypeCode.lowercase()}.jpg", body
        )
        val kind = documentTypeCode.toRequestBody("text/plain".toMediaTypeOrNull())
        return mapper.call { api.uploadDocument(part, kind) }.map { }
    }

    // -- the car's own papers -------------------------------------------

    suspend fun vehicleChecklist(vehicleId: String): ApiResult<VehicleChecklist> =
        mapper.call { api.vehicleDocuments(vehicleId) }.map { dto ->
            VehicleChecklist(
                vehicleId = dto.vehicle_id,
                plateNumber = dto.plate_number,
                required = dto.required,
                missing = dto.missing,
                vehicleStatus = dto.vehicle_status,
                canCarry = dto.can_carry,
                documents = dto.documents.map { d ->
                    VehicleDocument(
                        id = d.id,
                        vehicleId = d.vehicle_id,
                        documentTypeCode = d.document_type_code,
                        status = enumOrNull<DocumentStatus>(d.status) ?: DocumentStatus.PENDING,
                        expiresOn = d.expires_on,
                        rejectionReason = d.rejection_reason,
                        uploadedAt = runCatching { Instant.parse(d.uploaded_at) }
                            .getOrDefault(Instant.EPOCH),
                        isCurrent = d.is_current,
                    )
                },
            )
        }

    suspend fun uploadForVehicle(
        vehicleId: String,
        documentTypeCode: String,
        bytes: ByteArray,
        mimeType: String,
    ): ApiResult<Unit> {
        val body = bytes.toRequestBody(mimeType.toMediaTypeOrNull())
        val part = MultipartBody.Part.createFormData(
            "file", "${documentTypeCode.lowercase()}.jpg", body
        )
        val kind = documentTypeCode.toRequestBody("text/plain".toMediaTypeOrNull())
        return mapper.call { api.uploadVehicleDocument(vehicleId, part, kind) }.map { }
    }
}
