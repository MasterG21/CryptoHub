import SwiftUI

struct StatusBadge: View {
    let status: BookingStatus

    private var color: Color {
        switch status {
        case .pending: return PCColor.pending
        case .accepted: return PCColor.success
        case .completed: return Color(hex: "0B5CAD")
        case .declined, .cancelled: return PCColor.danger
        }
    }

    var body: some View {
        Text(status.label)
            .font(.caption.bold())
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(color.opacity(0.15))
            .foregroundColor(color)
            .clipShape(Capsule())
    }
}

struct RatingLabel: View {
    let average: Double?
    let count: Int

    var body: some View {
        if let average, count > 0 {
            Label("\(average, specifier: "%.1f") (\(count) review\(count == 1 ? "" : "s"))", systemImage: "star.fill")
                .font(.subheadline.bold())
                .foregroundColor(Color(hex: "D99A00"))
        } else {
            Text("No reviews yet")
                .font(.subheadline)
                .foregroundColor(PCColor.textMuted)
        }
    }
}
