// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "Comodoro",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "Comodoro", targets: ["Comodoro"])
    ],
    targets: [
        .executableTarget(
            name: "Comodoro",
            linkerSettings: [.linkedLibrary("sqlite3")]
        ),
        .testTarget(
            name: "ComodoroTests",
            dependencies: ["Comodoro"]
        )
    ]
)
