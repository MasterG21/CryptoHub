import Foundation

@MainActor
final class SitterDetailViewModel: ObservableObject {
    @Published private(set) var sitter: SitterProfile?
    @Published private(set) var reviews: [Review] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var bookingSuccessMessage: String?
    @Published var isSubmittingBooking = false

    func load(userId: Int) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            async let sitterTask = APIService.getSitter(userId: userId)
            async let reviewsTask = APIService.sitterReviews(userId: userId)
            sitter = try await sitterTask
            reviews = try await reviewsTask
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func requestBooking(
        sitterId: Int, petId: Int?, service: ServiceType, start: Date, end: Date, notes: String, token: String
    ) async -> Bool {
        isSubmittingBooking = true
        errorMessage = nil
        bookingSuccessMessage = nil
        defer { isSubmittingBooking = false }
        do {
            _ = try await APIService.createBooking(
                BookingCreateRequest(
                    sitterId: sitterId,
                    petId: petId,
                    serviceType: service,
                    startDate: DateFormatting.string(from: start),
                    endDate: DateFormatting.string(from: end),
                    notes: notes
                ),
                token: token
            )
            bookingSuccessMessage = "Booking request sent!"
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
}
