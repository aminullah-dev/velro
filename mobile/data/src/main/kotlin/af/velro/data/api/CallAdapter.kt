package af.velro.data.api

import java.io.IOException
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import retrofit2.Response

/**
 * Turns a Retrofit [Response] into an [ApiResult].
 *
 * Three failure modes, distinguished because the UI treats them differently: no
 * network at all (offer a retry, show cached data), a structured server error
 * (translate the code), and something unrecognisable (a general message plus
 * the request id).
 */
class ResponseMapper(private val json: Json) {

    suspend fun <T> call(block: suspend () -> Response<Envelope<T>>): ApiResult<T> =
        try {
            unwrap(block())
        } catch (e: IOException) {
            // No connectivity, DNS failure, timeout. Not a server error, and the
            // screen should say so in those words.
            ApiResult.Failure(ApiException.offline())
        } catch (e: SerializationException) {
            // The server answered and we could not read it: a contract
            // mismatch, not a network problem. Reporting this as "offline"
            // sends both the user and whoever debugs it in the wrong direction.
            ApiResult.Failure(
                ApiException(
                    code = ApiException.UNKNOWN,
                    httpStatus = 0,
                    context = mapOf("reason" to "response_unreadable"),
                )
            )
        } catch (e: Exception) {
            ApiResult.Failure(ApiException(ApiException.UNKNOWN, httpStatus = 0))
        }

    fun <T> unwrap(response: Response<Envelope<T>>): ApiResult<T> {
        if (response.isSuccessful) {
            val body = response.body()
            val value = body?.data
            return if (value != null) {
                ApiResult.Success(value)
            } else {
                // A 2xx with no payload where one was expected. Better to fail
                // loudly than to hand a screen a null it will crash on.
                ApiResult.Failure(
                    ApiException(ApiException.UNKNOWN, httpStatus = response.code())
                )
            }
        }
        return ApiResult.Failure(parseError(response))
    }

    fun parseError(response: Response<*>): ApiException {
        val raw = runCatching { response.errorBody()?.string() }.getOrNull()
        if (raw.isNullOrBlank()) {
            return ApiException(ApiException.UNKNOWN, httpStatus = response.code())
        }
        return runCatching {
            ApiException.from(json.decodeFromString<ErrorEnvelope>(raw), response.code())
        }.getOrElse {
            ApiException(ApiException.UNKNOWN, httpStatus = response.code())
        }
    }
}
