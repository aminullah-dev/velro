// swift-tools-version: 6.0
//
// Everything the passenger app knows that is not a screen: the API, the
// session, and the text. Kept out of the app target so `make core-test` checks
// it on the Mac in seconds, with no simulator in the way.

import PackageDescription

let package = Package(
    name: "VelroCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "VelroCore", targets: ["VelroCore"]),
    ],
    targets: [
        .target(name: "VelroCore"),
        .testTarget(name: "VelroCoreTests", dependencies: ["VelroCore"]),
    ]
)
