import SwiftUI

/// The mark between two facts on a row: "۲۴ سنبله | ۰ / ۴ | ۳ آنلاین".
///
/// A short rule, not a middle dot: beside Eastern digits "·" is read as the
/// Persian zero, so "· ۳" became "۳۰". A rule reads the same in both
/// directions and in every font.
struct DotSeparator: View {
    var body: some View {
        Capsule()
            .fill(Palette.border)
            .frame(width: 1, height: 12)
            .accessibilityHidden(true)
    }
}
