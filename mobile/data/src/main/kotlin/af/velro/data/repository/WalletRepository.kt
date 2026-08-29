package af.velro.data.repository

import af.velro.data.api.ApiResult
import af.velro.data.api.LedgerEntryDto
import af.velro.data.api.RequestSettlementRequest
import af.velro.data.api.ResponseMapper
import af.velro.data.api.SettlementDto
import af.velro.data.api.VelroApi
import af.velro.domain.LedgerEntry
import af.velro.domain.LedgerKind
import af.velro.domain.MoneyValue
import af.velro.domain.PayoutOptions
import af.velro.domain.Settlement
import af.velro.domain.SettlementDirection
import af.velro.domain.SettlementStatus
import af.velro.domain.enumOrNull
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The driver's money, section 88.
 *
 * Separate from DriverRepository because a wallet outlives any one trip: it is
 * read when the driver is offline, between shifts, and by someone checking last
 * month rather than today.
 */
@Singleton
class WalletRepository @Inject constructor(
    private val api: VelroApi,
    private val mapper: ResponseMapper,
) {

    data class LedgerPage(
        val entries: List<LedgerEntry>,
        val hasMore: Boolean,
        val nextOffset: Int,
    )

    suspend fun ledger(limit: Int = 30, offset: Int = 0): ApiResult<LedgerPage> =
        mapper.call { api.ledger(limit, offset) }.map { dto ->
            LedgerPage(
                entries = dto.entries.map(::toDomain),
                hasMore = dto.has_more,
                nextOffset = dto.next_offset,
            )
        }

    suspend fun payoutOptions(): ApiResult<PayoutOptions> =
        mapper.call { api.payoutOptions() }.map { dto ->
            PayoutOptions(
                minimum = MoneyValue(dto.minimum.amount_minor, dto.minimum.currency),
                canRequest = dto.can_request,
                direction = enumOrNull<SettlementDirection>(dto.direction)
                    ?: SettlementDirection.PAYOUT,
                amountOwed = dto.amount_owed
                    ?.let { MoneyValue(it.amount_minor, it.currency) }
                    ?: MoneyValue(0, dto.minimum.currency),
                amountWithdrawable = dto.amount_withdrawable
                    ?.let { MoneyValue(it.amount_minor, it.currency) }
                    ?: MoneyValue(0, dto.minimum.currency),
                openReference = dto.open_reference,
                history = dto.settlements.map(::toDomain),
            )
        }

    /** A null amount asks for the whole available balance. */
    suspend fun requestPayout(amountMinor: Long? = null): ApiResult<Settlement> =
        mapper.call { api.requestSettlement(RequestSettlementRequest(amountMinor)) }
            .map(::toDomain)

    private fun toDomain(dto: LedgerEntryDto) = LedgerEntry(
        id = dto.id,
        // An unrecognised kind still renders as a row with an amount: a driver
        // must never lose sight of money because the app is a version behind.
        kind = enumOrNull<LedgerKind>(dto.kind) ?: LedgerKind.UNKNOWN,
        amount = MoneyValue(dto.amount.amount_minor, dto.amount.currency),
        balanceAfter = MoneyValue(dto.balance_after.amount_minor, dto.balance_after.currency),
        createdAt = runCatching { Instant.parse(dto.created_at) }.getOrDefault(Instant.EPOCH),
        bookingId = dto.booking_id,
        tripId = dto.trip_id,
        settlementId = dto.settlement_id,
        note = dto.note,
    )

    private fun toDomain(dto: SettlementDto) = Settlement(
        id = dto.id,
        reference = dto.reference,
        amount = MoneyValue(dto.amount.amount_minor, dto.amount.currency),
        direction = enumOrNull<SettlementDirection>(dto.direction)
            ?: SettlementDirection.PAYOUT,
        status = enumOrNull<SettlementStatus>(dto.status) ?: SettlementStatus.PENDING,
        periodStart = dto.period_start,
        periodEnd = dto.period_end,
        paidAt = dto.paid_at?.let { runCatching { Instant.parse(it) }.getOrNull() },
        rejectionReason = dto.rejection_reason,
    )
}
