import SwiftUI
import WebKit

struct SiteBrowserView: View {
    let title: String
    let url: URL

    @State private var pageTitle = ""
    @State private var isLoading = false
    @State private var canGoBack = false
    @State private var canGoForward = false
    @State private var reloadToken = 0

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                }

                WebView(
                    url: url,
                    reloadToken: reloadToken,
                    pageTitle: $pageTitle,
                    isLoading: $isLoading,
                    canGoBack: $canGoBack,
                    canGoForward: $canGoForward
                )
            }
            .background(SeekaraTheme.wash.ignoresSafeArea())
            .navigationTitle(pageTitle.isEmpty ? title : pageTitle)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItemGroup(placement: .bottomBar) {
                    Button {
                        NotificationCenter.default.post(name: .seekaraWebGoBack, object: nil)
                    } label: {
                        Image(systemName: "chevron.backward")
                    }
                    .disabled(!canGoBack)

                    Button {
                        NotificationCenter.default.post(name: .seekaraWebGoForward, object: nil)
                    } label: {
                        Image(systemName: "chevron.forward")
                    }
                    .disabled(!canGoForward)

                    Spacer()

                    Button {
                        reloadToken += 1
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }

                    ShareLink(item: url) {
                        Image(systemName: "square.and.arrow.up")
                    }
                }
            }
        }
    }
}

extension Notification.Name {
    static let seekaraWebGoBack = Notification.Name("seekaraWebGoBack")
    static let seekaraWebGoForward = Notification.Name("seekaraWebGoForward")
}

struct WebView: UIViewRepresentable {
    let url: URL
    let reloadToken: Int
    @Binding var pageTitle: String
    @Binding var isLoading: Bool
    @Binding var canGoBack: Bool
    @Binding var canGoForward: Bool

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView()
        webView.navigationDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.load(URLRequest(url: url))

        context.coordinator.observe(webView)
        context.coordinator.bindNotifications(to: webView)
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        if context.coordinator.lastReloadToken != reloadToken {
            context.coordinator.lastReloadToken = reloadToken
            webView.reload()
        }
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        var parent: WebView
        var lastReloadToken = 0
        private var observations: [NSKeyValueObservation] = []
        private var tokens: [NSObjectProtocol] = []

        init(_ parent: WebView) {
            self.parent = parent
        }

        deinit {
            observations.forEach { $0.invalidate() }
            tokens.forEach { NotificationCenter.default.removeObserver($0) }
        }

        func observe(_ webView: WKWebView) {
            observations = [
                webView.observe(\.isLoading) { [weak self] view, _ in
                    DispatchQueue.main.async { self?.parent.isLoading = view.isLoading }
                },
                webView.observe(\.title) { [weak self] view, _ in
                    DispatchQueue.main.async { self?.parent.pageTitle = view.title ?? "" }
                },
                webView.observe(\.canGoBack) { [weak self] view, _ in
                    DispatchQueue.main.async { self?.parent.canGoBack = view.canGoBack }
                },
                webView.observe(\.canGoForward) { [weak self] view, _ in
                    DispatchQueue.main.async { self?.parent.canGoForward = view.canGoForward }
                },
            ]
        }

        func bindNotifications(to webView: WKWebView) {
            let center = NotificationCenter.default
            tokens = [
                center.addObserver(forName: .seekaraWebGoBack, object: nil, queue: .main) { _ in
                    if webView.canGoBack { webView.goBack() }
                },
                center.addObserver(forName: .seekaraWebGoForward, object: nil, queue: .main) { _ in
                    if webView.canGoForward { webView.goForward() }
                },
            ]
        }
    }
}

#Preview {
    SiteBrowserView(title: "SeekAra", url: SeekaraLinks.home)
}
