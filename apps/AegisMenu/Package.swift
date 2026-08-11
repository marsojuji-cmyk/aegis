// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AegisMenu",
    platforms: [
        .macOS(.v14),
    ],
    products: [
        .executable(name: "AegisMenu", targets: ["AegisMenu"]),
    ],
    targets: [
        .executableTarget(
            name: "AegisMenu",
            path: "Sources/AegisMenu"
        ),
    ]
)
