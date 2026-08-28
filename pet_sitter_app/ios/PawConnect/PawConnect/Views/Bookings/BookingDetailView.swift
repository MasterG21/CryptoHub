import SwiftUI

struct BookingDetailView: View {
    @State private var booking: Booking
    @EnvironmentObject var session: SessionStore
    @StateObject private var viewModel = BookingsViewModel()
    @State private var errorMessage: String?
    @State private var showReportUserSheet = false

    init(initialBooking: Booking) {
        _booking = State(initialValue: initialBooking)
    }

    private var isSitter: Bool { session.user?.id == booking.sitter.id }
    private var counterparty: UserOut { isSitter ? booking.owner : booking.sitter }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header

                if let errorMessage {
                    Text(errorMessage).foregroundColor(PCColor.danger).cardStyle()
                }

                actionButtons

                if booking.status == .completed && !isSitter {
                    ReviewFormView(bookingId: booking.id)
                }

                MessagesView(bookingId: booking.id).cardStyle()
            }
            .padding()
        }
        .background(PCColor.background.ignoresSafeArea())
        .navigationTitle("\(booking.serviceType.label)")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showReportUserSheet) {
            ReportSheet(targetType: .user, targetId: counterparty.id)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("\(booking.serviceType.label) with \(counterparty.fullName)").font(.headline)
                Spacer()
                StatusBadge(status: booking.status)
            }
            Text("\(booking.startDate) → \(booking.endDate)").foregroundColor(PCColor.textMuted)
            if let pet = booking.pet {
                Text("Pet: \(pet.name) (\(pet.species))")
            }
            if !booking.notes.isEmpty {
                Text(booking.notes)
            }
            Button("Report \(counterparty.fullName)") { showReportUserSheet = true }
                .font(.caption)
                .foregroundColor(PCColor.danger)
        }
        .cardStyle()
    }

    @ViewBuilder
    private var actionButtons: some View {
        HStack(spacing: 10) {
            if booking.status == .pending {
                if isSitter {
                    actionButton("Accept", status: .accepted, tint: PCColor.success)
                    actionButton("Decline", status: .declined, tint: PCColor.danger)
                } else {
                    actionButton("Cancel request", status: .cancelled, tint: PCColor.danger)
                }
            } else if booking.status == .accepted {
                actionButton("Cancel", status: .cancelled, tint: PCColor.danger)
                if isSitter {
                    actionButton("Mark completed", status: .completed, tint: PCColor.success)
                }
            }
        }
    }

    private func actionButton(_ title: String, status: BookingStatus, tint: Color) -> some View {
        Button(title) {
            Task {
                guard let token = session.token else { return }
                if let updated = await viewModel.updateStatus(bookingId: booking.id, status: status, token: token) {
                    booking = updated
                    errorMessage = nil
                } else {
                    errorMessage = viewModel.errorMessage
                }
            }
        }
        .buttonStyle(.bordered)
        .tint(tint)
    }
}
