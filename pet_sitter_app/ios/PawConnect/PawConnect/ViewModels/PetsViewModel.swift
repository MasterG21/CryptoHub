import Foundation

@MainActor
final class PetsViewModel: ObservableObject {
    @Published private(set) var pets: [Pet] = []
    @Published var errorMessage: String?
    @Published var isBusy = false

    func load(token: String) async {
        do {
            pets = try await APIService.listMyPets(token: token)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func addPet(name: String, species: String, breed: String?, notes: String, token: String) async {
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            let pet = try await APIService.createPet(
                PetCreateRequest(name: name, species: species, breed: breed, notes: notes), token: token
            )
            pets.append(pet)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deletePet(id: Int, token: String) async {
        do {
            try await APIService.deletePet(id: id, token: token)
            pets.removeAll { $0.id == id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
