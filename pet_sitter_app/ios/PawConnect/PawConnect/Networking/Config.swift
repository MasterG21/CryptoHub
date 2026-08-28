import Foundation

enum Config {
    /// Backend base URL, baked in at build time via the API_BASE_URL build
    /// setting in project.yml (see pet_sitter_app/DEPLOYMENT.md). Falls back
    /// to localhost for simulator development only — a release build must
    /// point at a real HTTPS backend, since App Transport Security blocks
    /// plain HTTP for anything other than the localhost exception declared
    /// in project.yml.
    static var apiBaseURL: URL {
        if let raw = Bundle.main.object(forInfoDictionaryKey: "API_BASE_URL") as? String,
           !raw.isEmpty,
           !raw.contains("your-backend-domain"),
           let url = URL(string: raw) {
            return url
        }
        return URL(string: "http://localhost:8000")!
    }
}
