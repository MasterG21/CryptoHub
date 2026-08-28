import SwiftUI

struct AuthView: View {
    @EnvironmentObject var session: SessionStore
    @State private var mode: Mode = .login

    enum Mode: String, CaseIterable { case login = "Log in", register = "Sign up" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("🐾 Welcome to PawConnect")
                    .font(.title2.bold())

                Picker("Mode", selection: $mode) {
                    ForEach(Mode.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)

                if let error = session.errorMessage {
                    Text(error).foregroundColor(PCColor.danger).font(.footnote)
                }

                switch mode {
                case .login: LoginForm()
                case .register: RegisterForm()
                }
            }
            .padding()
        }
        .background(PCColor.background.ignoresSafeArea())
        .navigationTitle("PawConnect")
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct LoginForm: View {
    @EnvironmentObject var session: SessionStore
    @State private var email = ""
    @State private var password = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            LabeledField(title: "Email") {
                TextField("you@example.com", text: $email)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.emailAddress)
                    .textFieldStyle(.roundedBorder)
            }
            LabeledField(title: "Password") {
                SecureField("Password", text: $password)
                    .textFieldStyle(.roundedBorder)
            }
            Button {
                Task { await session.login(email: email, password: password) }
            } label: {
                if session.isBusy {
                    ProgressView().frame(maxWidth: .infinity)
                } else {
                    Text("Log in").frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(.borderedProminent)
            .tint(PCColor.accent)
            .disabled(email.isEmpty || password.isEmpty || session.isBusy)
        }
    }
}

private struct RegisterForm: View {
    @EnvironmentObject var session: SessionStore
    @State private var fullName = ""
    @State private var email = ""
    @State private var password = ""
    @State private var city = ""
    @State private var phone = ""
    @State private var role: UserRole = .owner

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            LabeledField(title: "Full name") {
                TextField("Jane Doe", text: $fullName).textFieldStyle(.roundedBorder)
            }
            LabeledField(title: "Email") {
                TextField("you@example.com", text: $email)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.emailAddress)
                    .textFieldStyle(.roundedBorder)
            }
            LabeledField(title: "Password") {
                SecureField("At least 8 characters", text: $password).textFieldStyle(.roundedBorder)
            }
            LabeledField(title: "City") {
                TextField("Austin, TX", text: $city).textFieldStyle(.roundedBorder)
            }
            LabeledField(title: "Phone (optional)") {
                TextField("Phone", text: $phone).textFieldStyle(.roundedBorder)
            }
            LabeledField(title: "I am a...") {
                Picker("Role", selection: $role) {
                    ForEach(UserRole.allCases) { Text($0.label).tag($0) }
                }
                .pickerStyle(.segmented)
            }
            Button {
                Task {
                    await session.register(
                        fullName: fullName, email: email, password: password, role: role,
                        city: city.isEmpty ? nil : city, phone: phone.isEmpty ? nil : phone
                    )
                }
            } label: {
                if session.isBusy {
                    ProgressView().frame(maxWidth: .infinity)
                } else {
                    Text("Create account").frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(.borderedProminent)
            .tint(PCColor.accent)
            .disabled(fullName.isEmpty || email.isEmpty || password.count < 8 || session.isBusy)
        }
    }
}

struct LabeledField<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundColor(PCColor.textMuted)
            content
        }
    }
}
