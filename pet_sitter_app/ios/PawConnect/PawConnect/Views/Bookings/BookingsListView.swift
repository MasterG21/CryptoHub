import SwiftUI

struct BookingsListView: View {
    @EnvironmentObject var session: SessionStore
    @StateObject private var viewModel = BookingsViewModel()

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.bookings.isEmpty {
                ProgressView()
            } else if let error = viewModel.errorMessage, viewModel.bookings.isEmpty {
                Text(error).foregroundColor(PCColor.danger).padding()
            } else if viewModel.bookings.isEmpty {
                Text("No bookings yet.").foregroundColor(PCColor.textMuted).padding()
            } else {
                List(viewModel.bookings) { booking in
                    NavigationLink(value: booking) {
                        BookingRow(booking: booking)
                    }
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("My Bookings")
        .navigationDestination(for: Booking.self) { booking in
            BookingDetailView(initialBooking: booking)
        }
        .task { if let token = session.token { await viewModel.load(token: token) } }
        .refreshable { if let token = session.token { await viewModel.load(token: token) } }
    }
}

struct BookingRow: View {
    let booking: Booking
    @EnvironmentObject var session: SessionStore

    private var counterparty: UserOut {
        session.user?.id == booking.sitter.id ? booking.owner : booking.sitter
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("\(booking.serviceType.label) with \(counterparty.fullName)").font(.headline)
                Spacer()
                StatusBadge(status: booking.status)
            }
            Text("\(booking.startDate) → \(booking.endDate)").font(.caption).foregroundColor(PCColor.textMuted)
        }
        .padding(.vertical, 4)
    }
}

extension Booking: Hashable {
    static func == (lhs: Booking, rhs: Booking) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}
