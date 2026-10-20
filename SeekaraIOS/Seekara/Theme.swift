import SwiftUI

enum SeekaraTheme {
    static let ink = Color(red: 0.059, green: 0.071, blue: 0.086)
    static let mute = Color(red: 0.353, green: 0.380, blue: 0.424)
    static let wash = Color(red: 0.973, green: 0.976, blue: 0.984)
    static let paper = Color.white
    static let line = Color(red: 0.894, green: 0.906, blue: 0.925)
    static let seek = Color(red: 0.878, green: 0.478, blue: 0.271)
    static let ara = Color(red: 0.761, green: 0.294, blue: 0.294)
    static let oval = Color(red: 0.239, green: 0.863, blue: 0.518)
    static let ovalDeep = Color(red: 0.055, green: 0.478, blue: 0.239)
    static let ovalInk = Color(red: 0.012, green: 0.067, blue: 0.043)
    static let beacon = Color(red: 0.345, green: 0.337, blue: 0.839)

    static var brandGradient: LinearGradient {
        LinearGradient(
            colors: [seek, ara],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    static var ovalGradient: LinearGradient {
        LinearGradient(
            colors: [Color(red: 0.431, green: 0.941, blue: 0.659), oval],
            startPoint: .top,
            endPoint: .bottom
        )
    }
}
