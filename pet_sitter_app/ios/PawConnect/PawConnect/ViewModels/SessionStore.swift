import Foundation

@MainActor
final class SessionStore: ObservableObject {
    @Published private(set) var token: String?
    @Published private(set) var user: UserOut?
    @Published var errorMessage: String?
    @Published var isBusy = false

    private let tokenKey = "auth_token"
    private let userKey = "auth_user"

    init() {
        token = KeychainStore.get(forKey: tokenKey).flatMap { String(data: $0, encoding: .utf8) }
        if let data = KeychainStore.get(forKey: userKey) {
            user = try? JSONDecoder.snakeCase.decode(UserOut.self, from: data)
        }
    }

    var isLoggedIn: Bool { token != nil && user != nil }

    func register(fullName: String, email: String, password: String, role: UserRole, city: String?, phone: String?) async {
        await run {
            let result = try await APIService.register(
                RegisterRequest(email: email, password: password, fullName: fullName, role: role, city: city, phone: phone)
            )
            self.persist(result)
        }
    }

    func login(email: String, password: String) async {
        await run {
            let result = try await APIService.login(LoginRequest(email: email, password: password))
            self.persist(result)
        }
    }

    func logout() {
        token = nil
        user = nil
        KeychainStore.delete(forKey: tokenKey)
        KeychainStore.delete(forKey: userKey)
    }

    private func persist(_ result: Token) {
        token = result.accessToken
        user = result.user
        if let tokenData = result.accessToken.data(using: .utf8) {
            KeychainStore.set(tokenData, forKey: tokenKey)
        }
        if let userData = try? JSONEncoder.snakeCase.encode(result.user) {
            KeychainStore.set(userData, forKey: userKey)
        }
    }

    private func run(_ operation: @escaping () async throws -> Void) async {
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            try await operation()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

extension JSONDecoder {
    static var snakeCase: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }
}

extension JSONEncoder {
    static var snakeCase: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }
}
