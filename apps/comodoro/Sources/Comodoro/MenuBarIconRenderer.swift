import AppKit

extension PomodoroPhase {
    var displayColor: NSColor {
        switch self {
        case .work:
            NSColor(srgbRed: 0.09, green: 0.72, blue: 0.57, alpha: 1)
        case .rest:
            NSColor(srgbRed: 0.39, green: 0.69, blue: 1, alpha: 1)
        case .complete:
            NSColor(srgbRed: 0.97, green: 0.72, blue: 0.25, alpha: 1)
        }
    }
}

enum MenuBarIconRenderer {
    static let size = NSSize(width: 18, height: 18)

    @MainActor
    static func image(symbolName: String, fractionRemaining: Double, phase: PomodoroPhase) -> NSImage {
        let fraction = Swift.min(Swift.max(fractionRemaining, 0), 1)
        let ringRect = NSRect(origin: .zero, size: size).insetBy(dx: 1.5, dy: 1.5)

        let image = NSImage(size: size, flipped: false) { bounds in
            let phaseBackground = NSBezierPath(ovalIn: ringRect.insetBy(dx: 2.5, dy: 2.5))
            phase.displayColor.setFill()
            phaseBackground.fill()

            let backgroundRing = NSBezierPath(ovalIn: ringRect)
            backgroundRing.lineWidth = 1.4
            NSColor.black.withAlphaComponent(0.22).setStroke()
            backgroundRing.stroke()

            if fraction > 0 {
                let progressRing: NSBezierPath
                if fraction >= 0.999 {
                    progressRing = NSBezierPath(ovalIn: ringRect)
                } else {
                    progressRing = NSBezierPath()
                    progressRing.appendArc(
                        withCenter: NSPoint(x: bounds.midX, y: bounds.midY),
                        radius: ringRect.width / 2,
                        startAngle: 90,
                        endAngle: 90 - (360 * fraction),
                        clockwise: true
                    )
                    progressRing.lineCapStyle = .round
                }
                progressRing.lineWidth = 1.8
                NSColor.black.setStroke()
                progressRing.stroke()
            }

            guard
                let symbol = NSImage(systemSymbolName: symbolName, accessibilityDescription: nil),
                let configuredSymbol = symbol.withSymbolConfiguration(
                    NSImage.SymbolConfiguration(pointSize: 7, weight: .bold)
                )
            else {
                return true
            }

            let symbolRect = aspectFit(
                configuredSymbol.size,
                inside: NSRect(x: bounds.midX - 4, y: bounds.midY - 4, width: 8, height: 8)
            )
            configuredSymbol.draw(
                in: symbolRect,
                from: .zero,
                operation: .sourceOver,
                fraction: 1,
                respectFlipped: true,
                hints: nil
            )
            return true
        }
        image.isTemplate = false
        return image
    }

    private static func aspectFit(_ sourceSize: NSSize, inside bounds: NSRect) -> NSRect {
        guard sourceSize.width > 0, sourceSize.height > 0 else { return bounds }
        let scale = Swift.min(bounds.width / sourceSize.width, bounds.height / sourceSize.height)
        let fittedSize = NSSize(width: sourceSize.width * scale, height: sourceSize.height * scale)
        return NSRect(
            x: bounds.midX - (fittedSize.width / 2),
            y: bounds.midY - (fittedSize.height / 2),
            width: fittedSize.width,
            height: fittedSize.height
        )
    }
}
