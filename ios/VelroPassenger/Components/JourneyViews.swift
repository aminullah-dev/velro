import SwiftUI
import VelroCore

/// A status, as a word on a tinted pill. The word is always there: colour
/// alone never carries the meaning, in sunlight least of all.
struct StatusChip: View {
    let key: String
    let tone: StatusTone
    @Environment(\.strings) private var strings

    var body: some View {
        Text(strings[key])
            .velroFont(.caption)
            .padding(.horizontal, Spacing.md)
            .padding(.vertical, Spacing.xs)
            .foregroundStyle(foreground)
            .background(background, in: Capsule())
    }

    private var background: Color {
        switch tone {
        case .neutral: Palette.toneNeutral
        case .active: Palette.toneActive
        case .attention: Palette.toneAttention
        case .ended: Palette.toneNeutral
        case .failed: Palette.toneFailed
        }
    }

    private var foreground: Color {
        switch tone {
        case .neutral: Palette.onToneNeutral
        case .active: Palette.onToneActive
        case .attention: Palette.onToneAttention
        case .ended: Palette.onToneEnded
        case .failed: Palette.onToneFailed
        }
    }
}

/// Where the journey starts and where it ends: a dot, a line, a square.
///
/// The shape every transport product uses, because it reads without words --
/// which matters to a passenger who cannot read the station names. The two
/// ends are different shapes so they are told apart without colour. The rail
/// sits at the leading edge, so it moves sides with the language.
struct JourneyLine: View {
    let origin: String?
    let destination: String?
    var role: TextRole = .body
    @Environment(\.strings) private var strings

    var body: some View {
        if (origin ?? "").isEmpty && (destination ?? "").isEmpty {
            EmptyView()
        } else {
            HStack(alignment: .top, spacing: Spacing.md) {
                VStack(spacing: Spacing.xxs) {
                    Circle().fill(Palette.primary).frame(width: 10, height: 10)
                    Rectangle().fill(Palette.outline).frame(width: 2, height: 18)
                    RoundedRectangle(cornerRadius: 2).fill(Palette.accent).frame(width: 10, height: 10)
                }
                .padding(.top, 6)
                .accessibilityHidden(true)

                VStack(alignment: .leading, spacing: Spacing.sm) {
                    end(origin, fallback: "location.label.origin")
                    end(destination, fallback: "location.label.destination")
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
        }
    }

    private func end(_ name: String?, fallback: String) -> some View {
        let known = !(name ?? "").isEmpty
        return Text(known ? name! : strings[fallback])
            .velroFont(role)
            .foregroundStyle(known ? Palette.onSurface : Palette.onSurfaceVariant)
    }
}

/// A booking in a list: the journey first, then the seat, the day and the fare.
///
/// The number stays in Latin digits and left to right: it is quoted to an
/// operator and typed into a search box, and must match the office's copy.
struct BookingCard: View {
    let booking: Booking
    @Environment(\.strings) private var strings

    var body: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.md) {
                HStack {
                    Text(booking.number)
                        .velroFont(.label)
                        .foregroundStyle(Palette.onSurfaceVariant)
                        .environment(\.layoutDirection, .leftToRight)
                    Spacer()
                    StatusChip(key: booking.status.messageKey, tone: booking.status.tone)
                }

                JourneyLine(origin: booking.pickupStationName, destination: booking.dropoffDestinationName, role: .label)

                HStack(alignment: .bottom) {
                    VStack(alignment: .leading, spacing: Spacing.xxs) {
                        Text(strings["booking.label.seat"] + " "
                             + Numerals.localise(booking.seatNumbers.map(String.init).joined(separator: ", "), strings.locale))
                            .velroFont(.body)
                            .foregroundStyle(Palette.onSurface)
                        if let when = booking.departure ?? booking.created {
                            Text(Calendars.date(when, strings.locale))
                                .velroFont(.caption)
                                .foregroundStyle(Palette.onSurfaceVariant)
                        }
                    }
                    Spacer()
                    Text(MoneyFormatter.format(booking.fareTotal, strings: strings))
                        .velroFont(.heading, weight: .medium)
                        .foregroundStyle(Palette.onSurface)
                }
            }
        }
    }
}

/// A money line on a receipt.
struct FareRow: View {
    let label: String
    let amount: Money
    var bold = false
    @Environment(\.strings) private var strings

    var body: some View {
        HStack {
            Text(label)
                .velroFont(.label)
                .foregroundStyle(bold ? Palette.onSurface : Palette.onSurfaceVariant)
            Spacer()
            Text(MoneyFormatter.format(amount, strings: strings))
                .velroFont(.label, weight: bold ? .medium : .regular)
                .foregroundStyle(Palette.onSurface)
        }
        .padding(.vertical, Spacing.xs)
    }
}

/// The boarding code, the largest thing on its screen: a driver reads it
/// across a car in daylight, character by character, so it is always Latin.
struct BoardingCode: View {
    let code: String
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(spacing: Spacing.sm) {
            Text(strings["booking.label.code"])
                .velroFont(.caption)
                .foregroundStyle(Palette.onSurfaceVariant)
            Text(code)
                .font(.system(size: 40, weight: .bold, design: .rounded))
                .tracking(8)
                .monospacedDigit()
                .foregroundStyle(Palette.onPrimaryContainer)
                .padding(.horizontal, Spacing.xl)
                .padding(.vertical, Spacing.lg)
                .background(Palette.primaryContainer, in: RoundedRectangle(cornerRadius: Radius.lg, style: .continuous))
                .environment(\.layoutDirection, .leftToRight)
                .accessibilityIdentifier("booking.code")
            Text(strings["booking.hint.code"])
                .velroFont(.caption)
                .foregroundStyle(Palette.onSurfaceVariant)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
    }
}
