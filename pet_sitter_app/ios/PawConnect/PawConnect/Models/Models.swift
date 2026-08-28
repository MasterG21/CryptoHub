import Foundation

// MARK: - Enums (mirror app/models.py on the backend)

enum UserRole: String, Codable, CaseIterable, Identifiable {
    case owner
    case sitter

    var id: String { rawValue }

    var label: String {
        switch self {
        case .owner: return "Pet owner - I need a sitter"
        case .sitter: return "Pet sitter - I offer sitting services"
        }
    }
}

enum ServiceType: String, Codable, CaseIterable, Identifiable {
    case dogWalking = "dog_walking"
    case boarding
    case dropInVisit = "drop_in_visit"
    case daycare
    case houseSitting = "house_sitting"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .dogWalking: return "Dog walking"
        case .boarding: return "Boarding"
        case .dropInVisit: return "Drop-in visit"
        case .daycare: return "Daycare"
        case .houseSitting: return "House sitting"
        }
    }
}

enum BookingStatus: String, Codable {
    case pending, accepted, declined, cancelled, completed

    var label: String { rawValue.capitalized }

    var tintColor: String {
        switch self {
        case .pending: return "pending"
        case .accepted: return "accepted"
        case .completed: return "completed"
        case .declined, .cancelled: return "declined"
        }
    }
}

enum ReportTargetType: String, Codable {
    case message, review, user
}

enum ReportReason: String, Codable, CaseIterable, Identifiable {
    case spam
    case harassment
    case inappropriateContent = "inappropriate_content"
    case safetyConcern = "safety_concern"
    case other

    var id: String { rawValue }

    var label: String {
        switch self {
        case .spam: return "Spam"
        case .harassment: return "Harassment or abuse"
        case .inappropriateContent: return "Inappropriate content"
        case .safetyConcern: return "Safety concern"
        case .other: return "Other"
        }
    }
}

// MARK: - Models

struct UserOut: Codable, Identifiable, Equatable {
    let id: Int
    let email: String
    let fullName: String
    let role: UserRole
    let city: String?
    let phone: String?
}

struct Token: Codable {
    let accessToken: String
    let tokenType: String
    let user: UserOut
}

struct SitterProfile: Codable, Identifiable {
    let id: Int
    let user: UserOut
    let bio: String
    let hourlyRate: Double
    let yearsExperience: Int
    let services: [String]
    let acceptedPetTypes: [String]
    let city: String?
    let averageRating: Double?
    let reviewCount: Int
}

struct Pet: Codable, Identifiable {
    let id: Int
    let name: String
    let species: String
    let breed: String?
    let notes: String
}

struct Booking: Codable, Identifiable {
    let id: Int
    let owner: UserOut
    let sitter: UserOut
    let pet: Pet?
    let serviceType: ServiceType
    let startDate: String
    let endDate: String
    let status: BookingStatus
    let notes: String
    let createdAt: String
}

struct Message: Codable, Identifiable {
    let id: Int
    let senderId: Int
    let body: String
    let createdAt: String
}

struct Review: Codable, Identifiable {
    let id: Int
    let bookingId: Int
    let reviewer: UserOut
    let rating: Int
    let comment: String
    let createdAt: String
}

struct ReportOut: Codable, Identifiable {
    let id: Int
    let targetType: ReportTargetType
    let targetId: Int
    let reason: ReportReason
    let details: String
    let status: String
    let createdAt: String
}

// MARK: - Request bodies

struct RegisterRequest: Encodable {
    let email: String
    let password: String
    let fullName: String
    let role: UserRole
    let city: String?
    let phone: String?
}

struct LoginRequest: Encodable {
    let email: String
    let password: String
}

struct SitterProfileUpdateRequest: Encodable {
    let bio: String
    let hourlyRate: Double
    let yearsExperience: Int
    let services: [ServiceType]
    let acceptedPetTypes: [String]
    let city: String?
}

struct PetCreateRequest: Encodable {
    let name: String
    let species: String
    let breed: String?
    let notes: String
}

struct BookingCreateRequest: Encodable {
    let sitterId: Int
    let petId: Int?
    let serviceType: ServiceType
    let startDate: String
    let endDate: String
    let notes: String
}

struct BookingStatusUpdateRequest: Encodable {
    let status: BookingStatus
}

struct MessageCreateRequest: Encodable {
    let body: String
}

struct ReviewCreateRequest: Encodable {
    let rating: Int
    let comment: String
}

struct ReportCreateRequest: Encodable {
    let targetType: ReportTargetType
    let targetId: Int
    let reason: ReportReason
    let details: String
}
