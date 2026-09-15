import SwiftUI
import VelroCore

/// The map's colours for car states, light and dark.
///
/// The web panel's --map-trip / --map-online / --map-stale on a light map,
/// with lifted values for MapKit's dark map, where the web's greens and
/// greys would sink into the ground. Every pin also carries its state's
/// glyph and a legend with the words: colour never says it alone.
enum FleetPalette {
    static func color(_ state: FleetCarState, _ scheme: ColorScheme) -> Color {
        let dark = scheme == .dark
        return switch state {
        case .trip: Color(hex: dark ? 0x3987E5 : 0x2A78D6)
        case .waiting: Color(hex: dark ? 0x2FB27C : 0x127954)
        case .stale: Color(hex: dark ? 0x8B95A3 : 0x667085)
        }
    }

    /// The ring around a pin and the glyph on a filled one: white on either
    /// map, as the system's own markers are.
    static let ring = Color.white
}

/// One car: a disc in its state's colour with the state's glyph, an arrow
/// for its heading when the phone sends one, hollow for a test driver.
struct FleetPin: View {
    let state: FleetCarState
    let isTest: Bool
    var heading: Double?
    var isSelected = false
    var diameter: CGFloat = 30

    @Environment(\.colorScheme) private var scheme

    private var tint: Color { FleetPalette.color(state, scheme) }

    var body: some View {
        ZStack {
            if let heading {
                // Rotated with the frame around it, so the arrow rides the
                // disc's edge. The map does not rotate (north stays up), so a
                // compass heading is a screen direction.
                Image(systemName: "arrowtriangle.up.fill")
                    .font(.system(size: diameter * 0.32, weight: .bold))
                    .foregroundStyle(tint)
                    .shadow(color: .black.opacity(0.25), radius: 1)
                    .offset(y: -(diameter / 2 + diameter * 0.2))
                    .rotationEffect(.degrees(heading))
            }
            disc
        }
        .frame(width: diameter * 1.8, height: diameter * 1.8)
        .scaleEffect(isSelected ? 1.18 : 1)
        .animation(.spring(duration: 0.25), value: isSelected)
    }

    private var disc: some View {
        ZStack {
            Circle()
                .fill(isTest ? Palette.surface : tint)
            Circle()
                .strokeBorder(isTest ? tint : FleetPalette.ring, lineWidth: isTest ? 3 : 2)
            Image(systemName: state.symbol)
                .font(.system(size: diameter * 0.42, weight: .semibold))
                .foregroundStyle(isTest ? tint : FleetPalette.ring)
        }
        .frame(width: diameter, height: diameter)
        .overlay {
            if isSelected {
                Circle()
                    .strokeBorder(Palette.accent, lineWidth: 3)
                    .padding(-5)
            }
        }
        .shadow(color: .black.opacity(0.28), radius: 3, y: 1)
    }
}

/// A small pin for a legend or a list row: the same disc, no heading.
struct FleetPinGlyph: View {
    let state: FleetCarState
    var isTest = false
    var diameter: CGFloat = 18

    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let tint = FleetPalette.color(state, scheme)
        ZStack {
            Circle().fill(isTest ? Palette.surface : tint)
            Circle().strokeBorder(isTest ? tint : FleetPalette.ring, lineWidth: isTest ? 2 : 1)
            Image(systemName: state.symbol)
                .font(.system(size: diameter * 0.46, weight: .semibold))
                .foregroundStyle(isTest ? tint : FleetPalette.ring)
        }
        .frame(width: diameter, height: diameter)
        .accessibilityHidden(true)
    }
}
