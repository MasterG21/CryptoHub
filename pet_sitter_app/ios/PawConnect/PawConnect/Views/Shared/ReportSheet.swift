import SwiftUI

/// Lets a user flag a message, review, or another user as objectionable.
/// Required for App Store review of apps with user-generated content
/// (Guideline 1.2) — every place UGC is shown (messages, reviews) offers
/// this action.
struct ReportSheet: View {
    let targetType: ReportTargetType
    let targetId: Int

    @EnvironmentObject var session: SessionStore
    @Environment(\.dismiss) private var dismiss

    @State private var reason: ReportReason = .spam
    @State private var details = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var didSubmit = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Why are you reporting this?") {
                    Picker("Reason", selection: $reason) {
                        ForEach(ReportReason.allCases) { Text($0.label).tag($0) }
                    }
                    TextField("Additional details (optional)", text: $details, axis: .vertical)
                }
                if let errorMessage {
                    Text(errorMessage).foregroundColor(PCColor.danger)
                }
                if didSubmit {
                    Text("Thanks — our team will review this.").foregroundColor(PCColor.success)
                }
            }
            .navigationTitle("Report")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Submit") { Task { await submit() } }
                        .disabled(isSubmitting || didSubmit)
                }
            }
        }
    }

    private func submit() async {
        guard let token = session.token else { return }
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }
        do {
            _ = try await APIService.createReport(
                targetType: targetType, targetId: targetId, reason: reason, details: details, token: token
            )
            didSubmit = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
