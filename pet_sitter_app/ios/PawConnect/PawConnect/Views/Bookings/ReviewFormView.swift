import SwiftUI

struct ReviewFormView: View {
    let bookingId: Int

    @EnvironmentObject var session: SessionStore
    @State private var rating = 5
    @State private var comment = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var didSubmit = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Leave a review").font(.headline)

            if didSubmit {
                Text("Thanks for the review!").foregroundColor(PCColor.success)
            } else {
                Picker("Rating", selection: $rating) {
                    ForEach(1...5, id: \.self) { value in
                        Text("\(value) star\(value == 1 ? "" : "s")").tag(value)
                    }
                }
                TextField("How did it go?", text: $comment, axis: .vertical)
                    .textFieldStyle(.roundedBorder)

                if let errorMessage {
                    Text(errorMessage).foregroundColor(PCColor.danger).font(.footnote)
                }

                Button {
                    Task { await submit() }
                } label: {
                    if isSubmitting {
                        ProgressView().frame(maxWidth: .infinity)
                    } else {
                        Text("Submit review").frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(PCColor.accent)
                .disabled(isSubmitting)
            }
        }
        .cardStyle()
    }

    private func submit() async {
        guard let token = session.token else { return }
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }
        do {
            _ = try await APIService.createReview(bookingId: bookingId, rating: rating, comment: comment, token: token)
            didSubmit = true
        } catch {
            let message = error.localizedDescription
            if message.lowercased().contains("already reviewed") {
                didSubmit = true
            } else {
                errorMessage = message
            }
        }
    }
}
