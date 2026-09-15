import SwiftUI
import VelroCore

/// The filter chips, with how many drivers each would show.
struct FleetFilterBar: View {
    @Bindable var model: FleetModel
    @Environment(\.strings) private var strings

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Spacing.s2) {
                ForEach(FleetFilter.allCases) { filter in
                    chip(filter)
                }
            }
            .padding(.horizontal, Spacing.s3)
            .padding(.vertical, Spacing.s2)
        }
    }

    private func chip(_ filter: FleetFilter) -> some View {
        let isOn = model.filter == filter
        let count = model.count(filter)
        return Button {
            withAnimation(.snappy) { model.filter = filter }
        } label: {
            HStack(spacing: Spacing.s1 + 2) {
                glyph(filter)
                Text(strings[filter.labelKey])
                    .opsFont(.label, weight: .medium)
                    .lineLimit(1)
                Text(OpsFormat.count(count, strings))
                    .opsFont(.caption, weight: .bold)
                    .monospacedDigit()
                    .foregroundStyle(isOn ? Palette.onAccent : Palette.textMuted)
            }
            .padding(.horizontal, Spacing.s3)
            .frame(minHeight: 34)
            .foregroundStyle(isOn ? Palette.onAccent : Palette.text)
            .background {
                if isOn {
                    Capsule().fill(Palette.accent)
                } else {
                    Capsule().fill(.regularMaterial)
                }
            }
            .overlay { Capsule().strokeBorder(isOn ? Color.clear : Palette.border, lineWidth: 1) }
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(isOn ? [.isButton, .isSelected] : .isButton)
    }

    @ViewBuilder private func glyph(_ filter: FleetFilter) -> some View {
        switch filter {
        case .all: EmptyView()
        case .trip: FleetPinGlyph(state: .trip, diameter: 16)
        case .waiting: FleetPinGlyph(state: .waiting, diameter: 16)
        case .stale: FleetPinGlyph(state: .stale, diameter: 16)
        case .test: FleetPinGlyph(state: .waiting, isTest: true, diameter: 16)
        }
    }
}

/// What each pin means, how many of each, and how old the positions are.
struct FleetLegendCard: View {
    let model: FleetModel
    let snapshot: LiveMap
    @Environment(\.strings) private var strings

    var body: some View {
        let counts = FleetCounts(snapshot.drivers)
        let offMap = FleetGroups(snapshot.drivers).offMapCount
        VStack(alignment: .leading, spacing: Spacing.s2) {
            if let error = model.refreshError {
                Banner(strings.forErrorCode(error.code, context: error.context.arguments), tone: .error,
                       systemImage: "exclamationmark.triangle")
            }
            FleetFlowLayout(spacing: Spacing.s3, lineSpacing: Spacing.s2) {
                ForEach(FleetCarState.allCases) { state in
                    item(FleetPinGlyph(state: state), labelKey: state.labelKey, count: counts[state])
                }
                item(FleetPinGlyph(state: .waiting, isTest: true), labelKey: "admin.map.test_legend", count: counts.test)
            }
            HStack(spacing: Spacing.s2) {
                FleetAsOfText(snapshot: snapshot)
                Spacer(minLength: 0)
                if offMap > 0 {
                    Button {
                        withAnimation(.snappy) { model.mode = .list }
                    } label: {
                        Label(strings["ops.map.off_map", ["count": offMap]], systemImage: "list.bullet")
                            .opsFont(.caption, weight: .medium)
                            .lineLimit(1)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Palette.accent)
                }
            }
        }
        .padding(Spacing.s3)
        .frame(maxWidth: 560, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: Radius.lg, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: Radius.lg, style: .continuous).strokeBorder(Palette.border, lineWidth: 1)
        }
    }

    private func item(_ glyph: FleetPinGlyph, labelKey: String, count: Int) -> some View {
        HStack(spacing: Spacing.s1 + 2) {
            glyph
            Text(strings[labelKey])
                .opsFont(.caption, weight: .medium)
                .foregroundStyle(Palette.text)
            Text(OpsFormat.count(count, strings))
                .opsFont(.caption)
                .monospacedDigit()
                .foregroundStyle(Palette.textMuted)
        }
        .accessibilityElement(children: .combine)
    }
}

/// "Positions as of 08:30": Kabul time, with the day when it is not today's.
struct FleetAsOfText: View {
    let snapshot: LiveMap
    @Environment(\.strings) private var strings

    var body: some View {
        if let generated = snapshot.generated {
            let recent = abs(generated.timeIntervalSinceNow) < 6 * 3600
            Text(strings["admin.map.as_of", [
                "time": recent ? OpsFormat.time(generated, strings) : OpsFormat.dateTime(generated, strings),
            ]])
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
            .monospacedDigit()
        }
    }
}

/// A sentence in a card, over the map or in place of the list.
struct FleetNoticeCard: View {
    let systemImage: String
    let text: String

    var body: some View {
        HStack(spacing: Spacing.s3) {
            Image(systemName: systemImage)
                .font(.system(size: 20))
                .foregroundStyle(Palette.textMuted)
                .accessibilityHidden(true)
            Text(text)
                .opsFont(.body)
                .foregroundStyle(Palette.text)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(Spacing.s4)
        .frame(maxWidth: 480)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: Radius.lg, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: Radius.lg, style: .continuous).strokeBorder(Palette.border, lineWidth: 1)
        }
    }
}

/// Items in lines, wrapping when a line is full: a legend that fits an
/// iPhone in two lines and a Mac in one. Mirrored in right-to-left by
/// SwiftUI itself, as every layout is.
struct FleetFlowLayout: Layout {
    var spacing: CGFloat
    var lineSpacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let lines = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let width = lines.map(\.width).max() ?? 0
        let height = lines.reduce(0) { $0 + $1.height } + lineSpacing * CGFloat(max(0, lines.count - 1))
        return CGSize(width: proposal.width.map { min($0, width) } ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for line in arrange(width: bounds.width, subviews: subviews) {
            var x = bounds.minX
            for index in line.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(
                    at: CGPoint(x: x, y: y + (line.height - size.height) / 2),
                    proposal: ProposedViewSize(size)
                )
                x += size.width + spacing
            }
            y += line.height + lineSpacing
        }
    }

    private struct Line {
        var indices: [Int] = []
        var width: CGFloat = 0
        var height: CGFloat = 0
    }

    private func arrange(width: CGFloat, subviews: Subviews) -> [Line] {
        var lines: [Line] = []
        var current = Line()
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            let needed = current.indices.isEmpty ? size.width : current.width + spacing + size.width
            if needed > width, !current.indices.isEmpty {
                lines.append(current)
                current = Line()
            }
            current.width = current.indices.isEmpty ? size.width : current.width + spacing + size.width
            current.height = max(current.height, size.height)
            current.indices.append(index)
        }
        if !current.indices.isEmpty { lines.append(current) }
        return lines
    }
}
