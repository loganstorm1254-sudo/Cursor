import SwiftUI

struct HomeView: View {
    private let about = SeekaraAbout()
    private let oval = OvalInfo()
    private let beacon = BeaconInfo()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    hero
                    quickLinks
                    beaconCard
                    ovalCard
                    aboutBlock
                }
                .padding(.horizontal, 20)
                .padding(.top, 8)
                .padding(.bottom, 36)
            }
            .background(SeekaraTheme.wash.ignoresSafeArea())
            .navigationTitle("SeekAra")
            .navigationBarTitleDisplayMode(.large)
        }
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("SEEKARA")
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .tracking(3)
                .foregroundStyle(SeekaraTheme.mute)

            Text(about.headline)
                .font(.system(size: 32, weight: .bold, design: .rounded))
                .foregroundStyle(SeekaraTheme.ink)
                .lineSpacing(2)

            Text("Try SeekAra experiences — including Beacon moderation and Oval chat.")
                .font(.system(size: 17, weight: .medium))
                .foregroundStyle(SeekaraTheme.mute)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 8)
    }

    private var quickLinks: some View {
        HStack(spacing: 10) {
            LinkChip(title: "seekara.pt", url: SeekaraLinks.home, filled: true)
            LinkChip(title: "Oval", url: SeekaraLinks.oval, filled: false)
        }
    }

    private var beaconCard: some View {
        NavigationLink {
            BeaconView()
        } label: {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Label("SKR-010 · Live", systemImage: "circle.fill")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(SeekaraTheme.beacon)
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(SeekaraTheme.mute)
                }

                Text(beacon.name)
                    .font(.system(size: 26, weight: .bold, design: .rounded))
                    .foregroundStyle(SeekaraTheme.ink)

                Text(beacon.tagline)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(SeekaraTheme.mute)
                    .multilineTextAlignment(.leading)
            }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .fill(SeekaraTheme.paper)
                    .overlay(
                        RoundedRectangle(cornerRadius: 22, style: .continuous)
                            .stroke(SeekaraTheme.line, lineWidth: 1)
                    )
            )
        }
        .buttonStyle(.plain)
    }

    private var ovalCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("\(oval.code) · \(oval.status)")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(SeekaraTheme.ovalDeep)

            Text(oval.name)
                .font(.system(size: 26, weight: .bold, design: .rounded))
                .foregroundStyle(SeekaraTheme.ink)

            Text(oval.summary)
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(SeekaraTheme.mute)

            Link(destination: SeekaraLinks.oval) {
                Text("Open oval.seekara.pt")
                    .font(.system(size: 15, weight: .bold, design: .rounded))
                    .foregroundStyle(SeekaraTheme.ovalInk)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(SeekaraTheme.ovalGradient, in: Capsule())
            }
            .padding(.top, 4)
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(SeekaraTheme.paper)
                .overlay(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .stroke(SeekaraTheme.oval.opacity(0.35), lineWidth: 1)
                )
        )
    }

    private var aboutBlock: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("About SeekAra")
                .font(.system(size: 20, weight: .bold, design: .rounded))
                .foregroundStyle(SeekaraTheme.ink)
            Text(about.body)
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(SeekaraTheme.mute)
        }
    }
}

struct LinkChip: View {
    let title: String
    let url: URL
    let filled: Bool

    var body: some View {
        Link(destination: url) {
            Text(title)
                .font(.system(size: 14, weight: .bold, design: .rounded))
                .foregroundStyle(filled ? Color.white : SeekaraTheme.ink)
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .background {
                    if filled {
                        Capsule().fill(SeekaraTheme.brandGradient)
                    } else {
                        Capsule()
                            .fill(SeekaraTheme.paper)
                            .overlay(Capsule().stroke(SeekaraTheme.line, lineWidth: 1))
                    }
                }
        }
    }
}

#Preview {
    HomeView()
}
