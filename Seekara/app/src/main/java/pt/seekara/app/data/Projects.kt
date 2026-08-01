package pt.seekara.app.data

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Accessibility
import androidx.compose.material.icons.rounded.Public
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.material.icons.rounded.SmartToy
import androidx.compose.material.icons.rounded.SportsEsports
import androidx.compose.ui.graphics.vector.ImageVector

object SeekaraLinks {
    const val SITE = "https://www.seekara.pt/"
    const val PROJECTS = "https://www.seekara.pt/our-projects"
    const val SUPPORT_TICKET = "https://www.seekara.pt/support/support-ticket"
    const val DISCORD_BOT_SUPPORT = "https://www.seekara.pt/support/discordbotsupport"
}

data class Project(
    val number: Int,
    val name: String,
    val tagline: String,
    val description: String,
    val icon: ImageVector
)

val seekaraProjects = listOf(
    Project(
        number = 1,
        name = "Seekara Cloud Gaming",
        tagline = "Easy to use gaming platform",
        description = "One of the first cloud gaming platforms — broadcasting images and input over the internet using strings of numbers.",
        icon = Icons.Rounded.SportsEsports
    ),
    Project(
        number = 2,
        name = "Seekara Browse",
        tagline = "Simple browser for privacy nerds",
        description = "A minimalistic browser that stays fast, clean and out of your way.",
        icon = Icons.Rounded.Public
    ),
    Project(
        number = 3,
        name = "Seekara View",
        tagline = "Body tracking using PoseNet",
        description = "An online multiplayer full-body tracker that runs on machine-learning pose estimation.",
        icon = Icons.Rounded.Accessibility
    ),
    Project(
        number = 4,
        name = "Seekara Security Bots",
        tagline = "Security on Discord done right",
        description = "Keep your community safe with Seekara-enabled Discord security and moderation bots.",
        icon = Icons.Rounded.Shield
    ),
    Project(
        number = 5,
        name = "Sonar Instigator",
        tagline = "A sort of self-aware bot",
        description = "An experimental conversational bot with a mind of its own.",
        icon = Icons.Rounded.SmartToy
    )
)
