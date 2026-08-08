import AppKit
import Charts
import Foundation
import SwiftUI

private let tokemonSnapshotCacheFormatVersion = 1

#if !TOKEMON_TESTING
@main
struct TokemonMenuApp: App {
    @NSApplicationDelegateAdaptor(TokemonAppDelegate.self) private var appDelegate

    var body: some Scene {
        Settings {
            EmptyView()
        }
    }
}
#endif

@MainActor
private final class TokemonAppDelegate: NSObject, NSApplicationDelegate {
    private let store = TokemonStore()
    private var statusItem: NSStatusItem?
    private var panelController: TokemonPanelController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = item.button {
            button.image = NSImage(systemSymbolName: "chart.bar.xaxis", accessibilityDescription: "Tokemon")
            button.target = self
            button.action = #selector(togglePanel(_:))
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }
        statusItem = item
        panelController = TokemonPanelController(store: store)
    }

    @objc
    private func togglePanel(_ sender: Any?) {
        guard let button = statusItem?.button, let panelController else {
            return
        }

        if panelController.isVisible {
            panelController.close()
        } else {
            panelController.show(relativeTo: button)
        }
    }
}

private final class TokemonPanelController: NSObject {
    private let panel: TokemonPanel

    var isVisible: Bool {
        panel.isVisible
    }

    init(store: TokemonStore) {
        let panel = TokemonPanel(
            contentRect: NSRect(x: 0, y: 0, width: 460, height: 380),
            styleMask: [.titled, .closable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        panel.titleVisibility = .hidden
        panel.titlebarAppearsTransparent = true
        panel.isFloatingPanel = true
        panel.level = .statusBar
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        panel.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        panel.standardWindowButton(.closeButton)?.isHidden = true
        panel.standardWindowButton(.miniaturizeButton)?.isHidden = true
        panel.standardWindowButton(.zoomButton)?.isHidden = true
        panel.isMovableByWindowBackground = true
        panel.contentViewController = NSHostingController(rootView: TokemonContentView(store: store))
        self.panel = panel
        super.init()
    }

    func show(relativeTo button: NSStatusBarButton) {
        guard let buttonWindow = button.window else {
            panel.center()
            NSApp.activate(ignoringOtherApps: true)
            panel.makeKeyAndOrderFront(nil)
            return
        }

        let buttonFrame = button.convert(button.bounds, to: nil)
        let screenFrame = buttonWindow.convertToScreen(buttonFrame)
        let visibleFrame = buttonWindow.screen?.visibleFrame ?? NSScreen.main?.visibleFrame ?? screenFrame
        var origin = NSPoint(
            x: screenFrame.maxX - panel.frame.width,
            y: screenFrame.minY - panel.frame.height - 8
        )
        origin.x = min(max(origin.x, visibleFrame.minX + 8), visibleFrame.maxX - panel.frame.width - 8)
        origin.y = max(origin.y, visibleFrame.minY + 8)

        panel.setFrameOrigin(origin)
        NSApp.activate(ignoringOtherApps: true)
        panel.makeKeyAndOrderFront(nil)
    }

    func close() {
        panel.orderOut(nil)
    }
}

private final class TokemonPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

private struct TokemonContentView: View {
    @ObservedObject var store: TokemonStore

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(store.selectedRange.title)
                        .font(.title3.weight(.semibold))
                    Text(store.snapshot.subtitle)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Text("Codex + Claude")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 4) {
                    Text(store.snapshot.totalTokens.formatted())
                        .font(.system(size: 24, weight: .bold, design: .rounded))
                    Text("tokens")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Picker(
                "Range",
                selection: Binding(
                    get: { store.selectedRange },
                    set: { store.selectRange($0) }
                )
            ) {
                ForEach(TokemonRange.allCases) { range in
                    Text(range.shortLabel).tag(range)
                }
            }
            .pickerStyle(.segmented)

            if let errorMessage = store.errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .lineLimit(2)
            }

            Chart(store.snapshot.buckets) { bucket in
                BarMark(
                    x: .value("Bucket", bucket.date),
                    y: .value("Tokens", bucket.totalTokens)
                )
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .foregroundStyle(
                    .linearGradient(
                        colors: [
                            Color(red: 0.12, green: 0.59, blue: 0.56),
                            Color(red: 0.32, green: 0.77, blue: 0.52),
                        ],
                        startPoint: .bottom,
                        endPoint: .top
                    )
                )
            }
            .chartXAxis {
                AxisMarks(values: store.snapshot.axisMarkDates) { value in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                        .foregroundStyle(.quaternary)
                    AxisTick()
                    AxisValueLabel {
                        if let date = value.as(Date.self) {
                            Text(store.selectedRange.axisLabel(for: date))
                        }
                    }
                }
            }
            .chartYAxis {
                AxisMarks(position: .leading) { value in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                        .foregroundStyle(.quaternary)
                    AxisValueLabel {
                        if let tokens = value.as(Int.self) {
                            Text(tokens.abbreviatedTokenString)
                        }
                    }
                }
            }
            .chartYScale(domain: 0...max(store.snapshot.maxTokens, 1))
            .frame(height: 220)
            .overlay {
                if store.snapshot.totalTokens == 0 && !store.isLoading {
                    ContentUnavailableView(
                        "No token usage",
                        systemImage: "moon.zzz",
                        description: Text("No Codex or Claude usage was found for this range.")
                    )
                    .padding(.bottom, 8)
                }
            }

            HStack {
                if store.isLoading {
                    ProgressView()
                        .controlSize(.small)
                    if let lastUpdated = store.lastUpdated {
                        Text("Refreshing cached data from \(TokemonDateFormatting.clockString(for: lastUpdated))…")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        Text("Refreshing…")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } else if let lastUpdated = store.lastUpdated {
                    Text("Updated \(TokemonDateFormatting.clockString(for: lastUpdated))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Refresh") {
                    store.refresh()
                }
                .keyboardShortcut("r")
                Button("Quit") {
                    NSApplication.shared.terminate(nil)
                }
                .keyboardShortcut("q")
            }
        }
        .padding(16)
        .frame(width: 460)
        .background(.regularMaterial)
        .onAppear {
            store.ensureLoaded()
        }
    }
}

private typealias TokemonSnapshotLoader = @Sendable (TokemonRange) throws -> TokemonSnapshot

@MainActor
private final class TokemonStore: ObservableObject {
    @Published private(set) var selectedRange: TokemonRange
    @Published private(set) var snapshot: TokemonSnapshot
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var lastUpdated: Date?

    private let cache: TokemonSnapshotCache
    private let snapshotLoader: TokemonSnapshotLoader
    private var cachedSnapshots: [TokemonRange: TokemonCachedSnapshot]
    private var hasLoaded = false
    private var refreshTask: Task<Void, Never>?

    init(
        cache: TokemonSnapshotCache = .live(),
        snapshotLoader: @escaping TokemonSnapshotLoader = { range in
            try TokemonSnapshot.load(for: range)
        }
    ) {
        self.cache = cache
        self.snapshotLoader = snapshotLoader
        self.selectedRange = .today
        self.cachedSnapshots = cache.load()
        if let cachedSnapshot = self.cachedSnapshots[.today] {
            self.snapshot = cachedSnapshot.snapshot
            self.lastUpdated = cachedSnapshot.lastUpdated
        } else {
            self.snapshot = TokemonSnapshot.placeholder(for: .today)
            self.lastUpdated = nil
        }
    }

    func ensureLoaded() {
        if !hasLoaded && !isLoading {
            refresh(resetView: false)
        }
    }

    func selectRange(_ range: TokemonRange) {
        guard selectedRange != range else {
            return
        }
        selectedRange = range
        refresh(resetView: true)
    }

    func refresh() {
        refresh(resetView: false)
    }

    private func refresh(resetView: Bool) {
        let range = selectedRange
        primeVisibleSnapshot(for: range, resetIfMissing: resetView)
        errorMessage = nil
        isLoading = true
        refreshTask?.cancel()
        let snapshotLoader = self.snapshotLoader

        refreshTask = Task {
            do {
                let loadedSnapshot = try await Task.detached(priority: .userInitiated) {
                    try snapshotLoader(range)
                }.value
                guard !Task.isCancelled, selectedRange == range else {
                    return
                }
                snapshot = loadedSnapshot
                hasLoaded = true
                let updatedAt = Date()
                lastUpdated = updatedAt
                cacheSnapshot(loadedSnapshot, for: range, updatedAt: updatedAt)
            } catch {
                guard !Task.isCancelled, selectedRange == range else {
                    return
                }
                hasLoaded = false
                errorMessage = error.localizedDescription
            }
            if !Task.isCancelled, selectedRange == range {
                isLoading = false
            }
        }
    }

    private func primeVisibleSnapshot(for range: TokemonRange, resetIfMissing: Bool) {
        if let cachedSnapshot = cachedSnapshots[range] {
            snapshot = cachedSnapshot.snapshot
            lastUpdated = cachedSnapshot.lastUpdated
            return
        }
        if resetIfMissing {
            snapshot = .placeholder(for: range)
            lastUpdated = nil
        }
    }

    private func cacheSnapshot(_ snapshot: TokemonSnapshot, for range: TokemonRange, updatedAt: Date) {
        let cachedSnapshot = TokemonCachedSnapshot(range: range, lastUpdated: updatedAt, snapshot: snapshot)
        cachedSnapshots[range] = cachedSnapshot
        cache.save(cachedSnapshots)
    }
}

private enum TokemonRange: String, CaseIterable, Identifiable, Codable, Sendable {
    case today
    case week
    case month
    case year

    var id: String { rawValue }

    var title: String {
        switch self {
        case .today:
            return "Today"
        case .week:
            return "Last Week"
        case .month:
            return "Last Month"
        case .year:
            return "Last Year"
        }
    }

    var shortLabel: String {
        switch self {
        case .today:
            return "Today"
        case .week:
            return "Week"
        case .month:
            return "Month"
        case .year:
            return "Year"
        }
    }

    func makeRequest(now: Date = Date()) -> TokemonRequest {
        let calendar = TokemonCalendar.make()
        let today = calendar.startOfDay(for: now)

        switch self {
        case .today:
            let currentHour = TokemonCalendar.startOfHour(now, calendar: calendar)
            let bucketDates = TokemonCalendar.hourlyBuckets(from: today, through: currentHour, calendar: calendar)
            return TokemonRequest(
                cliArguments: [
                    TokemonDateFormatting.cliDateString(for: today),
                    TokemonDateFormatting.cliDateString(for: today),
                    "--sum-by",
                    "60",
                    "--format",
                    "json",
                    "--provider",
                    "all",
                ],
                subtitle: TokemonDateFormatting.longDayString(for: today),
                bucketDates: bucketDates
            )
        case .week:
            let start = calendar.date(byAdding: .day, value: -6, to: today) ?? today
            let bucketDates = TokemonCalendar.dailyBuckets(from: start, through: today, calendar: calendar)
            return TokemonRequest(
                cliArguments: [
                    TokemonDateFormatting.cliDateString(for: start),
                    TokemonDateFormatting.cliDateString(for: today),
                    "--sum-by",
                    "daily",
                    "--format",
                    "json",
                    "--provider",
                    "all",
                ],
                subtitle: TokemonDateFormatting.dateSpanString(start: start, end: today),
                bucketDates: bucketDates
            )
        case .month:
            let start = calendar.date(byAdding: .month, value: -1, to: today) ?? today
            let firstWeek = TokemonCalendar.startOfWeek(start, calendar: calendar)
            let lastWeek = TokemonCalendar.startOfWeek(today, calendar: calendar)
            let bucketDates = TokemonCalendar.weeklyBuckets(from: firstWeek, through: lastWeek, calendar: calendar)
            return TokemonRequest(
                cliArguments: [
                    TokemonDateFormatting.cliDateString(for: start),
                    TokemonDateFormatting.cliDateString(for: today),
                    "--sum-by",
                    "weekly",
                    "--format",
                    "json",
                    "--provider",
                    "all",
                ],
                subtitle: TokemonDateFormatting.dateSpanString(start: start, end: today),
                bucketDates: bucketDates
            )
        case .year:
            let currentMonth = TokemonCalendar.startOfMonth(today, calendar: calendar)
            let start = TokemonCalendar.startOfMonth(
                calendar.date(byAdding: .month, value: -11, to: currentMonth) ?? currentMonth,
                calendar: calendar
            )
            let bucketDates = TokemonCalendar.monthlyBuckets(from: start, through: currentMonth, calendar: calendar)
            return TokemonRequest(
                cliArguments: [
                    TokemonDateFormatting.cliDateString(for: start),
                    TokemonDateFormatting.cliDateString(for: today),
                    "--sum-by",
                    "monthly",
                    "--format",
                    "json",
                    "--provider",
                    "all",
                ],
                subtitle: TokemonDateFormatting.monthSpanString(start: start, end: currentMonth),
                bucketDates: bucketDates
            )
        }
    }

    func normalizeBucket(_ date: Date) -> Date {
        let calendar = TokemonCalendar.make()
        switch self {
        case .today:
            return TokemonCalendar.startOfHour(date, calendar: calendar)
        case .week:
            return calendar.startOfDay(for: date)
        case .month:
            return TokemonCalendar.startOfWeek(date, calendar: calendar)
        case .year:
            return TokemonCalendar.startOfMonth(date, calendar: calendar)
        }
    }

    func axisMarkDates(for buckets: [TokemonBucket]) -> [Date] {
        switch self {
        case .today:
            return buckets.enumerated().compactMap { index, bucket in
                if index == 0 || index == buckets.count - 1 || index % 4 == 0 {
                    return bucket.date
                }
                return nil
            }
        case .week, .month, .year:
            return buckets.map(\.date)
        }
    }

    func axisLabel(for date: Date) -> String {
        let calendar = TokemonCalendar.make()
        switch self {
        case .today:
            let hour = calendar.component(.hour, from: date)
            let suffix = hour >= 12 ? "p" : "a"
            let normalized = hour % 12 == 0 ? 12 : hour % 12
            return "\(normalized)\(suffix)"
        case .week:
            return TokemonDateFormatting.shortWeekdayString(for: date, calendar: calendar)
        case .month:
            return TokemonDateFormatting.weekBucketString(for: date)
        case .year:
            return TokemonDateFormatting.shortMonthString(for: date, calendar: calendar)
        }
    }
}

private struct TokemonRequest {
    let cliArguments: [String]
    let subtitle: String
    let bucketDates: [Date]
}

private struct TokemonSnapshot: Codable, Sendable {
    let subtitle: String
    let buckets: [TokemonBucket]
    let axisMarkDates: [Date]
    let totalTokens: Int
    let maxTokens: Int

    static func placeholder(for range: TokemonRange, now: Date = Date()) -> TokemonSnapshot {
        let request = range.makeRequest(now: now)
        let buckets = request.bucketDates.map { TokemonBucket(date: $0, totalTokens: 0) }
        return TokemonSnapshot(
            subtitle: request.subtitle,
            buckets: buckets,
            axisMarkDates: range.axisMarkDates(for: buckets),
            totalTokens: 0,
            maxTokens: 1
        )
    }

    static func load(for range: TokemonRange, now: Date = Date()) throws -> TokemonSnapshot {
        let request = range.makeRequest(now: now)
        let payload = try TokemonCommandRunner.fetchUsage(arguments: request.cliArguments)
        let totalsByBucket = payload.rows.reduce(into: [Date: Int]()) { partialResult, row in
            guard let bucketDate = TokemonDateFormatting.parseBucketString(row.bucket) else {
                return
            }
            let normalized = range.normalizeBucket(bucketDate)
            partialResult[normalized, default: 0] += row.totalTokens
        }
        let buckets = request.bucketDates.map { bucketDate in
            TokemonBucket(date: bucketDate, totalTokens: totalsByBucket[bucketDate, default: 0])
        }
        let totalTokens = buckets.reduce(into: 0) { partialResult, bucket in
            partialResult += bucket.totalTokens
        }
        let maxTokens = max(buckets.map(\.totalTokens).max() ?? 0, 1)
        return TokemonSnapshot(
            subtitle: request.subtitle,
            buckets: buckets,
            axisMarkDates: range.axisMarkDates(for: buckets),
            totalTokens: totalTokens,
            maxTokens: maxTokens
        )
    }
}

private struct TokemonCachedSnapshot: Codable {
    let range: TokemonRange
    let lastUpdated: Date
    let snapshot: TokemonSnapshot
}

private struct TokemonSnapshotCacheFile: Codable {
    let version: Int
    let entries: [TokemonCachedSnapshot]
}

private struct TokemonSnapshotCache {
    let fileURL: URL

    static func live() -> TokemonSnapshotCache {
        TokemonSnapshotCache(fileURL: defaultFileURL())
    }

    func load() -> [TokemonRange: TokemonCachedSnapshot] {
        guard let data = try? Data(contentsOf: fileURL) else {
            return [:]
        }
        guard let cacheFile = try? Self.makeDecoder().decode(TokemonSnapshotCacheFile.self, from: data) else {
            return [:]
        }
        guard cacheFile.version == tokemonSnapshotCacheFormatVersion else {
            return [:]
        }

        var snapshots: [TokemonRange: TokemonCachedSnapshot] = [:]
        for entry in cacheFile.entries {
            snapshots[entry.range] = entry
        }
        return snapshots
    }

    func save(_ entries: [TokemonRange: TokemonCachedSnapshot]) {
        let cacheFile = TokemonSnapshotCacheFile(
            version: tokemonSnapshotCacheFormatVersion,
            entries: Array(entries.values).sorted { $0.range.rawValue < $1.range.rawValue }
        )
        do {
            let data = try Self.makeEncoder().encode(cacheFile)
            try FileManager.default.createDirectory(
                at: fileURL.deletingLastPathComponent(),
                withIntermediateDirectories: true,
                attributes: nil
            )
            try data.write(to: fileURL, options: .atomic)
        } catch {
            return
        }
    }

    private static func defaultFileURL() -> URL {
        let environment = ProcessInfo.processInfo.environment
        if let overridePath = environment["TOKEMON_MENUAPP_CACHE_PATH"], !overridePath.isEmpty {
            return URL(fileURLWithPath: overridePath)
        }
        if let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first {
            return appSupport
                .appendingPathComponent("Tokemon", isDirectory: true)
                .appendingPathComponent("snapshot-cache.json")
        }
        return URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("tokemon-snapshot-cache.json")
    }

    private static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }

    private static func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }
}

private struct TokemonBucket: Identifiable, Codable, Sendable {
    let date: Date
    let totalTokens: Int

    var id: TimeInterval { date.timeIntervalSince1970 }
}

private struct TokemonPayload: Decodable {
    let rows: [TokemonRow]
}

private struct TokemonRow: Decodable {
    let bucket: String
    let totalTokens: Int

    enum CodingKeys: String, CodingKey {
        case bucket
        case totalTokens = "total_tokens"
    }
}

private enum TokemonCommandRunner {
    static func fetchUsage(arguments: [String]) throws -> TokemonPayload {
        guard
            let resourceRoot = Bundle.main.resourceURL
        else {
            throw TokemonError("Tokemon CLI was not bundled into the app.")
        }
        let scriptURL = resourceRoot.appendingPathComponent("bin/tokemon")

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [scriptURL.path] + arguments

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        var stdoutData = Data()
        var stderrData = Data()
        let drainGroup = DispatchGroup()

        drainGroup.enter()
        DispatchQueue.global(qos: .userInitiated).async {
            stdoutData = stdout.fileHandleForReading.readDataToEndOfFile()
            drainGroup.leave()
        }

        drainGroup.enter()
        DispatchQueue.global(qos: .utility).async {
            stderrData = stderr.fileHandleForReading.readDataToEndOfFile()
            drainGroup.leave()
        }

        try process.run()
        process.waitUntilExit()
        drainGroup.wait()

        if process.terminationStatus != 0 {
            let message = String(data: stderrData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
            throw TokemonError(message?.isEmpty == false ? message! : "Tokemon CLI exited with code \(process.terminationStatus).")
        }

        do {
            return try JSONDecoder().decode(TokemonPayload.self, from: stdoutData)
        } catch {
            throw TokemonError("Tokemon app could not decode CLI output: \(error.localizedDescription)")
        }
    }
}

private enum TokemonCalendar {
    static func make() -> Calendar {
        var calendar = Calendar.autoupdatingCurrent
        calendar.firstWeekday = 1
        return calendar
    }

    static func startOfHour(_ date: Date, calendar: Calendar) -> Date {
        let components = calendar.dateComponents([.year, .month, .day, .hour], from: date)
        return calendar.date(from: components) ?? date
    }

    static func startOfWeek(_ date: Date, calendar: Calendar) -> Date {
        let midnight = calendar.startOfDay(for: date)
        let weekday = calendar.component(.weekday, from: midnight)
        return calendar.date(byAdding: .day, value: -(weekday - 1), to: midnight) ?? midnight
    }

    static func startOfMonth(_ date: Date, calendar: Calendar) -> Date {
        let components = calendar.dateComponents([.year, .month], from: date)
        return calendar.date(from: components) ?? date
    }

    static func hourlyBuckets(from start: Date, through end: Date, calendar: Calendar) -> [Date] {
        var dates: [Date] = []
        var current = start
        while current <= end {
            dates.append(current)
            current = calendar.date(byAdding: .hour, value: 1, to: current) ?? current.addingTimeInterval(3600)
        }
        return dates
    }

    static func dailyBuckets(from start: Date, through end: Date, calendar: Calendar) -> [Date] {
        var dates: [Date] = []
        var current = start
        while current <= end {
            dates.append(current)
            current = calendar.date(byAdding: .day, value: 1, to: current) ?? current.addingTimeInterval(86_400)
        }
        return dates
    }

    static func weeklyBuckets(from start: Date, through end: Date, calendar: Calendar) -> [Date] {
        var dates: [Date] = []
        var current = start
        while current <= end {
            dates.append(current)
            current = calendar.date(byAdding: .day, value: 7, to: current) ?? current.addingTimeInterval(604_800)
        }
        return dates
    }

    static func monthlyBuckets(from start: Date, through end: Date, calendar: Calendar) -> [Date] {
        var dates: [Date] = []
        var current = start
        while current <= end {
            dates.append(current)
            current = startOfMonth(calendar.date(byAdding: .month, value: 1, to: current) ?? current, calendar: calendar)
        }
        return dates
    }
}

private enum TokemonDateFormatting {
    static func cliDateString(for date: Date) -> String {
        formatter("yyyy-MM-dd").string(from: date)
    }

    static func longDayString(for date: Date) -> String {
        formatter("MMM d, yyyy").string(from: date)
    }

    static func shortWeekdayString(for date: Date, calendar: Calendar) -> String {
        let weekday = calendar.component(.weekday, from: date)
        return calendar.shortWeekdaySymbols[max(0, min(calendar.shortWeekdaySymbols.count - 1, weekday - 1))]
    }

    static func shortMonthString(for date: Date, calendar: Calendar) -> String {
        let month = calendar.component(.month, from: date)
        return calendar.shortMonthSymbols[max(0, min(calendar.shortMonthSymbols.count - 1, month - 1))]
    }

    static func weekBucketString(for date: Date) -> String {
        formatter("MMM d").string(from: date)
    }

    static func dateSpanString(start: Date, end: Date) -> String {
        "\(formatter("MMM d").string(from: start)) - \(formatter("MMM d, yyyy").string(from: end))"
    }

    static func monthSpanString(start: Date, end: Date) -> String {
        "\(formatter("MMM yyyy").string(from: start)) - \(formatter("MMM yyyy").string(from: end))"
    }

    static func clockString(for date: Date) -> String {
        formatter("h:mm a").string(from: date)
    }

    static func parseBucketString(_ raw: String) -> Date? {
        formatter("yyyy-MM-dd'T'HH:mmXXXXX").date(from: raw)
    }

    private static func formatter(_ format: String) -> DateFormatter {
        let formatter = DateFormatter()
        formatter.calendar = TokemonCalendar.make()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = .autoupdatingCurrent
        formatter.dateFormat = format
        return formatter
    }
}

private struct TokemonError: LocalizedError {
    let message: String

    init(_ message: String) {
        self.message = message
    }

    var errorDescription: String? { message }
}

private extension Int {
    var abbreviatedTokenString: String {
        if self >= 1_000_000 {
            return String(format: "%.1fM", Double(self) / 1_000_000.0)
        }
        if self >= 1_000 {
            return String(format: "%.1fk", Double(self) / 1_000.0)
        }
        return formatted()
    }
}

#if TOKEMON_TESTING
enum TokemonMenuAppTestSupport {
    @MainActor
    static func runCacheScenario(cacheFileURL: URL) async throws -> String {
        let now = Date(timeIntervalSince1970: 1_708_300_800)
        let cache = TokemonSnapshotCache(fileURL: cacheFileURL)
        cache.save(
            [
                .today: TokemonCachedSnapshot(
                    range: .today,
                    lastUpdated: now.addingTimeInterval(-900),
                    snapshot: TokemonSnapshot.fixture(for: .today, totalTokens: 111, now: now)
                ),
                .week: TokemonCachedSnapshot(
                    range: .week,
                    lastUpdated: now.addingTimeInterval(-600),
                    snapshot: TokemonSnapshot.fixture(for: .week, totalTokens: 222, now: now)
                ),
            ]
        )

        let store = TokemonStore(
            cache: cache,
            snapshotLoader: { range in
                Thread.sleep(forTimeInterval: 0.15)
                switch range {
                case .today:
                    return TokemonSnapshot.fixture(for: .today, totalTokens: 333, now: now)
                case .week:
                    return TokemonSnapshot.fixture(for: .week, totalTokens: 444, now: now)
                case .month:
                    return TokemonSnapshot.fixture(for: .month, totalTokens: 555, now: now)
                case .year:
                    return TokemonSnapshot.fixture(for: .year, totalTokens: 666, now: now)
                }
            }
        )

        let initialToday = store.snapshot.totalTokens
        let initialHasTimestamp = store.lastUpdated == nil ? 0 : 1

        store.ensureLoaded()
        let loadingToday = store.isLoading ? 1 : 0
        let staleToday = store.snapshot.totalTokens
        try await waitUntilIdle(store)
        let freshToday = store.snapshot.totalTokens

        store.selectRange(.week)
        let loadingWeek = store.isLoading ? 1 : 0
        let staleWeek = store.snapshot.totalTokens
        try await waitUntilIdle(store)
        let freshWeek = store.snapshot.totalTokens

        let reopenedStore = TokemonStore(
            cache: cache,
            snapshotLoader: { _ in TokemonSnapshot.fixture(for: .today, totalTokens: 999, now: now) }
        )

        let payload: [String: Int] = [
            "fresh_today": freshToday,
            "fresh_week": freshWeek,
            "initial_has_timestamp": initialHasTimestamp,
            "initial_today": initialToday,
            "loading_today": loadingToday,
            "loading_week": loadingWeek,
            "reopened_has_timestamp": reopenedStore.lastUpdated == nil ? 0 : 1,
            "reopened_today": reopenedStore.snapshot.totalTokens,
            "stale_today": staleToday,
            "stale_week": staleWeek,
        ]
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        return String(decoding: data, as: UTF8.self)
    }

    @MainActor
    private static func waitUntilIdle(_ store: TokemonStore) async throws {
        for _ in 0..<200 {
            if !store.isLoading {
                return
            }
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        throw TokemonError("Timed out waiting for Tokemon refresh.")
    }
}

private extension TokemonSnapshot {
    static func fixture(for range: TokemonRange, totalTokens: Int, now: Date) -> TokemonSnapshot {
        let request = range.makeRequest(now: now)
        var buckets = request.bucketDates.map { TokemonBucket(date: $0, totalTokens: 0) }
        if let lastIndex = buckets.indices.last {
            let bucket = buckets[lastIndex]
            buckets[lastIndex] = TokemonBucket(date: bucket.date, totalTokens: totalTokens)
        }
        return TokemonSnapshot(
            subtitle: request.subtitle,
            buckets: buckets,
            axisMarkDates: range.axisMarkDates(for: buckets),
            totalTokens: totalTokens,
            maxTokens: max(totalTokens, 1)
        )
    }
}
#endif
