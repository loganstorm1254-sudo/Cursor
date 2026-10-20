import Foundation

enum SeekaraLinks {
    static let home = URL(string: "https://seekara.pt")!
    static let wwwHome = URL(string: "https://www.seekara.pt")!
    static let oval = URL(string: "https://oval.seekara.pt")!
    static let works = URL(string: "https://seekara.pt/#works")!
    static let discordBotSupport = URL(string: "https://www.seekara.pt/support/discordbotsupport")!
}

struct BeaconInfo: Identifiable, Hashable {
    let id = "SKR-010"
    let name = "Beacon"
    let status = "Live"
    let category = "Discord"
    let tagline = "Advanced Discord moderation by SeekAra Discord Bot Labs"
    let summary = """
    Beacon is SeekAra’s advanced Discord moderation bot (SKR-010). \
    It helps communities stay safe and organized with antinuke protection, \
    structure backups, warns, stickies, polls, XP/economy, and more.
    """
    let features: [BeaconFeature] = [
        .init(title: "Antinuke", detail: "Hardens your server against mass bans, channel wipes, and hostile takeovers."),
        .init(title: "Structure backups", detail: "Snapshot roles, channels, and layout so you can recover after accidents."),
        .init(title: "Warns", detail: "Track member warnings with a clear moderation history."),
        .init(title: "Stickies", detail: "Pin important messages that stay visible as chat moves."),
        .init(title: "Polls", detail: "Run community votes without leaving Discord."),
        .init(title: "XP & economy", detail: "Reward activity with leveling and a lightweight server economy."),
    ]
    let ecosystem: [RelatedProject] = [
        .init(code: "SKR-011", name: "Flare", blurb: "Discord security & verification — alt scans, automod, captcha, reports."),
        .init(code: "SKR-012", name: "Reverb", blurb: "Describe a community once — builds channels, roles, and wires Beacon + Flare + SeekDesk."),
        .init(code: "SKR-013", name: "SeekDesk", blurb: "Support-ticket Discord bot with a help-desk flow for communities."),
    ]
}

struct BeaconFeature: Identifiable, Hashable {
    var id: String { title }
    let title: String
    let detail: String
}

struct RelatedProject: Identifiable, Hashable {
    var id: String { code }
    let code: String
    let name: String
    let blurb: String
}

struct OvalInfo {
    let name = "Oval"
    let code = "SKR-001"
    let status = "Live · Flagship"
    let summary = """
    Oval is SeekAra’s AI chat assistant for writing, learning, and everyday questions. \
    Try it free as a guest at oval.seekara.pt — a SeekAra account unlocks chats, memory, Oval+, and the API.
    """
}

struct SeekaraAbout {
    let headline = "Projects designed to help you get things done quickly."
    let body = """
    SeekAra is a place where you can try new tech projects from the SeekAra team and friends. \
    From Oval chat to Beacon moderation and beyond, every build is meant to ship useful tools fast.
    """
}
