package af.velro.data.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * The server's response envelope.
 *
 * Every response has this shape, success or failure, so the client parses one
 * format. The error carries a stable code and a structured context, never a
 * rendered sentence: the phone resolves the code to a message in the locale the
 * person is actually reading.
 */
@Serializable
data class Envelope<T>(
    val success: Boolean = true,
    val data: T? = null,
    val message: String? = null,
    val meta: Map<String, JsonElement> = emptyMap(),
)

@Serializable
data class ErrorEnvelope(
    val success: Boolean = false,
    val error: ApiErrorBody,
)

@Serializable
data class ApiErrorBody(
    val code: String,
    @SerialName("message_key") val messageKey: String? = null,
    val context: Map<String, JsonElement> = emptyMap(),
    @SerialName("request_id") val requestId: String? = null,
)

/**
 * A failure the app can act on.
 *
 * [code] drives behaviour, [context] fills the translated sentence, and
 * [requestId] is what support asks for. The message itself is never carried
 * from the server.
 */
class ApiException(
    val code: String,
    val httpStatus: Int,
    val context: Map<String, Any?> = emptyMap(),
    val requestId: String? = null,
) : Exception("$code (HTTP $httpStatus)") {

    val isAuthFailure: Boolean
        get() = code in setOf("TOKEN_INVALID", "TOKEN_EXPIRED", "REFRESH_TOKEN_REVOKED")

    /** Worth retrying by itself; a conflict or a validation failure is not. */
    val isTransient: Boolean
        get() = httpStatus >= 500 || code == "RATE_LIMITED"

    companion object {
        const val OFFLINE = "NETWORK_OFFLINE"
        const val UNKNOWN = "INTERNAL_ERROR"

        fun offline() = ApiException(OFFLINE, httpStatus = 0)

        fun from(body: ErrorEnvelope, httpStatus: Int) = ApiException(
            code = body.error.code,
            httpStatus = httpStatus,
            context = body.error.context.mapValues { it.value.unwrap() },
            requestId = body.error.requestId,
        )
    }
}

private fun JsonElement.unwrap(): Any? = when (this) {
    is JsonNull -> null
    is JsonPrimitive -> if (isString) content else (content.toLongOrNull() ?: content)
    is JsonObject -> mapValues { it.value.unwrap() }
    else -> toString()
}

/**
 * The result of a call the UI can exhaustively handle.
 *
 * Deliberately not a bare exception: a screen must decide what to show for a
 * failure, and a sealed type makes forgetting one a compile error.
 */
sealed interface ApiResult<out T> {
    data class Success<T>(val value: T) : ApiResult<T>
    data class Failure(val error: ApiException) : ApiResult<Nothing>

    val successOrNull: T? get() = (this as? Success)?.value

    fun <R> map(transform: (T) -> R): ApiResult<R> = when (this) {
        is Success -> Success(transform(value))
        is Failure -> this
    }
}

inline fun <T> ApiResult<T>.onSuccess(block: (T) -> Unit): ApiResult<T> {
    if (this is ApiResult.Success) block(value)
    return this
}

inline fun <T> ApiResult<T>.onFailure(block: (ApiException) -> Unit): ApiResult<T> {
    if (this is ApiResult.Failure) block(error)
    return this
}
