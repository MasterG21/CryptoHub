import SwiftUI

struct SitterDetailView: View {
    let sitterUserId: Int

    @EnvironmentObject var session: SessionStore
    @StateObject private var viewModel = SitterDetailViewModel()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if viewModel.isLoading {
                    ProgressView().frame(maxWidth: .infinity)
                } else if let sitter = viewModel.sitter {
                    sitterHeader(sitter)

                    if let error = viewModel.errorMessage {
                        Text(error).foregroundColor(PCColor.danger)
                    }

                    if session.user?.role == .owner {
                        BookingRequestForm(sitter: sitter, viewModel: viewModel)
                    } else if session.user == nil {
                        Text("Log in as a pet owner to request a booking.")
                            .foregroundColor(PCColor.textMuted)
                    }

                    reviewsSection
                } else if let error = viewModel.errorMessage {
                    Text(error).foregroundColor(PCColor.danger)
                }
            }
            .padding()
        }
        .background(PCColor.background.ignoresSafeArea())
        .navigationTitle(viewModel.sitter?.user.fullName ?? "Sitter")
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.load(userId: sitterUserId) }
    }

    private func sitterHeader(_ sitter: SitterProfile) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(sitter.city ?? "Location not set").foregroundColor(PCColor.textMuted)
            RatingLabel(average: sitter.averageRating, count: sitter.reviewCount)
            Text(sitter.bio.isEmpty ? "No bio provided." : sitter.bio)
            Text("$\(sitter.hourlyRate, specifier: "%.0f")/hr · \(sitter.yearsExperience) yr experience")
                .font(.subheadline.bold())
            if !sitter.services.isEmpty {
                Text("Services: " + sitter.services.compactMap { ServiceType(rawValue: $0)?.label }.joined(separator: ", "))
                    .font(.caption).foregroundColor(PCColor.textMuted)
            }
            if !sitter.acceptedPetTypes.isEmpty {
                Text("Pets: " + sitter.acceptedPetTypes.joined(separator: ", "))
                    .font(.caption).foregroundColor(PCColor.textMuted)
            }
        }
        .cardStyle()
    }

    private var reviewsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Reviews").font(.headline)
            if viewModel.reviews.isEmpty {
                Text("No reviews yet.").foregroundColor(PCColor.textMuted)
            } else {
                ForEach(viewModel.reviews) { review in
                    ReviewRow(review: review)
                }
            }
        }
    }
}

private struct ReviewRow: View {
    let review: Review
    @EnvironmentObject var session: SessionStore
    @State private var showReportSheet = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                ForEach(0..<5) { index in
                    Image(systemName: index < review.rating ? "star.fill" : "star")
                        .foregroundColor(Color(hex: "D99A00"))
                        .font(.caption)
                }
                Spacer()
                Text(review.reviewer.fullName).font(.caption).foregroundColor(PCColor.textMuted)
            }
            if !review.comment.isEmpty {
                Text(review.comment).font(.subheadline)
            }
            if session.isLoggedIn {
                Button("Report") { showReportSheet = true }
                    .font(.caption)
                    .foregroundColor(PCColor.danger)
            }
        }
        .cardStyle()
        .sheet(isPresented: $showReportSheet) {
            ReportSheet(targetType: .review, targetId: review.id)
        }
    }
}

private struct BookingRequestForm: View {
    let sitter: SitterProfile
    @ObservedObject var viewModel: SitterDetailViewModel

    @EnvironmentObject var session: SessionStore
    @StateObject private var petsViewModel = PetsViewModel()

    @State private var service: ServiceType = .dogWalking
    @State private var petId: Int?
    @State private var startDate = Date()
    @State private var endDate = Date().addingTimeInterval(86400)
    @State private var notes = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Request a booking").font(.headline)

            Picker("Service", selection: $service) {
                ForEach(ServiceType.allCases) { Text($0.label).tag($0) }
            }
            Picker("Pet", selection: $petId) {
                Text("No specific pet").tag(Int?.none)
                ForEach(petsViewModel.pets) { pet in
                    Text("\(pet.name) (\(pet.species))").tag(Int?.some(pet.id))
                }
            }
            DatePicker("Start date", selection: $startDate, displayedComponents: .date)
            DatePicker("End date", selection: $endDate, in: startDate..., displayedComponents: .date)
            TextField("Anything the sitter should know?", text: $notes, axis: .vertical)
                .textFieldStyle(.roundedBorder)

            if let message = viewModel.bookingSuccessMessage {
                Text(message).foregroundColor(PCColor.success).font(.footnote)
            }

            Button {
                Task {
                    guard let token = session.token else { return }
                    let success = await viewModel.requestBooking(
                        sitterId: sitter.user.id, petId: petId, service: service,
                        start: startDate, end: endDate, notes: notes, token: token
                    )
                    if success { notes = "" }
                }
            } label: {
                if viewModel.isSubmittingBooking {
                    ProgressView().frame(maxWidth: .infinity)
                } else {
                    Text("Request booking").frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(.borderedProminent)
            .tint(PCColor.accent)
            .disabled(viewModel.isSubmittingBooking)
        }
        .cardStyle()
        .task {
            if let token = session.token { await petsViewModel.load(token: token) }
        }
    }
}
