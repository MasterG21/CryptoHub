import Foundation

/// Placeholder decoded type for endpoints that return no body (e.g. DELETE).
struct EmptyResponse: Decodable {}

private struct ErrorDetail: Decodable {
    let detail: String
}

final class APIClient {
    static let shared = APIClient()

    private let baseURL = Config.apiBaseURL
    private let session = URLSession.shared

    private let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    private let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()

    /// GET/DELETE-style request with no body.
    @discardableResult
    func request<Response: Decodable>(
        _ path: String,
        method: String = "GET",
        token: String? = nil,
        query: [URLQueryItem] = []
    ) async throws -> Response {
        try await send(path: path, method: method, token: token, query: query, bodyData: nil)
    }

    /// POST/PUT/PATCH-style request with an Encodable body.
    @discardableResult
    func request<Response: Decodable, Body: Encodable>(
        _ path: String,
        method: String = "POST",
        body: Body,
        token: String? = nil
    ) async throws -> Response {
        let bodyData = try encoder.encode(body)
        return try await send(path: path, method: method, token: token, query: [], bodyData: bodyData)
    }

    private func send<Response: Decodable>(
        path: String,
        method: String,
        token: String?,
        query: [URLQueryItem],
        bodyData: Data?
    ) async throws -> Response {
        guard var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false) else {
            throw APIError.network("Invalid URL")
        }
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw APIError.network("Invalid URL") }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = method
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token {
            urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        urlRequest.httpBody = bodyData

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: urlRequest)
        } catch {
            throw APIError.network(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIError.network("No response from the server")
        }

        if http.statusCode == 401 {
            throw APIError.unauthorized
        }

        guard (200...299).contains(http.statusCode) else {
            if let detail = try? decoder.decode(ErrorDetail.self, from: data) {
                throw APIError.server(detail.detail)
            }
            throw APIError.server("Request failed with status \(http.statusCode)")
        }

        if Response.self == EmptyResponse.self {
            return EmptyResponse() as! Response // swiftlint:disable:this force_cast
        }

        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw APIError.decoding
        }
    }
}
