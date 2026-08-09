import SwiftUI

struct HistoryView: View {
    @ObservedObject var store: PomodoroStore
    @State private var displayedMonth: Date

    private let calendar: Calendar
    private let accent = Color(red: 0.09, green: 0.72, blue: 0.57)
    private let surface = Color(red: 0.055, green: 0.063, blue: 0.071)

    init(store: PomodoroStore, calendar: Calendar = .current) {
        self.store = store
        self.calendar = calendar
        _displayedMonth = State(initialValue: Self.monthStart(for: Date(), calendar: calendar))
    }

    var body: some View {
        VStack(spacing: 0) {
            header

            VStack(spacing: 18) {
                summary
                monthNavigation
                calendarGrid

                if let error = store.errorMessage {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(.system(size: 10, weight: .medium, design: .monospaced))
                        .foregroundStyle(.orange)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Label(
                    "Each marker is a completed focus block.",
                    systemImage: "checkmark.circle"
                )
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(22)
        }
        .frame(minWidth: 500, minHeight: 560)
        .background(surface)
        .foregroundStyle(.white)
    }

    private var header: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(accent.opacity(0.16))
                Image(systemName: "calendar.badge.checkmark")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(accent)
            }
            .frame(width: 38, height: 38)

            VStack(alignment: .leading, spacing: 2) {
                Text("FOCUS HISTORY")
                    .font(.system(size: 15, weight: .bold, design: .monospaced))
                    .tracking(1.2)
                Text("COMPLETED POMODOROS BY DAY")
                    .font(.system(size: 9, weight: .medium, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .tracking(0.8)
            }

            Spacer()
        }
        .padding(.horizontal, 22)
        .padding(.vertical, 18)
        .background(Color.black.opacity(0.2))
        .overlay(alignment: .bottom) {
            Rectangle().fill(Color.white.opacity(0.06)).frame(height: 1)
        }
    }

    private var summary: some View {
        let counts = store.dailyCounts(in: displayedMonth, calendar: calendar)
        let total = counts.values.reduce(0, +)
        let activeDays = counts.values.filter { $0 > 0 }.count
        let bestDay = counts.values.max() ?? 0

        return HStack(spacing: 10) {
            summaryCard(value: "\(total)", label: "TOTAL")
            summaryCard(value: "\(activeDays)", label: "ACTIVE DAYS")
            summaryCard(value: "\(bestDay)", label: "BEST DAY")
        }
    }

    private func summaryCard(value: String, label: String) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(value)
                .font(.system(size: 23, weight: .bold, design: .monospaced))
                .foregroundStyle(accent)
            Text(label)
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .foregroundStyle(.secondary)
                .tracking(0.8)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 11, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .stroke(Color.white.opacity(0.06), lineWidth: 1)
        )
    }

    private var monthNavigation: some View {
        HStack {
            monthButton(systemName: "chevron.left", offset: -1)

            Spacer()

            Text(monthTitle)
                .font(.system(size: 16, weight: .bold, design: .monospaced))

            Spacer()

            monthButton(systemName: "chevron.right", offset: 1)
        }
    }

    private func monthButton(systemName: String, offset: Int) -> some View {
        Button {
            guard let month = calendar.date(byAdding: .month, value: offset, to: displayedMonth) else { return }
            displayedMonth = month
        } label: {
            Image(systemName: systemName)
                .font(.system(size: 11, weight: .bold))
                .frame(width: 30, height: 30)
                .background(Color.white.opacity(0.06), in: Circle())
        }
        .buttonStyle(.plain)
    }

    private var calendarGrid: some View {
        let columns = Array(repeating: GridItem(.flexible(), spacing: 7), count: 7)
        let counts = store.dailyCounts(in: displayedMonth, calendar: calendar)

        return VStack(spacing: 9) {
            LazyVGrid(columns: columns, spacing: 7) {
                ForEach(weekdaySymbols, id: \.self) { weekday in
                    Text(weekday.uppercased())
                        .font(.system(size: 9, weight: .bold, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                }
            }

            LazyVGrid(columns: columns, spacing: 7) {
                ForEach(calendarCells) { cell in
                    if let date = cell.date {
                        dayCell(date: date, count: counts[calendar.startOfDay(for: date), default: 0])
                    } else {
                        Color.clear.frame(height: 58)
                    }
                }
            }
        }
    }

    private func dayCell(date: Date, count: Int) -> some View {
        let isToday = calendar.isDateInToday(date)
        let intensity = count == 0 ? 0 : Swift.min(0.12 + (Double(count) * 0.08), 0.58)

        return VStack(alignment: .leading, spacing: 6) {
            Text("\(calendar.component(.day, from: date))")
                .font(.system(size: 11, weight: isToday ? .bold : .medium, design: .monospaced))
                .foregroundStyle(isToday ? accent : .white.opacity(0.78))

            Spacer(minLength: 0)

            if count > 0 {
                HStack(spacing: 4) {
                    Circle().fill(accent).frame(width: 5, height: 5)
                    Text("\(count)")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                }
                .foregroundStyle(accent)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 42, alignment: .topLeading)
        .padding(8)
        .background(
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .fill(count > 0 ? accent.opacity(intensity) : Color.white.opacity(0.035))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .stroke(isToday ? accent.opacity(0.75) : Color.white.opacity(0.05), lineWidth: isToday ? 1.5 : 1)
        )
    }

    private var monthTitle: String {
        let formatter = DateFormatter()
        formatter.calendar = calendar
        formatter.locale = .current
        formatter.dateFormat = "LLLL yyyy"
        return formatter.string(from: displayedMonth)
    }

    private var weekdaySymbols: [String] {
        let formatter = DateFormatter()
        formatter.locale = .current
        guard let symbols = formatter.veryShortStandaloneWeekdaySymbols, symbols.count == 7 else {
            return ["S", "M", "T", "W", "T", "F", "S"]
        }
        let firstIndex = calendar.firstWeekday - 1
        return Array(symbols[firstIndex...] + symbols[..<firstIndex])
    }

    private var calendarCells: [CalendarCell] {
        guard
            let dayRange = calendar.range(of: .day, in: .month, for: displayedMonth),
            let firstDay = calendar.date(from: calendar.dateComponents([.year, .month], from: displayedMonth))
        else { return [] }

        let firstWeekday = calendar.component(.weekday, from: firstDay)
        let leadingBlanks = (firstWeekday - calendar.firstWeekday + 7) % 7
        var cells = (0..<leadingBlanks).map { CalendarCell(id: $0, date: nil) }

        for day in dayRange {
            let date = calendar.date(byAdding: .day, value: day - 1, to: firstDay)
            cells.append(CalendarCell(id: cells.count, date: date))
        }
        while cells.count % 7 != 0 {
            cells.append(CalendarCell(id: cells.count, date: nil))
        }
        return cells
    }

    private static func monthStart(for date: Date, calendar: Calendar) -> Date {
        calendar.date(from: calendar.dateComponents([.year, .month], from: date)) ?? date
    }
}

private struct CalendarCell: Identifiable {
    let id: Int
    let date: Date?
}
