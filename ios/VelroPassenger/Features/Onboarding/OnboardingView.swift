import SwiftUI
import VelroCore

/// Three pages, once, before the first sign-in: what is different about
/// VELRO, said before anybody is asked for a phone number. She names the
/// price; drivers answer; she travels with a code and a way to call for help.
///
/// Skippable from the first page, and never shown again once passed -- a
/// shared phone handed to a second person opens on sign-in, not on a tour.
struct OnboardingView: View {
    let finish: () -> Void
    @Environment(\.strings) private var strings
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var page = 0

    private let pages: [Page] = [
        Page(titleKey: "onboarding.fare.title", bodyKey: "onboarding.fare.body", chip: .fare),
        Page(titleKey: "onboarding.offers.title", bodyKey: "onboarding.offers.body", chip: .offers),
        Page(titleKey: "onboarding.safe.title", bodyKey: "onboarding.safe.body", chip: .safe),
    ]

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(strings["app.name"])
                    .velroFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.primary)
                Spacer()
                TextAction(label: strings["common.action.skip"], action: finish)
                    .accessibilityIdentifier("intro.skip")
            }
            .padding(.horizontal, Spacing.gutter)

            TabView(selection: $page) {
                ForEach(pages.indices, id: \.self) { index in
                    PageView(page: pages[index], current: page == index)
                        .tag(index)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))

            VStack(spacing: Spacing.xl) {
                ProgressTrack(count: pages.count, current: page) { go(to: page - 1) }
                PrimaryButton(label: strings[page == pages.count - 1 ? "common.action.get_started" : "common.action.next"]) {
                    if page == pages.count - 1 { finish() } else { go(to: page + 1) }
                }
                .accessibilityIdentifier("intro.next")
            }
            .padding(.horizontal, Spacing.gutter)
            .padding(.bottom, Spacing.lg)
        }
        .frame(maxWidth: Wide.readable)
        .frame(maxWidth: .infinity)
        .background(Palette.background)
    }

    private func go(to index: Int) {
        guard pages.indices.contains(index) else { return }
        withAnimation(reduceMotion ? nil : .snappy) { page = index }
    }

    fileprivate struct Page {
        let titleKey: String
        let bodyKey: String
        let chip: Chip
    }

    fileprivate enum Chip { case fare, offers, safe }
}

private struct PageView: View {
    let page: OnboardingView.Page
    let current: Bool
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.md) {
            Text(strings[page.titleKey])
                .velroFont(.hero)
                .foregroundStyle(Palette.primary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            Text(strings[page.bodyKey])
                .velroFont(.body)
                .foregroundStyle(Palette.onSurfaceVariant)
                .fixedSize(horizontal: false, vertical: true)

            Spacer(minLength: Spacing.lg)
            Hero(chip: page.chip, current: current)
                .frame(maxWidth: .infinity)
            Spacer(minLength: Spacing.lg)
        }
        .padding(.horizontal, Spacing.gutter)
        .padding(.top, Spacing.xl)
    }
}

/// The car on its road, with the one thing each page is about floating
/// beside it. The car drives in when its page arrives.
private struct Hero: View {
    let chip: OnboardingView.Chip
    let current: Bool
    @Environment(\.layoutDirection) private var direction
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.strings) private var strings
    @State private var arrived = false

    var body: some View {
        ZStack {
            Circle()
                .fill(Palette.primaryContainer)
                .frame(width: 260, height: 260)
            // The road under the wheels.
            Capsule()
                .fill(Palette.outlineVariant)
                .frame(width: 300, height: 8)
                .offset(y: 70)
            Image(systemName: "car.side.fill")
                .font(.system(size: 150, weight: .regular))
                .foregroundStyle(Palette.primary)
                // The symbol faces left; turned round in English, so the car
                // always heads the way the pages turn.
                .scaleEffect(x: direction == .rightToLeft ? 1 : -1)
                .shadow(color: .black.opacity(0.18), radius: 10, y: 10)
                .offset(x: arrived ? 0 : (direction == .rightToLeft ? 60 : -60), y: 10)
                .opacity(arrived ? 1 : 0)
            floating
                .offset(x: 70, y: -95)
                .scaleEffect(arrived ? 1 : 0.6)
                .opacity(arrived ? 1 : 0)
        }
        .frame(height: 300)
        .accessibilityHidden(true)
        .onAppear { arrive() }
        .onChange(of: current) { _, now in if now { arrive() } else { arrived = false } }
    }

    private func arrive() {
        guard current else { return }
        if reduceMotion { arrived = true; return }
        arrived = false
        withAnimation(.spring(duration: 0.6, bounce: 0.25).delay(0.1)) { arrived = true }
    }

    @ViewBuilder
    private var floating: some View {
        switch chip {
        case .fare:
            // Her price, in her currency, before anybody else's.
            HStack(spacing: Spacing.sm) {
                Image(systemName: "banknote.fill")
                    .foregroundStyle(Palette.accent)
                Text(strings["common.label.currency_afn"])
                    .velroFont(.label, weight: .bold)
                    .foregroundStyle(Palette.onSurface)
                Image(systemName: "hand.raised.fill")
                    .foregroundStyle(Palette.primary)
            }
            .padding(.horizontal, Spacing.lg)
            .padding(.vertical, Spacing.md)
            .background(Palette.surface, in: Capsule())
            .elevation(.high)
        case .offers:
            // Two answers, one marked as the better.
            VStack(spacing: Spacing.sm) {
                miniOffer(best: true)
                miniOffer(best: false).scaleEffect(0.92)
            }
        case .safe:
            HStack(spacing: Spacing.sm) {
                Image(systemName: "checkmark.shield.fill")
                    .font(.title2)
                    .foregroundStyle(Palette.primary)
                Text("• • • •")
                    .font(.system(size: 18, weight: .bold, design: .rounded))
                    .foregroundStyle(Palette.onPrimaryContainer)
            }
            .padding(.horizontal, Spacing.lg)
            .padding(.vertical, Spacing.md)
            .background(Palette.surface, in: Capsule())
            .elevation(.high)
        }
    }

    private func miniOffer(best: Bool) -> some View {
        HStack(spacing: Spacing.sm) {
            Circle().fill(Palette.surfaceVariant).frame(width: 26, height: 26)
                .overlay(Image(systemName: "person.fill").font(.caption2).foregroundStyle(Palette.onSurfaceVariant))
            VStack(alignment: .leading, spacing: 4) {
                Capsule().fill(Palette.onSurface.opacity(0.7)).frame(width: 46, height: 6)
                StarRating(rating: best ? 5 : 4, size: 7)
            }
            Capsule().fill(best ? Palette.primary : Palette.outline).frame(width: 28, height: 10)
        }
        .padding(Spacing.sm)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: Radius.md, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: Radius.md, style: .continuous)
                .strokeBorder(Palette.primary, lineWidth: best ? 2 : 0)
        )
        .elevation(.high)
    }
}

/// Where she is in the tour: a road with a stop per page and a car at the
/// current one. Back sits at the start of the road from the second page on.
private struct ProgressTrack: View {
    let count: Int
    let current: Int
    let back: () -> Void
    @Environment(\.strings) private var strings
    @Environment(\.layoutDirection) private var direction
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(spacing: Spacing.md) {
            Button(action: back) {
                Image(systemName: "chevron.backward")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(Palette.primary)
                    .frame(width: Sizing.touchTarget, height: Sizing.touchTarget)
                    .contentShape(Rectangle())
            }
            .buttonStyle(PressStyle())
            .opacity(current == 0 ? 0 : 1)
            .disabled(current == 0)
            .accessibilityLabel(strings["common.action.back"])

            GeometryReader { geometry in
                let width = geometry.size.width
                let y = geometry.size.height / 2
                ZStack {
                    Capsule().fill(Palette.outlineVariant)
                        .frame(width: width, height: 3)
                        .position(x: width / 2, y: y)
                    Capsule().fill(Palette.primary)
                        .frame(width: width * fraction(current), height: 3)
                        .position(x: width * fraction(current) / 2, y: y)
                    ForEach(0..<count, id: \.self) { index in
                        Circle()
                            .fill(index <= current ? Palette.primary : Palette.outline)
                            .frame(width: 9, height: 9)
                            .position(x: width * fraction(index), y: y)
                    }
                    // The car points the way the pages go: right in English,
                    // left in Dari and Pashto, where the whole track mirrors.
                    CarGlyph(size: 34)
                        .rotationEffect(.degrees(direction == .rightToLeft ? -90 : 90))
                        .position(x: width * fraction(current), y: y)
                }
                .animation(reduceMotion ? nil : .spring(duration: 0.5, bounce: 0.2), value: current)
            }
            .frame(height: Sizing.touchTarget)
            .padding(.trailing, Spacing.lg)
        }
        .accessibilityElement(children: .contain)
        .accessibilityValue(strings["common.state.step", ["current": current + 1, "total": count]])
    }

    private func fraction(_ index: Int) -> CGFloat {
        count > 1 ? CGFloat(index) / CGFloat(count - 1) : 0
    }
}
