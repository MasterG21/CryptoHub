import Foundation

@MainActor
final class BrowseViewModel: ObservableObject {
    @Published var city = ""
    @Published var petType = ""
    @Published var maxRate = ""
    @Published var service: ServiceType?
    @Published private(set) var sitters: [SitterProfile] = []
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    func search() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            sitters = try await APIService.listSitters(
                city: city.isEmpty ? nil : city,
                service: service,
                petType: petType.isEmpty ? nil : petType,
                maxRate: Double(maxRate)
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
