import SwiftUI

struct BeaconView: View {
    private let beacon = BeaconInfo()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    header
                    summary
                    features
                    ecosystem
                    actions
                }
                .padding(.horizontal, 20)
                .padding(.top, 8)
                .padding(.bottom, 36)
            }
            .background(SeekaraTheme.wash.ignoresSafeArea())
            .navigationTitle("Beacon")
            .navigationBarTitleDisplayMode(.large)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Text(beacon.id)
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(SeekaraTheme.beacon.opacity(0.12), in: Capsule())
                    .foregroundStyle(SeekaraTheme.beacon)

                Text(beacon.status)
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(SeekaraTheme.oval.opacity(0.18), in: Capsule())
                    .foregroundStyle(SeekaraTheme.ovalDeep)

                Text(beacon.category)
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundStyle(SeekaraTheme.mute)
            }

            Text(beacon.name)
                .font(.system(size: 34, weight: .bold, design: .rounded))
                .foregroundStyle(SeekaraTheme.ink)

            Text(beacon.tagline)
                .font(.system(size: 17, weight: .medium))
                .foregroundStyle(SeekaraTheme.mute)
        }
    }

    private var summary: some View {
        Text(beacon.summary)
            .font(.system(size: 16, weight: .medium))
            .foregroundStyle(SeekaraTheme.ink.opacity(0.85))
            .lineSpacing(3)
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(SeekaraTheme.paper)
                    .overlay(
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .stroke(SeekaraTheme.line, lineWidth: 1)
                    )
            )
    }

    private var features: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("What Beacon includes")
                .font(.system(size: 20, weight: .bold, design: .rounded))
                .foregroundStyle(SeekaraTheme.ink)

            ForEach(beacon.features) { feature in
                VStack(alignment: .leading, spacing: 4) {
                    Text(feature.title)
                        .font(.system(size: 16, weight: .bold, design: .rounded))
                        .foregroundStyle(SeekaraTheme.ink)
                    Text(feature.detail)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(SeekaraTheme.mute)
                }
                .padding(.vertical, 4)

                if feature.id != beacon.features.last?.id {
                    Divider().overlay(SeekaraTheme.line)
                }
            }
        }
        .padding(18)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(SeekaraTheme.paper)
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(SeekaraTheme.line, lineWidth: 1)
                )
        )
    }

    private var ecosystem: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Works with")
                .font(.system(size: 20, weight: .bold, design: .rounded))
                .foregroundStyle(SeekaraTheme.ink)

            Text("Beacon sits with SeekAra’s other Discord tools on seekara.pt.")
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(SeekaraTheme.mute)

            ForEach(beacon.ecosystem) { project in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(project.name)
                            .font(.system(size: 16, weight: .bold, design: .rounded))
                        Spacer()
                        Text(project.code)
                            .font(.system(size: 12, weight: .semibold, design: .rounded))
                            .foregroundStyle(SeekaraTheme.mute)
                    }
                    Text(project.blurb)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(SeekaraTheme.mute)
                }
                .padding(.vertical, 6)
            }
        }
        .padding(18)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(SeekaraTheme.paper)
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(SeekaraTheme.line, lineWidth: 1)
                )
        )
    }

    private var actions: some View {
        VStack(spacing: 10) {
            Link(destination: SeekaraLinks.works) {
                actionLabel("See Beacon on seekara.pt", prominent: true)
            }
            Link(destination: SeekaraLinks.oval) {
                actionLabel("Try Oval AI chat", prominent: false)
            }
            Link(destination: SeekaraLinks.discordBotSupport) {
                actionLabel("Discord bot support", prominent: false)
            }
        }
    }

    private func actionLabel(_ title: String, prominent: Bool) -> some View {
        Text(title)
            .font(.system(size: 16, weight: .bold, design: .rounded))
            .foregroundStyle(prominent ? Color.white : SeekaraTheme.ink)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background {
                if prominent {
                    Capsule().fill(SeekaraTheme.brandGradient)
                } else {
                    Capsule()
                        .fill(SeekaraTheme.paper)
                        .overlay(Capsule().stroke(SeekaraTheme.line, lineWidth: 1))
                }
            }
    }
}

#Preview {
    BeaconView()
}
