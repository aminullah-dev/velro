package af.velro.data.repository

import kotlinx.serialization.json.JsonPrimitive
import af.velro.data.api.ApiResult
import af.velro.data.api.MarkReadRequest
import af.velro.data.api.ResponseMapper
import af.velro.data.api.VelroApi
import af.velro.domain.Notification
import af.velro.domain.NotificationInbox
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The inbox.
 *
 * VELRO has no push transport yet -- there are no Firebase credentials in this
 * repository and none to create. The backend already writes every notification
 * to the database first and treats delivery as an optimisation on top (ADR
 * 0005), which means the inbox alone is enough for a driver to learn that their
 * fare was accepted. Reading it is what closes the loop; a push, when there is
 * one, only makes it faster.
 */
@Singleton
class NotificationRepository @Inject constructor(
    private val api: VelroApi,
    private val mapper: ResponseMapper,
) {

    suspend fun inbox(limit: Int = 30): ApiResult<NotificationInbox> =
        mapper.call { api.notifications(limit) }.map { dto ->
            NotificationInbox(
                unread = dto.unread,
                notifications = dto.notifications.map { n ->
                    Notification(
                        id = n.id,
                        messageKey = n.message_key,
                        // A JsonPrimitive's `content` is the value without
                        // JSON quoting -- 32000 becomes "32000" and "AFN"
                        // stays "AFN". Anything structured keeps its JSON
                        // form rather than being dropped.
                        payload = n.payload.mapValues { (_, value) ->
                            (value as? JsonPrimitive)?.content ?: value.toString()
                        },
                        tripId = n.trip_id,
                        bookingId = n.booking_id,
                        createdAt = runCatching { Instant.parse(n.created_at) }
                            .getOrDefault(Instant.EPOCH),
                        readAt = n.read_at?.let {
                            runCatching { Instant.parse(it) }.getOrNull()
                        },
                    )
                },
            )
        }

    /**
     * Mark as read.
     *
     * An empty list marks everything, because the ordinary gesture is opening
     * the screen rather than dismissing one message at a time.
     */
    suspend fun markRead(ids: List<String> = emptyList()): ApiResult<Unit> =
        mapper.call { api.markNotificationsRead(MarkReadRequest(ids)) }.map { }
}
