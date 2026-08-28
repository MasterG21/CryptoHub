import SwiftUI

struct BrowseView: View {
    @StateObject private var viewModel = BrowseViewModel()

    var body: some View {
        List {
            Section("Find a pet sitter") {
                TextField("City", text: $viewModel.city)
                TextField("Pet type (dog, cat, ...)", text: $viewModel.petType)
                Picker("Service", selection: $viewModel.service) {
                    Text("Any service").tag(ServiceType?.none)
                    ForEach(ServiceType.allCases) { service in
                        Text(service.label).tag(ServiceType?.some(service))
                    }
                }
                TextField("Max hourly rate ($)", text: $viewModel.maxRate)
                    .keyboardType(.decimalPad)
                Button("Search") { Task { await viewModel.search() } }
                    .foregroundColor(PCColor.accentDark)
            }

            if viewModel.isLoading {
                ProgressView().frame(maxWidth: .infinity)
            } else if let error = viewModel.errorMessage {
                Text(error).foregroundColor(PCColor.danger)
            } else if viewModel.sitters.isEmpty {
                Text("No sitters match those filters yet.").foregroundColor(PCColor.textMuted)
            } else {
                Section("Sitters") {
                    ForEach(viewModel.sitters) { sitter in
                        NavigationLink(value: sitter) {
                            SitterRow(sitter: sitter)
                        }
                    }
                }
            }
        }
        .navigationTitle("Browse Sitters")
        .navigationDestination(for: SitterProfile.self) { sitter in
            SitterDetailView(sitterUserId: sitter.user.id)
        }
        .task { await viewModel.search() }
        .refreshable { await viewModel.search() }
    }
}

struct SitterRow: View {
    let sitter: SitterProfile

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(sitter.user.fullName).font(.headline)
            Text(sitter.city ?? "Location not set").font(.caption).foregroundColor(PCColor.textMuted)
            RatingLabel(average: sitter.averageRating, count: sitter.reviewCount)
            Text("$\(sitter.hourlyRate, specifier: "%.0f")/hr · \(sitter.yearsExperience) yr experience")
                .font(.subheadline)
        }
        .padding(.vertical, 4)
    }
}

extension SitterProfile: Hashable {
    static func == (lhs: SitterProfile, rhs: SitterProfile) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}
