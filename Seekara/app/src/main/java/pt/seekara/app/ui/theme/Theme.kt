package pt.seekara.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Navy = Color(0xFF0A0F1E)
val SurfaceDark = Color(0xFF10182B)
val SurfaceRaised = Color(0xFF17203A)
val Cyan = Color(0xFF22D3EE)
val Blue = Color(0xFF3B82F6)
val Violet = Color(0xFF8B5CF6)
val TextPrimary = Color(0xFFE7ECF6)
val TextSecondary = Color(0xFF97A3BD)

private val SeekaraDarkColors = darkColorScheme(
    primary = Cyan,
    onPrimary = Color(0xFF00252D),
    primaryContainer = Color(0xFF10394A),
    onPrimaryContainer = Color(0xFFB7EDFA),
    secondary = Blue,
    onSecondary = Color(0xFFEAF2FF),
    tertiary = Violet,
    background = Navy,
    onBackground = TextPrimary,
    surface = SurfaceDark,
    onSurface = TextPrimary,
    surfaceVariant = SurfaceRaised,
    onSurfaceVariant = TextSecondary,
    surfaceContainer = SurfaceDark,
    surfaceContainerHigh = SurfaceRaised,
    outline = Color(0xFF2A3654),
    outlineVariant = Color(0xFF1E2A47)
)

@Composable
fun SeekaraTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = SeekaraDarkColors,
        content = content
    )
}
