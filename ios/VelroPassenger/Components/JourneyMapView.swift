import MapKit
import SwiftUI
import VelroCore

/// The road between a journey's two ends, and the car on it while one is owed.
///
/// A picture on top of a flow that already works in words: when the server
/// cannot draw the road, there is no map and no complaint. The base map is
/// Apple's; the road line is the server's, and so is its attribution.
struct JourneyMapView: View {
    let map: TripMap
    var vehicle: VehicleLocation?
    var height: CGFloat? = 180
    /// Edge to edge, for the ride itself: no rounded card, no caption under it.
    var fullBleed = false
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.xxs) {
            Map(initialPosition: .rect(region), interactionModes: [.pan, .zoom]) {
                if road.count >= 2 {
                    MapPolyline(coordinates: road)
                        .stroke(Palette.primary, style: StrokeStyle(lineWidth: 4, lineCap: .round, lineJoin: .round))
                }
                if let origin = map.origin {
                    Annotation(origin.name, coordinate: coordinate(origin)) {
                        Circle().fill(Palette.primary).frame(width: 14, height: 14)
                            .overlay(Circle().stroke(.white, lineWidth: 2))
                    }
                }
                if let destination = map.destination {
                    Annotation(destination.name, coordinate: coordinate(destination)) {
                        // A square, not a second dot: the two ends are not
                        // interchangeable, as on the journey line.
                        RoundedRectangle(cornerRadius: 3).fill(Palette.accent).frame(width: 14, height: 14)
                            .overlay(RoundedRectangle(cornerRadius: 3).stroke(.white, lineWidth: 2))
                    }
                }
                if let vehicle {
                    Annotation("", coordinate: CLLocationCoordinate2D(latitude: vehicle.latitude, longitude: vehicle.longitude)) {
                        Image(systemName: "car.circle.fill")
                            .font(.system(size: 28))
                            .foregroundStyle(.white, Palette.brandField)
                            .shadow(radius: 2)
                    }
                }
            }
            .mapStyle(.standard(pointsOfInterest: .excludingAll))
            .frame(height: height)
            .frame(maxHeight: height == nil ? .infinity : nil)
            .clipShape(RoundedRectangle(cornerRadius: fullBleed ? 0 : Radius.card, style: .continuous))
            .accessibilityHidden(true)

            if !fullBleed, let attribution = map.attribution, !attribution.isEmpty {
                Text(attribution)
                    .font(.caption2)
                    .foregroundStyle(Palette.onSurfaceVariant)
                    .environment(\.layoutDirection, .leftToRight)
            }
        }
    }

    private var road: [CLLocationCoordinate2D] {
        map.road.map { CLLocationCoordinate2D(latitude: $0.latitude, longitude: $0.longitude) }
    }

    private func coordinate(_ place: MapPlace) -> CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: place.latitude, longitude: place.longitude)
    }

    /// Everything worth seeing -- road, ends, car -- with a margin.
    private var region: MKMapRect {
        var points = road
        if let origin = map.origin { points.append(coordinate(origin)) }
        if let destination = map.destination { points.append(coordinate(destination)) }
        if let vehicle { points.append(CLLocationCoordinate2D(latitude: vehicle.latitude, longitude: vehicle.longitude)) }
        var rect = MKMapRect.null
        for point in points {
            let mapPoint = MKMapPoint(point)
            rect = rect.union(MKMapRect(x: mapPoint.x, y: mapPoint.y, width: 1, height: 1))
        }
        guard !rect.isNull else { return MKMapRect(origin: MKMapPoint(CLLocationCoordinate2D(latitude: 34.95, longitude: 68.6)), size: MKMapSize(width: 60_000, height: 60_000)) }
        let margin = max(rect.width, rect.height) * 0.25 + 2_000
        return rect.insetBy(dx: -margin, dy: -margin)
    }
}
