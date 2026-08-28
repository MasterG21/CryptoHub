import Foundation

/// Typed convenience wrappers around APIClient, one per backend endpoint.
/// Mirrors pet_sitter_app/frontend/app.js's `api()` call sites.
enum APIService {
    // MARK: Auth

    static func register(_ payload: RegisterRequest) async throws -> Token {
        try await APIClient.shared.request("/api/auth/register", method: "POST", body: payload)
    }

    static func login(_ payload: LoginRequest) async throws -> Token {
        try await APIClient.shared.request("/api/auth/login", method: "POST", body: payload)
    }

    static func me(token: String) async throws -> UserOut {
        try await APIClient.shared.request("/api/auth/me", token: token)
    }

    // MARK: Sitters

    static func listSitters(city: String?, service: ServiceType?, petType: String?, maxRate: Double?) async throws -> [SitterProfile] {
        var query: [URLQueryItem] = []
        if let city, !city.isEmpty { query.append(URLQueryItem(name: "city", value: city)) }
        if let service { query.append(URLQueryItem(name: "service", value: service.rawValue)) }
        if let petType, !petType.isEmpty { query.append(URLQueryItem(name: "pet_type", value: petType)) }
        if let maxRate { query.append(URLQueryItem(name: "max_rate", value: String(maxRate))) }
        return try await APIClient.shared.request("/api/sitters", query: query)
    }

    static func getSitter(userId: Int) async throws -> SitterProfile {
        try await APIClient.shared.request("/api/sitters/\(userId)")
    }

    static func updateMySitterProfile(_ payload: SitterProfileUpdateRequest, token: String) async throws -> SitterProfile {
        try await APIClient.shared.request("/api/sitters/me", method: "PUT", body: payload, token: token)
    }

    static func sitterReviews(userId: Int) async throws -> [Review] {
        try await APIClient.shared.request("/api/sitters/\(userId)/reviews")
    }

    // MARK: Pets

    static func listMyPets(token: String) async throws -> [Pet] {
        try await APIClient.shared.request("/api/pets", token: token)
    }

    static func createPet(_ payload: PetCreateRequest, token: String) async throws -> Pet {
        try await APIClient.shared.request("/api/pets", method: "POST", body: payload, token: token)
    }

    static func deletePet(id: Int, token: String) async throws {
        let _: EmptyResponse = try await APIClient.shared.request("/api/pets/\(id)", method: "DELETE", token: token)
    }

    // MARK: Bookings

    static func createBooking(_ payload: BookingCreateRequest, token: String) async throws -> Booking {
        try await APIClient.shared.request("/api/bookings", method: "POST", body: payload, token: token)
    }

    static func listMyBookings(token: String) async throws -> [Booking] {
        try await APIClient.shared.request("/api/bookings", token: token)
    }

    static func updateBookingStatus(id: Int, status: BookingStatus, token: String) async throws -> Booking {
        try await APIClient.shared.request(
            "/api/bookings/\(id)", method: "PATCH", body: BookingStatusUpdateRequest(status: status), token: token
        )
    }

    static func listMessages(bookingId: Int, token: String) async throws -> [Message] {
        try await APIClient.shared.request("/api/bookings/\(bookingId)/messages", token: token)
    }

    static func sendMessage(bookingId: Int, body: String, token: String) async throws -> Message {
        try await APIClient.shared.request(
            "/api/bookings/\(bookingId)/messages", method: "POST", body: MessageCreateRequest(body: body), token: token
        )
    }

    static func createReview(bookingId: Int, rating: Int, comment: String, token: String) async throws -> Review {
        try await APIClient.shared.request(
            "/api/bookings/\(bookingId)/review", method: "POST",
            body: ReviewCreateRequest(rating: rating, comment: comment), token: token
        )
    }

    // MARK: Reports (App Store UGC moderation requirement)

    static func createReport(
        targetType: ReportTargetType, targetId: Int, reason: ReportReason, details: String, token: String
    ) async throws -> ReportOut {
        try await APIClient.shared.request(
            "/api/reports", method: "POST",
            body: ReportCreateRequest(targetType: targetType, targetId: targetId, reason: reason, details: details),
            token: token
        )
    }
}
