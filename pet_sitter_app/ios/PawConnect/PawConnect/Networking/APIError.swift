import Foundation

enum APIError: LocalizedError {
    case server(String)
    case unauthorized
    case decoding
    case network(String)

    var errorDescription: String? {
        switch self {
        case .server(let message): return message
        case .unauthorized: return "Your session has expired. Please log in again."
        case .decoding: return "Something went wrong reading the server's response."
        case .network(let message): return message
        }
    }
}
