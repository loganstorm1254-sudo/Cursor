import SwiftUI

struct RootTabView: View {
    var body: some View {
        TabView {
            HomeView()
                .tabItem { Label("Home", systemImage: "house.fill") }

            BeaconView()
                .tabItem { Label("Beacon", systemImage: "antenna.radiowaves.left.and.right") }

            SiteBrowserView(title: "SeekAra", url: SeekaraLinks.home)
                .tabItem { Label("seekara.pt", systemImage: "globe") }

            SiteBrowserView(title: "Oval", url: SeekaraLinks.oval)
                .tabItem { Label("Oval", systemImage: "bubble.left.and.bubble.right.fill") }
        }
        .tint(SeekaraTheme.seek)
    }
}

#Preview {
    RootTabView()
}
