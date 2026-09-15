import SwiftUI
import VelroCore

/// The payout queue, section 88 (admin/src/pages/Settlements.tsx), and the
/// drivers holding VELRO's share of cash fares.
///
/// Which way the money moves is the first thing read on every row -- never
/// left to the amount's sign. Every step is confirmed: marking paid cannot be
/// undone, and a refusal carries a reason the driver reads.
struct PayoutsView: View {
    @Environment(\.strings) private var strings

    init() {}

    var body: some View {
        PayoutsScreen()
    }
}

private enum PayoutsTab: Hashable {
    case queue, debtors
}

private struct PayoutsScreen: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @Environment(\.layoutDirection) private var direction
    @Environment(\.locale) private var locale
    @State private var model = PayoutsModel()
    @State private var tab = PayoutsTab.queue
    @State private var confirm: ConfirmRequest?
    @State private var collecting: Debtor?

    var body: some View {
        Group {
            if !ops.isFinance {
                EmptyStateView(messageKey: "error.permission_denied", systemImage: "lock")
            } else {
                content
            }
        }
        .background(Palette.background)
        .navigationTitle(strings["admin.nav.settlements"])
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                RefreshButton { [model, ops] in await model.load(ops) }
            }
        }
        .poll(every: .seconds(30)) { [model, ops] in
            await model.load(ops)
        }
        .confirmAction($confirm)
        .sheet(item: $collecting) { debtor in
            CollectSheet(debtor: debtor, model: model)
                .carryingOps(ops, strings: strings, direction: direction, locale: locale)
        }
    }

    private var content: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.s4) {
                if let notice = model.notice {
                    NoticeBanner(notice: notice)
                }
                summary
                Picker(strings["admin.nav.settlements"], selection: $tab) {
                    Text(title(for: .queue, count: model.queue.value?.count)).tag(PayoutsTab.queue)
                    Text(title(for: .debtors, count: model.debtors.value?.count)).tag(PayoutsTab.debtors)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                switch tab {
                case .queue: queueSection
                case .debtors: debtorsSection
                }
            }
            .padding(Spacing.s4)
            .frame(maxWidth: 1000, alignment: .leading)
            .frame(maxWidth: .infinity)
            .animation(.default, value: model.notice)
        }
        .refreshable { [model, ops] in await model.load(ops) }
    }

    private func title(for tab: PayoutsTab, count: Int?) -> String {
        let name = strings[tab == .queue ? "admin.settlements.queue" : "admin.settlements.debtors"]
        guard let count else { return name }
        return OpsJoin.counted(name, count, strings)
    }

    // MARK: The totals

    @ViewBuilder private var summary: some View {
        if let queue = model.queue.value {
            let currency = queue.first?.amount.currency ?? "AFN"
            let toPay = queue.filter { $0.direction == .payout }.reduce(Int64(0)) { $0 + $1.amount.amountMinor }
            let toCollect = queue.filter { $0.direction == .collection }.reduce(Int64(0)) { $0 + $1.amount.amountMinor }
            let owed = (model.debtors.value ?? []).reduce(Int64(0)) { $0 + $1.amountOwed.amountMinor }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 200), spacing: Spacing.s3)], spacing: Spacing.s3) {
                StatCard("admin.stat.settlements_open", count: queue.count, systemImage: "tray.full", attention: true)
                StatCard("ops.payouts.to_pay", money: Money(amountMinor: toPay, currency: currency), systemImage: "tray.and.arrow.up")
                StatCard(
                    "ops.payouts.to_collect", money: Money(amountMinor: toCollect, currency: currency),
                    systemImage: "tray.and.arrow.down"
                )
                StatCard(
                    "admin.stat.cash_owed", money: Money(amountMinor: owed, currency: currency),
                    systemImage: "banknote", attention: true
                ) { tab = .debtors }
            }
        }
    }

    // MARK: The queue

    private var queueSection: some View {
        LoadStateView(model.queue, retry: { [model, ops] in await model.load(ops) }) { queue in
            if queue.isEmpty {
                EmptyStateView(messageKey: "admin.settlements.none", systemImage: "checkmark.circle")
                    .frame(minHeight: 240)
            } else {
                LazyVStack(spacing: Spacing.s3) {
                    ForEach(queue) { settlement in
                        SettlementCard(settlement: settlement) { step in
                            confirm = request(step, for: settlement)
                        }
                    }
                }
            }
        }
    }

    private func request(_ step: SettlementStatus, for settlement: AdminSettlement) -> ConfirmRequest {
        let s = strings
        let who = settlement.driverName ?? s["common.value.no_name"]
        let summary = ["\u{2066}\(settlement.reference)\u{2069}", OpsFormat.money(settlement.amount, strings: s), who]
            .joined(separator: OpsJoin.separator(s))
        let isCollection = settlement.direction == .collection
        switch step {
        case .processing:
            return ConfirmRequest(
                title: s["admin.settlements.start"],
                message: summary + "\n\n" + s["ops.payouts.start_hint"],
                confirmTitle: s["admin.settlements.start"]
            ) { [model, ops] _ in
                await model.decide(settlement, to: .processing, reason: nil, ops: ops, strings: s)
            }
        case .paid:
            return ConfirmRequest(
                title: s["admin.settlements.mark_paid"],
                message: summary + "\n\n" + s[isCollection ? "ops.payouts.confirm_collected" : "ops.payouts.confirm_paid"],
                confirmTitle: s["admin.settlements.mark_paid"]
            ) { [model, ops] _ in
                await model.decide(settlement, to: .paid, reason: nil, ops: ops, strings: s)
            }
        case .rejected, .pending:
            return ConfirmRequest(
                title: s["admin.settlements.reject"],
                message: summary + "\n\n" + s[isCollection ? "ops.payouts.reject_collection_hint" : "ops.payouts.reject_payout_hint"],
                confirmTitle: s["admin.settlements.reject"],
                isDestructive: true,
                reason: .required,
                reasonPrompt: s["admin.settlements.reject_reason"]
            ) { [model, ops] reason in
                await model.decide(settlement, to: .rejected, reason: reason, ops: ops, strings: s)
            }
        }
    }

    // MARK: The drivers who owe

    private var debtorsSection: some View {
        LoadStateView(model.debtors, retry: { [model, ops] in await model.load(ops) }) { debtors in
            if debtors.isEmpty {
                EmptyStateView(messageKey: "admin.settlements.no_debtors", systemImage: "checkmark.circle")
                    .frame(minHeight: 240)
            } else {
                LazyVStack(spacing: Spacing.s3) {
                    ForEach(debtors) { debtor in
                        DebtorCard(debtor: debtor, open: model.openSettlement(for: debtor.driverId)) {
                            collecting = debtor
                        }
                    }
                }
            }
        }
    }
}

@MainActor
@Observable
final class PayoutsModel: NoticeShowing {
    private(set) var queue: LoadState<[AdminSettlement]> = .loading
    private(set) var debtors: LoadState<[Debtor]> = .loading
    var notice: OpsNotice?

    func load(_ ops: OpsModel) async {
        async let queueResult = ops.send(AdminAPI.settlements())
        async let debtorResult = ops.send(AdminAPI.debtors())
        let (settlements, owing) = await (queueResult, debtorResult)
        if case .failure(let error) = settlements, error == .cancelled { return }
        queue = LoadState(settlements, keeping: queue)
        if case .failure(let error) = owing, error == .cancelled { return }
        debtors = LoadState(owing, keeping: debtors)
    }

    /// The settlement already open for this driver: the server allows one at a time.
    func openSettlement(for driverId: String) -> AdminSettlement? {
        queue.value?.first { $0.driverId == driverId }
    }

    func decide(
        _ settlement: AdminSettlement, to target: SettlementStatus, reason: String?, ops: OpsModel, strings: Strings
    ) async -> APIError? {
        switch await ops.send(AdminAPI.decideSettlement(settlement.id, to: target, reason: reason)) {
        case .failure(let error):
            if error.code == "SETTLEMENT_INVALID_TRANSITION" { await load(ops) }
            return error
        case .success(let updated):
            show(OpsNotice(
                text: strings[updated.status.messageKey] + OpsJoin.separator(strings) + "\u{2066}\(updated.reference)\u{2069}"
            ))
            await load(ops)
            await ops.refreshAttention()
            return nil
        }
    }

    func collect(_ debtor: Debtor, amountMinor: Int64?, ops: OpsModel, strings: Strings) async -> APIError? {
        switch await ops.send(AdminAPI.collect(driverId: debtor.driverId, amountMinor: amountMinor)) {
        case .failure(let error):
            return error
        case .success(let settlement):
            show(OpsNotice(
                text: [
                    strings["admin.settlements.collect_from"],
                    OpsFormat.money(settlement.amount, strings: strings),
                    "\u{2066}\(settlement.reference)\u{2069}",
                ].joined(separator: OpsJoin.separator(strings))
            ))
            await load(ops)
            await ops.refreshAttention()
            return nil
        }
    }
}

/// Which way the money moves, in words and a picture, from VELRO's side.
struct DirectionLabel: View {
    let direction: SettlementDirection
    @Environment(\.strings) private var strings

    var body: some View {
        let collection = direction == .collection
        let colors = Palette.chip(collection ? .active : .attention)
        HStack(spacing: Spacing.s1) {
            Image(systemName: collection ? "tray.and.arrow.down.fill" : "tray.and.arrow.up.fill")
                .accessibilityHidden(true)
            Text(strings[collection ? "ops.payouts.direction.collection" : "ops.payouts.direction.payout"])
                .lineLimit(1)
        }
        .opsFont(.caption, weight: .medium)
        .padding(.horizontal, Spacing.s3)
        .padding(.vertical, 3)
        .foregroundStyle(colors.foreground)
        .background(colors.background, in: Capsule())
    }
}

struct SettlementCard: View {
    let settlement: AdminSettlement
    let act: (SettlementStatus) -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s3) {
            HStack(alignment: .top, spacing: Spacing.s3) {
                VStack(alignment: .leading, spacing: Spacing.s1) {
                    DirectionLabel(direction: settlement.direction)
                    Text(settlement.driverName ?? strings["common.value.no_name"])
                        .opsFont(.heading)
                        .foregroundStyle(Palette.text)
                    PhoneLink(settlement.driverPhone)
                        .opsFont(.caption)
                }
                Spacer(minLength: 0)
                VStack(alignment: .trailing, spacing: Spacing.s1) {
                    MoneyText(settlement.amount)
                        .opsFont(.title, weight: .bold)
                        .foregroundStyle(Palette.text)
                    StatusChip(settlement: settlement.status)
                }
            }
            .accessibilityElement(children: .combine)
            HStack(spacing: Spacing.s3) {
                HStack(spacing: Spacing.s1) {
                    Text(strings["admin.col.reference"])
                    LTRText(settlement.reference)
                        .textSelection(.enabled)
                }
                HStack(spacing: Spacing.s1) {
                    Text(strings["admin.col.period"])
                    DateText(settlement.periodStart)
                    Text("–")
                    DateText(settlement.periodEnd)
                }
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
            if let reason = settlement.rejectionReason, !reason.isEmpty {
                Text(reason)
                    .opsFont(.caption)
                    .foregroundStyle(Palette.danger)
            }
            let steps = settlement.nextSteps
            if !steps.isEmpty {
                HStack(spacing: Spacing.s2) {
                    ForEach(steps, id: \.self) { step in
                        stepButton(step)
                    }
                    Spacer(minLength: 0)
                }
                .opsFont(.label, weight: .medium)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opsCard()
    }

    @ViewBuilder private func stepButton(_ step: SettlementStatus) -> some View {
        switch step {
        case .processing:
            Button { act(step) } label: {
                Label(strings["admin.settlements.start"], systemImage: "play.circle")
            }
            .buttonStyle(.borderedProminent)
        case .paid:
            Button { act(step) } label: {
                Label(strings["admin.settlements.mark_paid"], systemImage: "checkmark.circle")
            }
            .buttonStyle(.borderedProminent)
        case .rejected:
            Button(role: .destructive) { act(step) } label: {
                Label(strings["admin.settlements.reject"], systemImage: "xmark.circle")
            }
            .buttonStyle(.bordered)
            .tint(Palette.danger)
        case .pending:
            EmptyView()
        }
    }
}

struct DebtorCard: View {
    let debtor: Debtor
    /// Already in the queue for him: another cannot be opened until it is settled.
    let open: AdminSettlement?
    let collect: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s3) {
            HStack(alignment: .top, spacing: Spacing.s3) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(debtor.driverName ?? strings["common.value.no_name"])
                        .opsFont(.heading)
                        .foregroundStyle(Palette.text)
                    // Every row here ends in a phone call.
                    PhoneLink(debtor.driverPhone)
                        .opsFont(.caption)
                    HStack(spacing: Spacing.s1) {
                        Text(strings["admin.col.trips"])
                        Text(OpsFormat.count(debtor.completedTrips, strings))
                    }
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
                }
                Spacer(minLength: 0)
                VStack(alignment: .trailing, spacing: 2) {
                    Text(strings["admin.settlements.owed"])
                        .opsFont(.caption)
                        .foregroundStyle(Palette.textMuted)
                    MoneyText(debtor.amountOwed)
                        .opsFont(.title, weight: .bold)
                        .foregroundStyle(Palette.attention)
                }
            }
            .accessibilityElement(children: .combine)
            if let open {
                Banner(
                    strings["ops.payouts.open_already", ["reference": "\u{2066}\(open.reference)\u{2069}"]],
                    tone: .info, systemImage: "hourglass"
                )
            }
            HStack {
                Spacer(minLength: 0)
                Button(action: collect) {
                    Label(strings["admin.settlements.collect"], systemImage: "banknote")
                }
                .buttonStyle(.borderedProminent)
                .disabled(open != nil)
            }
            .opsFont(.label, weight: .medium)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opsCard()
    }
}
