import SwiftUI

// The drawn pieces of a ride app: streets, cars, the sheet that lies over a
// map, the round buttons that float on one. Drawn rather than shipped as
// pictures, so they cost nothing on a metered connection, follow the theme,
// and stay sharp at any size.

/// A car seen from above, pointing up. Rotated by whoever places it.
struct CarGlyph: View {
    /// The primary green: the brand by day, the light green after dark,
    /// where the brand green would vanish into the night ground.
    var color: Color = Palette.primary
    var size: CGFloat = 28

    var body: some View {
        Canvas { context, canvas in
            let w = canvas.width, h = canvas.height
            let shell = CGRect(x: w * 0.18, y: 0, width: w * 0.64, height: h)
            context.fill(Path(roundedRect: shell, cornerRadius: w * 0.22), with: .color(color))
            // Glass front and back, lighter than the shell.
            let front = CGRect(x: w * 0.27, y: h * 0.2, width: w * 0.46, height: h * 0.17)
            let back = CGRect(x: w * 0.29, y: h * 0.7, width: w * 0.42, height: h * 0.12)
            context.fill(Path(roundedRect: front, cornerRadius: w * 0.06), with: .color(.white.opacity(0.85)))
            context.fill(Path(roundedRect: back, cornerRadius: w * 0.05), with: .color(.white.opacity(0.7)))
            // Mirrors.
            let mirror = CGSize(width: w * 0.1, height: h * 0.06)
            context.fill(Path(roundedRect: CGRect(origin: CGPoint(x: w * 0.1, y: h * 0.3), size: mirror), cornerRadius: 1), with: .color(color))
            context.fill(Path(roundedRect: CGRect(origin: CGPoint(x: w * 0.8, y: h * 0.3), size: mirror), cornerRadius: 1), with: .color(color))
        }
        .frame(width: size * 0.62, height: size)
        .shadow(color: .black.opacity(0.2), radius: 2, y: 1)
        .accessibilityHidden(true)
    }
}

/// A town's streets, drawn: the backdrop of the sign-in card and the intro.
///
/// The same map every time, so it reads as a picture and never as a claim
/// about where anybody is. A car drives the route to the pin; with reduced
/// motion it waits at the start.
struct StreetMapArt: View {
    var animated = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        GeometryReader { geometry in
            let size = geometry.size
            TimelineView(.animation(minimumInterval: 1 / 30, paused: !animated || reduceMotion)) { timeline in
                let progress = (animated && !reduceMotion) ? Self.progress(at: timeline.date) : 0
                ZStack(alignment: .topLeading) {
                    Canvas { context, canvas in
                        draw(in: &context, size: canvas)
                    }
                    parked(size: size)
                    let (point, angle) = Self.position(on: Self.route, at: progress, size: size)
                    CarGlyph(size: 30)
                        .rotationEffect(.radians(angle))
                        .position(point)
                    pin.position(Self.point(Self.route.last!, size))
                }
            }
        }
        // A picture, not a layout: the canvas is never mirrored, so the cars
        // placed on it must not be either, or in Dari they leave the road.
        .environment(\.layoutDirection, .leftToRight)
        .accessibilityHidden(true)
    }

    // MARK: Geometry, in unit coordinates

    /// Avenues first, drawn wider; then the side streets.
    private static let avenues: [[CGPoint]] = [
        [CGPoint(x: -0.05, y: 0.78), CGPoint(x: 0.4, y: 0.62), CGPoint(x: 1.05, y: 0.55)],
        [CGPoint(x: 0.18, y: -0.05), CGPoint(x: 0.3, y: 0.45), CGPoint(x: 0.38, y: 1.05)],
        [CGPoint(x: 0.95, y: -0.05), CGPoint(x: 0.62, y: 0.5), CGPoint(x: 0.45, y: 1.05)],
    ]
    private static let streets: [[CGPoint]] = [
        [CGPoint(x: -0.05, y: 0.22), CGPoint(x: 0.55, y: 0.08)],
        [CGPoint(x: -0.05, y: 0.42), CGPoint(x: 0.3, y: 0.36), CGPoint(x: 0.8, y: 0.2)],
        [CGPoint(x: 0.5, y: -0.05), CGPoint(x: 0.56, y: 0.3)],
        [CGPoint(x: 0.7, y: 0.0), CGPoint(x: 1.05, y: 0.32)],
        [CGPoint(x: 0.75, y: 0.38), CGPoint(x: 1.05, y: 0.8)],
        [CGPoint(x: 0.05, y: 0.6), CGPoint(x: 0.22, y: 1.05)],
        [CGPoint(x: 0.55, y: 0.75), CGPoint(x: 1.05, y: 1.0)],
        [CGPoint(x: 0.82, y: 0.6), CGPoint(x: 0.72, y: 1.05)],
        [CGPoint(x: -0.05, y: 0.95), CGPoint(x: 0.3, y: 0.88)],
        [CGPoint(x: 0.12, y: 0.1), CGPoint(x: 0.08, y: 0.5)],
    ]
    /// From the car's corner to the pin, along the streets above.
    static let route: [CGPoint] = [
        CGPoint(x: 0.24, y: 0.12), CGPoint(x: 0.3, y: 0.45), CGPoint(x: 0.4, y: 0.62), CGPoint(x: 0.62, y: 0.6),
    ]
    private static let parkedCars: [(CGPoint, Double)] = [
        (CGPoint(x: 0.08, y: 0.3), 0.15), (CGPoint(x: 0.86, y: 0.22), 2.4), (CGPoint(x: 0.8, y: 0.85), -1.1),
    ]

    private static func point(_ unit: CGPoint, _ size: CGSize) -> CGPoint {
        CGPoint(x: unit.x * size.width, y: unit.y * size.height)
    }

    private func draw(in context: inout GraphicsContext, size: CGSize) {
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(Palette.primaryContainer))
        // A few blocks, a shade darker, so the ground is a town and not paper.
        for (index, block) in [CGRect(x: 0.38, y: 0.12, width: 0.14, height: 0.14),
                               CGRect(x: 0.7, y: 0.66, width: 0.12, height: 0.12),
                               CGRect(x: 0.04, y: 0.66, width: 0.12, height: 0.1)].enumerated() {
            let rect = CGRect(x: block.minX * size.width, y: block.minY * size.height,
                              width: block.width * size.width, height: block.height * size.height)
            context.fill(Path(roundedRect: rect, cornerRadius: 6),
                         with: .color(Palette.primary.opacity(index == 1 ? 0.08 : 0.06)))
        }
        let street = Palette.surface
        for line in Self.streets {
            context.stroke(path(line, size), with: .color(street), style: StrokeStyle(lineWidth: 5, lineCap: .round, lineJoin: .round))
        }
        for line in Self.avenues {
            context.stroke(path(line, size), with: .color(street), style: StrokeStyle(lineWidth: 10, lineCap: .round, lineJoin: .round))
        }
        context.stroke(path(Self.route, size), with: .color(Palette.primary),
                       style: StrokeStyle(lineWidth: 4, lineCap: .round, lineJoin: .round))
    }

    private func path(_ points: [CGPoint], _ size: CGSize) -> Path {
        var path = Path()
        path.addLines(points.map { Self.point($0, size) })
        return path
    }

    private func parked(size: CGSize) -> some View {
        ForEach(Array(Self.parkedCars.enumerated()), id: \.offset) { _, car in
            CarGlyph(size: 26)
                .rotationEffect(.radians(car.1))
                .position(Self.point(car.0, size))
        }
    }

    /// The destination: an amber pin, a square at its foot as on the journey
    /// line, so the two ends differ by shape as well as colour.
    private var pin: some View {
        Image(systemName: "mappin.circle.fill")
            .font(.system(size: 28))
            .foregroundStyle(.white, Palette.accent)
            .background(Circle().fill(.white).padding(4))
            .shadow(color: .black.opacity(0.18), radius: 4, y: 2)
            .offset(y: -14)
    }

    // MARK: Motion

    /// Eight seconds to the pin, a breath there, and round again.
    private static func progress(at date: Date) -> Double {
        let period = 10.0
        let t = date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: period) / 8.0
        let clamped = min(t, 1)
        return clamped < 0.5 ? 2 * clamped * clamped : 1 - pow(-2 * clamped + 2, 2) / 2
    }

    static func position(on route: [CGPoint], at progress: Double, size: CGSize) -> (CGPoint, Double) {
        let points = route.map { point($0, size) }
        var lengths: [CGFloat] = []
        for index in 1..<points.count {
            lengths.append(hypot(points[index].x - points[index - 1].x, points[index].y - points[index - 1].y))
        }
        let total = lengths.reduce(0, +)
        var remaining = CGFloat(progress) * total
        for index in 1..<points.count {
            let segment = lengths[index - 1]
            let a = points[index - 1], b = points[index]
            if remaining <= segment || index == points.count - 1 {
                let f = segment == 0 ? 0 : min(remaining / segment, 1)
                let point = CGPoint(x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f)
                // The glyph points up; atan2 measures from the x axis.
                let angle = atan2(b.y - a.y, b.x - a.x) + .pi / 2
                return (point, Double(angle))
            }
            remaining -= segment
        }
        return (points[0], 0)
    }
}

/// A round button floating over a map or a picture: glass, 52pt.
struct RoundIconButton: View {
    let systemImage: String
    let label: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(Palette.brandField)
                .frame(width: Sizing.touchTarget, height: Sizing.touchTarget)
                .glass(in: Circle())
                .contentShape(Circle())
        }
        .buttonStyle(PressStyle())
        .accessibilityLabel(label)
    }
}

/// The handle on a sheet: a short rounded bar.
struct SheetGrabber: View {
    var body: some View {
        Capsule()
            .fill(Palette.outline.opacity(0.45))
            .frame(width: 44, height: 5)
            .frame(maxWidth: .infinity)
            .padding(.top, Spacing.sm)
            .accessibilityHidden(true)
    }
}

extension View {
    /// The panel that rises over a map: frosted, so the map still shows
    /// faintly through its edge, rounded on top and square at the bottom
    /// where it meets the edge of the phone. Frosted, not clear: the words on
    /// it are read in daylight, so the page colour is laid back over the blur.
    func sheetPanel() -> some View {
        background(
            UnevenRoundedRectangle(topLeadingRadius: Radius.sheet, topTrailingRadius: Radius.sheet, style: .continuous)
                .fill(Palette.background.opacity(0.88))
                .background(.ultraThinMaterial, in: UnevenRoundedRectangle(topLeadingRadius: Radius.sheet, topTrailingRadius: Radius.sheet, style: .continuous))
                .overlay(
                    UnevenRoundedRectangle(topLeadingRadius: Radius.sheet, topTrailingRadius: Radius.sheet, style: .continuous)
                        .stroke(.white.opacity(0.5), lineWidth: 1)
                )
                .shadow(color: .black.opacity(0.08), radius: 24, y: -6)
                .ignoresSafeArea(edges: .bottom)
        )
    }

    /// The same panel standing free beside the map on a wide screen -- an
    /// unfolded phone -- rounded all round, where a sheet would stretch a
    /// list across the whole width.
    func floatingPanel() -> some View {
        background(
            RoundedRectangle(cornerRadius: Radius.sheet, style: .continuous)
                .fill(Palette.background.opacity(0.88))
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: Radius.sheet, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: Radius.sheet, style: .continuous).stroke(.white.opacity(0.5), lineWidth: 1))
                .shadow(color: .black.opacity(0.10), radius: 24, y: 8)
        )
        .clipShape(RoundedRectangle(cornerRadius: Radius.sheet, style: .continuous))
    }

    /// Glass, for what floats over a map or a picture: iOS's own from 26 on,
    /// which bends and catches the light as it should; before that a frosted
    /// material with a bright edge, the nearest thing.
    @ViewBuilder
    func glass<S: Shape>(in shape: S) -> some View {
        if #available(iOS 26.0, *) {
            glassEffect(.regular.interactive(), in: shape)
        } else {
            background(.ultraThinMaterial, in: shape)
                .overlay(shape.stroke(.white.opacity(0.45), lineWidth: 1))
                .elevation(.high)
        }
    }
}

/// Rings spreading from a car: drivers are being shown the request now.
/// Still, with reduced motion: the words beside it carry the meaning.
struct RadarPulse: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { timeline in
            let t = reduceMotion ? 0.35 : timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 2.4) / 2.4
            ZStack {
                ForEach(0..<3) { ring in
                    let phase = (t + Double(ring) / 3).truncatingRemainder(dividingBy: 1)
                    Circle()
                        .stroke(Palette.primary.opacity(0.5 * (1 - phase)), lineWidth: 2)
                        .frame(width: 60 + 110 * phase, height: 60 + 110 * phase)
                }
                Circle()
                    .fill(Palette.primaryContainer)
                    .frame(width: 72, height: 72)
                Image(systemName: "car.fill")
                    .font(.system(size: 28, weight: .semibold))
                    .foregroundStyle(Palette.primary)
            }
            .frame(width: 180, height: 180)
        }
        .accessibilityHidden(true)
    }
}

/// Five stars for a rating out of five, half stars included. The number is
/// said beside it; the stars are for the eye.
struct StarRating: View {
    let rating: Double
    var size: CGFloat = 12

    var body: some View {
        HStack(spacing: 2) {
            ForEach(0..<5) { index in
                let fill = rating - Double(index)
                Image(systemName: fill >= 0.75 ? "star.fill" : (fill >= 0.25 ? "star.leadinghalf.filled" : "star"))
                    .font(.system(size: size, weight: .semibold))
                    .foregroundStyle(Palette.accent)
            }
        }
        .accessibilityHidden(true)
    }
}
