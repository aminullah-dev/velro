import SwiftUI
import VelroCore

/// The ride's life as a row of stops: what is done is filled and ticked, where
/// it is now is lit with a ring, what is still ahead is a hollow outline.
///
/// Icons, not words -- the single clearest "this is a ride being watched"
/// signal a transport app carries, and it reads at a glance to a passenger who
/// cannot read the station names. It follows the page's direction, so in Dari
/// and Pashto the first stop is on the right and the ride runs leftward.
///
/// A ride that failed shows nothing: the status pill already says cancelled,
/// and a half-lit track beside it would only contradict it.
struct TripStatusStepper: View {
    let status: BookingStatus
    @Environment(\.strings) private var strings
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulse = false

    private struct Step { let icon: String; let labelKey: String }

    private let steps: [Step] = [
        Step(icon: "paperplane.fill", labelKey: "booking.status.confirmed"),
        Step(icon: "person.fill", labelKey: "booking.status.driver_assigned"),
        Step(icon: "car.fill", labelKey: "booking.status.ready"),
        Step(icon: "figure.seated.side", labelKey: "booking.status.onboard"),
        Step(icon: "flag.checkered", labelKey: "booking.status.completed"),
    ]

    /// Which stop is lit. Pending and confirmed are the same stop to a
    /// passenger: the car is asked for, nobody is assigned yet.
    private var current: Int? {
        switch status {
        case .pending, .confirmed: 0
        case .driverAssigned: 1
        case .ready: 2
        case .onboard: 3
        case .completed: 4
        case .cancelled, .noShow: nil
        }
    }

    var body: some View {
        if let current {
            HStack(spacing: 0) {
                ForEach(steps.indices, id: \.self) { index in
                    node(index, current: current)
                    if index < steps.count - 1 {
                        Rectangle()
                            .fill(index < current ? Palette.primary : Palette.outlineVariant)
                            .frame(height: 3)
                            .frame(maxWidth: .infinity)
                    }
                }
            }
            .frame(maxWidth: .infinity)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(strings[steps[current].labelKey])
            .onAppear { if !reduceMotion { pulse = true } }
        }
    }

    private func node(_ index: Int, current: Int) -> some View {
        let done = index < current
        let active = index == current
        let filled = done || active
        return ZStack {
            // The breath around the live stop: present without motion too, so
            // the current step is always findable, and only pulsing when the
            // phone allows it.
            if active {
                Circle()
                    .stroke(Palette.primary.opacity(0.22), lineWidth: 6)
                    .frame(width: 42, height: 42)
                    .scaleEffect(pulse ? 1 : 0.82)
                    .opacity(pulse ? 0 : 0.9)
                    .animation(reduceMotion ? nil : .easeOut(duration: 1.4).repeatForever(autoreverses: false), value: pulse)
                Circle()
                    .stroke(Palette.primary.opacity(0.3), lineWidth: 2)
                    .frame(width: 40, height: 40)
            }
            Circle()
                .fill(filled ? Palette.primary : Palette.surfaceVariant)
                .frame(width: active ? 32 : 26, height: active ? 32 : 26)
                .overlay(Circle().strokeBorder(filled ? Color.clear : Palette.outline, lineWidth: 1))
            Image(systemName: done ? "checkmark" : steps[index].icon)
                .font(.system(size: active ? 14 : 11, weight: .bold))
                .foregroundStyle(filled ? Palette.onPrimary : Palette.onSurfaceVariant)
                .accessibilityHidden(true)
        }
        .frame(width: 44, height: 44)
    }
}
