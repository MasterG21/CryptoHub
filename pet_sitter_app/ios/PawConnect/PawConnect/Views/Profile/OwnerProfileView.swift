import SwiftUI

struct OwnerProfileView: View {
    @EnvironmentObject var session: SessionStore
    @StateObject private var viewModel = PetsViewModel()

    @State private var name = ""
    @State private var species = ""
    @State private var breed = ""
    @State private var notes = ""

    var body: some View {
        Form {
            if let user = session.user {
                Section("Account") {
                    Text(user.fullName)
                    Text(user.email).foregroundColor(PCColor.textMuted)
                }
            }

            Section("Add a pet") {
                TextField("Pet name", text: $name)
                TextField("Species (dog, cat, ...)", text: $species)
                TextField("Breed (optional)", text: $breed)
                TextField("Feeding schedule, medications, quirks...", text: $notes, axis: .vertical)
                Button("Add pet") {
                    Task {
                        guard let token = session.token else { return }
                        await viewModel.addPet(
                            name: name, species: species,
                            breed: breed.isEmpty ? nil : breed, notes: notes, token: token
                        )
                        name = ""; species = ""; breed = ""; notes = ""
                    }
                }
                .disabled(name.isEmpty || species.isEmpty || viewModel.isBusy)
                if let error = viewModel.errorMessage {
                    Text(error).foregroundColor(PCColor.danger).font(.footnote)
                }
            }

            Section("My pets") {
                if viewModel.pets.isEmpty {
                    Text("No pets added yet.").foregroundColor(PCColor.textMuted)
                } else {
                    ForEach(viewModel.pets) { pet in
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(pet.name) (\(pet.species))").font(.headline)
                            if let breed = pet.breed, !breed.isEmpty {
                                Text(breed).font(.caption).foregroundColor(PCColor.textMuted)
                            }
                            if !pet.notes.isEmpty {
                                Text(pet.notes).font(.subheadline)
                            }
                        }
                    }
                    .onDelete { indexSet in
                        Task {
                            guard let token = session.token else { return }
                            for index in indexSet {
                                await viewModel.deletePet(id: viewModel.pets[index].id, token: token)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("My Profile")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Log out") { session.logout() }
            }
        }
        .task { if let token = session.token { await viewModel.load(token: token) } }
    }
}
