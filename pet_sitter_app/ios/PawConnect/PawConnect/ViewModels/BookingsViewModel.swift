import Foundation

@MainActor
final class BookingsViewModel: ObservableObject {
    @Published private(set) var bookings: [Booking] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    func load(token: String) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            bookings = try await APIService.listMyBookings(token: token)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @discardableResult
    func updateStatus(bookingId: Int, status: BookingStatus, token: String) async -> Booking? {
        do {
            let updated = try await APIService.updateBookingStatus(id: bookingId, status: status, token: token)
            if let index = bookings.firstIndex(where: { $0.id == updated.id }) {
                bookings[index] = updated
            }
            return updated
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }
}

@MainActor
final class MessagesViewModel: ObservableObject {
    @Published private(set) var messages: [Message] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var isSending = false

    func load(bookingId: Int, token: String) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            messages = try await APIService.listMessages(bookingId: bookingId, token: token)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func send(bookingId: Int, body: String, token: String) async {
        let trimmed = body.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        isSending = true
        errorMessage = nil
        defer { isSending = false }
        do {
            let message = try await APIService.sendMessage(bookingId: bookingId, body: trimmed, token: token)
            messages.append(message)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
