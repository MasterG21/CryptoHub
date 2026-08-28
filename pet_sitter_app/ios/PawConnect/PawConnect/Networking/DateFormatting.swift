import Foundation

enum DateFormatting {
    /// The backend's `date` fields are plain ISO "yyyy-MM-dd" strings.
    static let isoDate: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()

    static func string(from date: Date) -> String {
        isoDate.string(from: date)
    }

    static func date(from string: String) -> Date? {
        isoDate.date(from: string)
    }

    /// Backend `created_at` timestamps come from Python's `datetime.utcnow().isoformat()`,
    /// which has no timezone designator (e.g. "2026-08-28T12:34:56.789123"), so try both
    /// the strict ISO 8601 parser (in case a "Z" is ever added) and naive fallback formats.
    private static let naiveFormats = ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss"]

    static func displayDateTime(_ isoString: String) -> String {
        let strict = ISO8601DateFormatter()
        strict.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var date = strict.date(from: isoString)
        if date == nil {
            strict.formatOptions = [.withInternetDateTime]
            date = strict.date(from: isoString)
        }
        if date == nil {
            for format in naiveFormats {
                let formatter = DateFormatter()
                formatter.locale = Locale(identifier: "en_US_POSIX")
                formatter.timeZone = TimeZone(identifier: "UTC")
                formatter.dateFormat = format
                if let parsed = formatter.date(from: isoString) {
                    date = parsed
                    break
                }
            }
        }
        guard let date else { return isoString }
        let display = DateFormatter()
        display.dateStyle = .medium
        display.timeStyle = .short
        return display.string(from: date)
    }
}
