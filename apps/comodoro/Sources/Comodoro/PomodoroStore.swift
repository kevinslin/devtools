import Combine
import Foundation
import SQLite3

@MainActor
final class PomodoroStore: ObservableObject {
    @Published private(set) var revision = 0
    @Published private(set) var errorMessage: String?

    let databaseURL: URL
    nonisolated(unsafe) private var database: OpaquePointer?

    init(databaseURL: URL? = nil) {
        self.databaseURL = databaseURL ?? Self.defaultDatabaseURL()
        openDatabase()
    }

    deinit {
        if let database {
            sqlite3_close(database)
        }
    }

    func recordCompletedPomodoro(
        at date: Date,
        duration: TimeInterval,
        cycle: Int,
        totalCycles: Int
    ) {
        guard let database else { return }
        let sql = """
            INSERT OR IGNORE INTO pomodoros
                (completion_millisecond, completed_at, duration_seconds, cycle_number, total_cycles)
            VALUES (?, ?, ?, ?, ?);
            """
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK else {
            reportDatabaseError()
            return
        }
        defer { sqlite3_finalize(statement) }

        let completionMillisecond = Int64((date.timeIntervalSince1970 * 1_000).rounded())
        sqlite3_bind_int64(statement, 1, completionMillisecond)
        sqlite3_bind_double(statement, 2, date.timeIntervalSince1970)
        sqlite3_bind_int64(statement, 3, Int64(duration.rounded()))
        sqlite3_bind_int(statement, 4, Int32(cycle))
        sqlite3_bind_int(statement, 5, Int32(totalCycles))

        guard sqlite3_step(statement) == SQLITE_DONE else {
            reportDatabaseError()
            return
        }
        if sqlite3_changes(database) > 0 {
            revision += 1
        }
    }

    func dailyCounts(in month: Date, calendar: Calendar = .current) -> [Date: Int] {
        guard
            let database,
            let interval = calendar.dateInterval(of: .month, for: month)
        else { return [:] }

        let sql = """
            SELECT completed_at
            FROM pomodoros
            WHERE completed_at >= ? AND completed_at < ?
            ORDER BY completed_at ASC;
            """
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK else {
            reportDatabaseError()
            return [:]
        }
        defer { sqlite3_finalize(statement) }

        sqlite3_bind_double(statement, 1, interval.start.timeIntervalSince1970)
        sqlite3_bind_double(statement, 2, interval.end.timeIntervalSince1970)

        var counts: [Date: Int] = [:]
        while sqlite3_step(statement) == SQLITE_ROW {
            let completedAt = Date(timeIntervalSince1970: sqlite3_column_double(statement, 0))
            counts[calendar.startOfDay(for: completedAt), default: 0] += 1
        }
        return counts
    }

    private func openDatabase() {
        do {
            try FileManager.default.createDirectory(
                at: databaseURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
        } catch {
            errorMessage = "Could not create the history folder: \(error.localizedDescription)"
            return
        }

        guard sqlite3_open(databaseURL.path, &database) == SQLITE_OK else {
            reportDatabaseError(prefix: "Could not open history")
            return
        }

        let schema = """
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS pomodoros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                completion_millisecond INTEGER NOT NULL UNIQUE,
                completed_at REAL NOT NULL,
                duration_seconds INTEGER NOT NULL,
                cycle_number INTEGER NOT NULL,
                total_cycles INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS pomodoros_completed_at_idx
                ON pomodoros(completed_at);
            """
        guard sqlite3_exec(database, schema, nil, nil, nil) == SQLITE_OK else {
            reportDatabaseError(prefix: "Could not prepare history")
            return
        }
    }

    private func reportDatabaseError(prefix: String = "History database error") {
        let detail = database.flatMap { sqlite3_errmsg($0) }.map(String.init(cString:)) ?? "Unknown error"
        errorMessage = "\(prefix): \(detail)"
    }

    private static func defaultDatabaseURL() -> URL {
        let applicationSupport = FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
        return applicationSupport
            .appendingPathComponent("Comodoro", isDirectory: true)
            .appendingPathComponent("history.sqlite3")
    }
}
