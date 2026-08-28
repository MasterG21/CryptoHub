import SwiftUI

struct MessagesView: View {
    let bookingId: Int

    @EnvironmentObject var session: SessionStore
    @StateObject private var viewModel = MessagesViewModel()
    @State private var draft = ""
    @State private var reportingMessageId: Int?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Messages").font(.headline)

            if viewModel.isLoading {
                ProgressView()
            } else if viewModel.messages.isEmpty {
                Text("No messages yet.").foregroundColor(PCColor.textMuted).font(.footnote)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(viewModel.messages) { message in
                        MessageBubble(
                            message: message,
                            isMine: message.senderId == session.user?.id,
                            onReport: { reportingMessageId = message.id }
                        )
                    }
                }
            }

            if let error = viewModel.errorMessage {
                Text(error).foregroundColor(PCColor.danger).font(.footnote)
            }

            HStack {
                TextField("Write a message...", text: $draft)
                    .textFieldStyle(.roundedBorder)
                Button("Send") {
                    guard let token = session.token else { return }
                    Task {
                        await viewModel.send(bookingId: bookingId, body: draft, token: token)
                        draft = ""
                    }
                }
                .disabled(viewModel.isSending || draft.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .task { if let token = session.token { await viewModel.load(bookingId: bookingId, token: token) } }
        .sheet(item: Binding(
            get: { reportingMessageId.map { IdentifiableInt(id: $0) } },
            set: { reportingMessageId = $0?.id }
        )) { wrapped in
            ReportSheet(targetType: .message, targetId: wrapped.id)
        }
    }
}

private struct MessageBubble: View {
    let message: Message
    let isMine: Bool
    let onReport: () -> Void

    var body: some View {
        VStack(alignment: isMine ? .trailing : .leading, spacing: 2) {
            HStack {
                Text(message.body)
                    .padding(8)
                    .background(isMine ? Color(hex: "FFE6D9") : PCColor.background)
                    .cornerRadius(8)
            }
            if !isMine {
                Button("Report", action: onReport)
                    .font(.caption2)
                    .foregroundColor(PCColor.danger)
            }
        }
        .frame(maxWidth: .infinity, alignment: isMine ? .trailing : .leading)
    }
}

/// Small helper so `Int?` can drive `.sheet(item:)`.
struct IdentifiableInt: Identifiable {
    let id: Int
}
