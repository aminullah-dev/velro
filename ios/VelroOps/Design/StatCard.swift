import SwiftUI
import VelroCore

/// A figure with its label: the dashboard's cards (the panel's Stat,
/// ActionStat and MoneyStat).
///
/// `attention` marks a number that asks somebody to act: when it is not zero
/// it turns amber and the card gets a thick start edge, so the state survives
/// a colour-blind reading. Zero reads quiet. With an `action` the card is a
/// button that opens the list the number was counted from.
///
///     StatCard("admin.stat.overdue", count: a.overdueTrips, noteKey: "admin.stat.overdue_hint",
///              attention: true) { navigator.open(.trips, filter: "overdue") }
///     StatCard("admin.stat.cash_owed", money: finance.cashOwed)
///     StatCard("admin.stat.utilisation", percent: today.utilisationPercent)
///         .note(OpsFormat.fraction(booked, of: seats, strings))
struct StatCard: View {
    enum Value {
        case count(Int)
        case money(Money)
        case percent(Int?)
        case text(String)
    }

    @Environment(\.strings) private var strings
    @Environment(\.statCardFillsRow) private var fillsRow
    private let labelKey: String
    private let value: Value
    private let noteKey: String?
    private var noteText: String?
    private let systemImage: String?
    private let attention: Bool
    private let action: (() -> Void)?

    init(_ labelKey: String, count: Int, noteKey: String? = nil, systemImage: String? = nil,
         attention: Bool = false, action: (() -> Void)? = nil) {
        self.init(labelKey, value: .count(count), noteKey: noteKey, systemImage: systemImage, attention: attention, action: action)
    }

    init(_ labelKey: String, money: Money, noteKey: String? = nil, systemImage: String? = nil,
         attention: Bool = false, action: (() -> Void)? = nil) {
        self.init(labelKey, value: .money(money), noteKey: noteKey, systemImage: systemImage, attention: attention, action: action)
    }

    init(_ labelKey: String, percent: Int?, noteKey: String? = nil, systemImage: String? = nil,
         action: (() -> Void)? = nil) {
        self.init(labelKey, value: .percent(percent), noteKey: noteKey, systemImage: systemImage, attention: false, action: action)
    }

    /// A value already written -- a time, a version, a name.
    init(_ labelKey: String, text: String, noteKey: String? = nil, systemImage: String? = nil,
         action: (() -> Void)? = nil) {
        self.init(labelKey, value: .text(text), noteKey: noteKey, systemImage: systemImage, attention: false, action: action)
    }

    init(_ labelKey: String, value: Value, noteKey: String?, systemImage: String?,
         attention: Bool, action: (() -> Void)?) {
        self.labelKey = labelKey
        self.value = value
        self.noteKey = noteKey
        self.systemImage = systemImage
        self.attention = attention
        self.action = action
    }

    /// A note already written -- "۱۲ از ۲۰ چوکی" -- where a key alone cannot
    /// say it. Shown under the key's note when both are given.
    func note(_ text: String?) -> StatCard {
        var card = self
        card.noteText = text
        return card
    }

    private var isZero: Bool {
        switch value {
        case .count(let count): count == 0
        case .money(let money): money.amountMinor == 0
        case .percent(let percent): percent == nil || percent == 0
        case .text: false
        }
    }

    private var needsYou: Bool { attention && !isZero }

    private var formatted: String {
        switch value {
        case .count(let count): OpsFormat.count(count, strings)
        case .money(let money): OpsFormat.money(money, strings: strings)
        case .percent(let percent): OpsFormat.percent(percent, strings)
        case .text(let text): text
        }
    }

    private var isMoney: Bool {
        if case .money = value { true } else { false }
    }

    var body: some View {
        if let action {
            Button(action: action) { card }
                .buttonStyle(.plain)
        } else {
            card
        }
    }

    private var card: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s1) {
                if let systemImage { Image(systemName: systemImage) }
                Text(strings[labelKey])
                    .lineLimit(2)
            }
            .opsFont(.label, weight: .regular)
            .foregroundStyle(Palette.textMuted)

            Text(formatted)
                .opsFont(isMoney ? .title : .display, weight: isZero ? .medium : .bold)
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.6)
                .foregroundStyle(needsYou ? Palette.attention : isZero ? Palette.textMuted : Palette.text)

            if let noteKey {
                Text(strings[noteKey])
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
            if let noteText {
                Text(noteText)
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
            if action != nil {
                if fillsRow { Spacer(minLength: 0) }
                Text(strings["admin.ops.open"])
                    .opsFont(.caption, weight: .medium)
                    .foregroundStyle(Palette.accent)
                    .padding(.top, Spacing.s1)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: fillsRow ? .infinity : nil, alignment: .topLeading)
        .padding(Spacing.s4)
        .background(Palette.surface)
        .overlay(alignment: .leading) {
            if needsYou {
                Rectangle().fill(Palette.attentionEdge).frame(width: 4)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: Radius.lg, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: Radius.lg, style: .continuous)
                .strokeBorder(needsYou ? Palette.attentionEdge : Palette.border, lineWidth: 1)
        }
        .contentShape(RoundedRectangle(cornerRadius: Radius.lg, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

extension EnvironmentValues {
    /// Cards grow to the tallest in their row. Only a grid that sizes its
    /// rows sets it: in a plain stack a card would take the whole height.
    @Entry var statCardFillsRow = false
}
