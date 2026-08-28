import SwiftUI

extension Color {
    init(hex: String) {
        let scanner = Scanner(string: hex.trimmingCharacters(in: CharacterSet(charactersIn: "#")))
        var rgb: UInt64 = 0
        scanner.scanHexInt64(&rgb)
        self.init(
            red: Double((rgb >> 16) & 0xFF) / 255,
            green: Double((rgb >> 8) & 0xFF) / 255,
            blue: Double(rgb & 0xFF) / 255
        )
    }
}

enum PCColor {
    static let accent = Color(hex: "FF7A45")
    static let accentDark = Color(hex: "E35F2B")
    static let background = Color(hex: "FAF7F2")
    static let card = Color.white
    static let border = Color(hex: "E7DED4")
    static let textPrimary = Color(hex: "2B2320")
    static let textMuted = Color(hex: "7A6F66")
    static let success = Color(hex: "2E7D32")
    static let danger = Color(hex: "C62828")
    static let pending = Color(hex: "B8860B")
}

struct CardBackground: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding()
            .background(PCColor.card)
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(PCColor.border, lineWidth: 1)
            )
    }
}

extension View {
    func cardStyle() -> some View { modifier(CardBackground()) }
}
