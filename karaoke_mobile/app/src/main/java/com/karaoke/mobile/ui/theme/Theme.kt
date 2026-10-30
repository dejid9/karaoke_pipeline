package com.karaoke.mobile.ui.theme

import android.app.Activity
import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

/**
 * Палитра темы караоке-редактора
 */
data class KaraokeThemePalette(
    val name: String,
    val isDark: Boolean,
    val accent: Color,
    val accentAlt: Color,
    val bg: Color,
    val panel: Color,
    val raised: Color,
    val inputBg: Color,
    val fg: Color,
    val muted: Color,
    val border: Color,
    val canvas: Color,
    val canvasAlt: Color,
    val grid: Color,
    val selection: Color,
    val success: Color,
    val warning: Color,
    val danger: Color,
    val accentFg: Color = Color.White
)

val NavyDarkPalette = KaraokeThemePalette(
    name = "navy_dark",
    isDark = true,
    accent = NavyPrimary,
    accentAlt = NavyPrimaryAlt,
    bg = NavyBg,
    panel = NavyPanel,
    raised = NavyRaised,
    inputBg = NavyPanel,
    fg = NavyFg,
    muted = NavyMuted,
    border = NavyBorder,
    canvas = NavyCanvas,
    canvasAlt = NavyCanvasAlt,
    grid = NavyGrid,
    selection = NavySelection,
    success = NavySuccess,
    warning = NavyWarning,
    danger = NavyDanger
)

val NavyLightPalette = KaraokeThemePalette(
    name = "navy_light",
    isDark = false,
    accent = NavyLightPrimary,
    accentAlt = NavyLightPrimaryAlt,
    bg = NavyLightBg,
    panel = NavyLightPanel,
    raised = NavyLightRaised,
    inputBg = NavyLightPanel,
    fg = NavyLightFg,
    muted = NavyLightMuted,
    border = NavyLightBorder,
    canvas = NavyLightCanvas,
    canvasAlt = NavyLightCanvasAlt,
    grid = NavyLightGrid,
    selection = NavyLightPrimaryAlt,
    success = Color(0xFF2F8A52),
    warning = Color(0xFFA56C00),
    danger = Color(0xFFB83F48)
)

val PurpleDarkPalette = NavyDarkPalette.copy(
    name = "purple_dark",
    accent = PurplePrimary,
    accentAlt = PurplePrimaryAlt,
    bg = PurpleBg,
    panel = PurplePanel,
    raised = PurpleRaised
)

val RedDarkPalette = NavyDarkPalette.copy(
    name = "red_dark",
    accent = RedPrimary,
    accentAlt = RedPrimaryAlt,
    bg = RedBg,
    panel = RedPanel,
    raised = RedRaised
)

val GreenDarkPalette = NavyDarkPalette.copy(
    name = "green_dark",
    accent = GreenPrimary,
    accentAlt = GreenPrimaryAlt,
    bg = GreenBg,
    panel = GreenPanel,
    raised = GreenRaised
)

val YellowDarkPalette = NavyDarkPalette.copy(
    name = "yellow_dark",
    accent = YellowPrimary,
    accentAlt = YellowPrimaryAlt,
    bg = YellowBg,
    panel = YellowPanel,
    raised = YellowRaised,
    accentFg = Color.Black
)

val VaporDarkPalette = NavyDarkPalette.copy(
    name = "vapor_dark",
    accent = VaporPrimary,
    accentAlt = VaporPrimaryAlt,
    bg = VaporBg,
    panel = VaporPanel,
    raised = VaporRaised
)

val CappuccinoDarkPalette = NavyDarkPalette.copy(
    name = "cappuccino_dark",
    accent = CappuccinoPrimary,
    accentAlt = CappuccinoPrimaryAlt,
    bg = CappuccinoBg,
    panel = CappuccinoPanel,
    raised = CappuccinoRaised,
    accentFg = Color.Black
)

val allThemes = listOf(
    NavyDarkPalette,
    NavyLightPalette,
    PurpleDarkPalette,
    RedDarkPalette,
    GreenDarkPalette,
    YellowDarkPalette,
    VaporDarkPalette,
    CappuccinoDarkPalette
)

fun KaraokeThemePalette.toColorScheme() = if (isDark) {
    darkColorScheme(
        primary = accent,
        onPrimary = accentFg,
        primaryContainer = accentAlt,
        onPrimaryContainer = accentFg,
        secondary = accentAlt,
        onSecondary = accentFg,
        secondaryContainer = raised,
        onSecondaryContainer = fg,
        tertiary = selection,
        onTertiary = accentFg,
        tertiaryContainer = panel,
        onTertiaryContainer = fg,
        background = bg,
        onBackground = fg,
        surface = panel,
        onSurface = fg,
        surfaceVariant = raised,
        onSurfaceVariant = muted,
        surfaceTint = accent,
        inverseSurface = fg,
        inverseOnSurface = bg,
        error = danger,
        onError = Color.White,
        errorContainer = danger.copy(alpha = 0.2f),
        onErrorContainer = danger,
        outline = border,
        outlineVariant = grid,
        scrim = Color.Black.copy(alpha = 0.5f)
    )
} else {
    lightColorScheme(
        primary = accent,
        onPrimary = Color.White,
        primaryContainer = accentAlt,
        onPrimaryContainer = accent,
        secondary = accentAlt,
        onSecondary = accent,
        secondaryContainer = raised,
        onSecondaryContainer = fg,
        tertiary = selection,
        onTertiary = accent,
        tertiaryContainer = panel,
        onTertiaryContainer = fg,
        background = bg,
        onBackground = fg,
        surface = panel,
        onSurface = fg,
        surfaceVariant = raised,
        onSurfaceVariant = muted,
        surfaceTint = accent,
        inverseSurface = fg,
        inverseOnSurface = bg,
        error = danger,
        onError = Color.White,
        errorContainer = danger.copy(alpha = 0.1f),
        onErrorContainer = danger,
        outline = border,
        outlineVariant = grid,
        scrim = Color.Black.copy(alpha = 0.3f)
    )
}

@Composable
fun KaraokeMobileTheme(
    palette: KaraokeThemePalette = NavyDarkPalette,
    dynamicColor: Boolean = false,
    content: @Composable () -> Unit
) {
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (palette.isDark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        else -> palette.toColorScheme()
    }
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = colorScheme.background.toArgb()
            window.navigationBarColor = colorScheme.surface.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !palette.isDark
            WindowCompat.getInsetsController(window, view).isAppearanceLightNavigationBars = !palette.isDark
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}
