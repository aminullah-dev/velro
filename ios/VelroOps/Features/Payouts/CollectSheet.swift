import SwiftUI
import VelroCore

/// Cash a driver handed in, against what he owes: all of it by default, or
/// part. The settlement it opens waits in the queue until someone marks it
/// paid, so a wrong entry can still be refused.
struct CollectSheet: View {
    let debtor: Debtor
    let model: PayoutsModel
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @Environment(\.dismiss) private var dismiss
    @State private var takeAll = true
    @State private var amountText = ""
    @State private var isWorking = false
    @State private var error: APIError?

    private var owedMinor: Int64 { debtor.amountOwed.amountMinor }
    private var parsed: Int64? { CollectAmount.minor(from: amountText) }

    private var problemKey: String? {
        guard !takeAll, !amountText.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
        guard let minor = parsed, minor > 0 else { return "admin.error.not_a_number" }
        return minor > owedMinor ? "ops.payouts.collect_too_much" : nil
    }

    private var canConfirm: Bool {
        guard !isWorking else { return false }
        if takeAll { return owedMinor > 0 }
        guard let minor = parsed else { return false }
        return minor > 0 && minor <= owedMinor
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.s4) {
                VStack(alignment: .leading, spacing: Spacing.s1) {
                    Text(strings["admin.settlements.collect_from"])
                        .opsFont(.title, weight: .bold)
                        .foregroundStyle(Palette.text)
                    Text(debtor.driverName ?? strings["common.value.no_name"])
                        .opsFont(.body)
                        .foregroundStyle(Palette.textMuted)
                    HStack(spacing: Spacing.s1) {
                        Text(strings["admin.settlements.owed"])
                        MoneyText(debtor.amountOwed)
                            .foregroundStyle(Palette.attention)
                    }
                    .opsFont(.body, weight: .medium)
                }
                Picker(strings["admin.col.amount"], selection: $takeAll) {
                    Text(strings["ops.payouts.collect_all", ["amount": OpsFormat.money(debtor.amountOwed, strings: strings)]])
                        .tag(true)
                    Text(strings["ops.payouts.collect_part"]).tag(false)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                if !takeAll {
                    VStack(alignment: .leading, spacing: Spacing.s1) {
                        Text(strings["admin.col.amount"])
                            .opsFont(.label)
                            .foregroundStyle(Palette.text)
                        HStack(spacing: Spacing.s2) {
                            TextField(strings["admin.col.amount"], text: $amountText)
                                .textFieldStyle(.roundedBorder)
                                .opsFont(.body)
                                .environment(\.layoutDirection, .leftToRight)
                                #if os(iOS)
                                .keyboardType(.decimalPad)
                                #endif
                            Text(strings["common.label.currency_afn"])
                                .opsFont(.body)
                                .foregroundStyle(Palette.textMuted)
                        }
                        if let problemKey {
                            Text(strings[problemKey])
                                .opsFont(.caption)
                                .foregroundStyle(Palette.danger)
                        }
                    }
                }
                Text(strings["ops.payouts.collect_hint"])
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
                if let error {
                    Banner(strings.forErrorCode(error.code, context: error.context.arguments), tone: .error)
                }
                SheetButtons(
                    confirmTitle: strings["admin.settlements.collect"], isDestructive: false,
                    isWorking: isWorking, canConfirm: canConfirm
                ) {
                    Task { await submit() }
                }
            }
            .padding(Spacing.s6)
        }
        .frame(minWidth: 380, idealWidth: 480, maxWidth: 560)
        .presentationDetents([.medium, .large])
        .interactiveDismissDisabled(isWorking)
    }

    private func submit() async {
        isWorking = true
        error = nil
        let failure = await model.collect(debtor, amountMinor: takeAll ? nil : parsed, ops: ops, strings: strings)
        isWorking = false
        if let failure {
            if failure != .cancelled { error = failure }
        } else {
            dismiss()
        }
    }
}

/// An amount in afghani as typed -- Latin or Eastern digits, "٫" or "." for
/// the decimal point, at most two decimals -- in minor units. No floating
/// point: 12.10 is 1210, never 1209.
enum CollectAmount {
    static func minor(from text: String) -> Int64? {
        let plain = Numerals.latin(text)
            .replacingOccurrences(of: "٫", with: ".")
            .replacingOccurrences(of: "٬", with: "")
            .replacingOccurrences(of: ",", with: "")
            .trimmingCharacters(in: .whitespaces)
        let parts = plain.split(separator: ".", maxSplits: 1, omittingEmptySubsequences: false).map(String.init)
        let whole = parts.first ?? ""
        let fraction = parts.count > 1 ? parts[1] : ""
        let digitsOnly: (String) -> Bool = { $0.allSatisfy { $0.isASCII && $0.isNumber } }
        guard
            !(whole.isEmpty && fraction.isEmpty),
            digitsOnly(whole), digitsOnly(fraction),
            fraction.count <= 2, whole.count <= 12
        else { return nil }
        let wholeValue = Int64(whole.isEmpty ? "0" : whole) ?? 0
        let fractionValue = Int64(String((fraction + "00").prefix(2))) ?? 0
        return wholeValue * 100 + fractionValue
    }
}
