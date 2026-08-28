import SwiftUI

struct RootView: View {
    @EnvironmentObject var session: SessionStore

    var body: some View {
        Group {
            if session.isLoggedIn {
                MainTabView()
            } else {
                NavigationStack {
                    AuthView()
                }
            }
        }
        .tint(PCColor.accent)
    }
}

struct MainTabView: View {
    var body: some View {
        TabView {
            NavigationStack { BrowseView() }
                .tabItem { Label("Browse", systemImage: "magnifyingglass") }

            NavigationStack { BookingsListView() }
                .tabItem { Label("Bookings", systemImage: "calendar") }

            NavigationStack { ProfileRouterView() }
                .tabItem { Label("Profile", systemImage: "person.crop.circle") }
        }
    }
}

struct ProfileRouterView: View {
    @EnvironmentObject var session: SessionStore

    var body: some View {
        if session.user?.role == .sitter {
            SitterProfileEditView()
        } else {
            OwnerProfileView()
        }
    }
}
