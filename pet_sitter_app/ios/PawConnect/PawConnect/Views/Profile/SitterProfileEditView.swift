import SwiftUI

struct SitterProfileEditView: View {
    @EnvironmentObject var session: SessionStore

    @State private var bio = ""
    @State private var hourlyRate = "0"
    @State private var yearsExperience = "0"
    @State private var city = ""
    @State private var petTypesText = ""
    @State private var selectedServices: Set<ServiceType> = []

    @State private var isLoading = false
    @State private var isSaving = false
    @State private var errorMessage: String?
    @State private var didSave = false

    var body: some View {
        Form {
            if let user = session.user {
                Section("Account") {
                    Text(user.fullName)
                    Text(user.email).foregroundColor(PCColor.textMuted)
                }
            }

            Section("Sitter profile") {
                TextField("Bio", text: $bio, axis: .vertical)
                TextField("Hourly rate ($)", text: $hourlyRate).keyboardType(.decimalPad)
                TextField("Years of experience", text: $yearsExperience).keyboardType(.numberPad)
                TextField("City", text: $city)
                TextField("Pet types you accept (comma-separated)", text: $petTypesText)
            }

            Section("Services offered") {
                ForEach(ServiceType.allCases) { service in
                    Toggle(service.label, isOn: Binding(
                        get: { selectedServices.contains(service) },
                        set: { isOn in
                            if isOn { selectedServices.insert(service) } else { selectedServices.remove(service) }
                        }
                    ))
                }
            }

            if let errorMessage {
                Text(errorMessage).foregroundColor(PCColor.danger)
            }
            if didSave {
                Text("Profile saved.").foregroundColor(PCColor.success)
            }

            Button {
                Task { await save() }
            } label: {
                if isSaving { ProgressView() } else { Text("Save profile") }
            }
            .disabled(isSaving)
        }
        .navigationTitle("My Profile")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Log out") { session.logout() }
            }
        }
        .overlay {
            if isLoading { ProgressView() }
        }
        .task { await load() }
    }

    private func load() async {
        guard let userId = session.user?.id else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            let profile = try await APIService.getSitter(userId: userId)
            bio = profile.bio
            hourlyRate = String(format: "%.0f", profile.hourlyRate)
            yearsExperience = String(profile.yearsExperience)
            city = profile.city ?? ""
            petTypesText = profile.acceptedPetTypes.joined(separator: ", ")
            selectedServices = Set(profile.services.compactMap { ServiceType(rawValue: $0) })
        } catch {
            // A brand-new sitter has no profile row yet on first load in some flows;
            // that's fine, the form just starts empty.
        }
    }

    private func save() async {
        guard let token = session.token else { return }
        isSaving = true
        errorMessage = nil
        didSave = false
        defer { isSaving = false }
        let petTypes = petTypesText.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        do {
            _ = try await APIService.updateMySitterProfile(
                SitterProfileUpdateRequest(
                    bio: bio,
                    hourlyRate: Double(hourlyRate) ?? 0,
                    yearsExperience: Int(yearsExperience) ?? 0,
                    services: Array(selectedServices),
                    acceptedPetTypes: petTypes,
                    city: city.isEmpty ? nil : city
                ),
                token: token
            )
            didSave = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
