package com.karaoke.mobile.ui.theme

import android.app.Activity
import android.os.Build
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
    danger = NavyDanger,
    accentFg = Color.White
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
    danger = Color(0xFFB83F48),
    accentFg = Color.White
)

val PurpleDarkPalette = KaraokeThemePalette(
    name = "purple_dark",
    isDark = true,
    accent = PurplePrimary,
    accentAlt = PurplePrimaryAlt,
    bg = PurpleBg,
    panel = PurplePanel,
    raised = PurpleRaised,
    inputBg = PurplePanel,
    fg = Color(0xFFF6EEFC),
    muted = Color(0xFFB29EC2),
    border = Color(0xFF473456),
    canvas = Color(0xFF140F1A),
    canvasAlt = Color(0xFF1B1423),
    grid = Color(0xFF33243F),
    selection = PurplePrimaryAlt,
    success = Color(0xFF72D19A),
    warning = Color(0xFFE6BD5B),
    danger = Color(0xFFFF747E),
    accentFg = Color.White
)

val RedDarkPalette = KaraokeThemePalette(
    name = "red_dark",
    isDark = true,
    accent = RedPrimary,
    accentAlt = RedPrimaryAlt,
    bg = RedBg,
    panel = RedPanel,
    raised = RedRaised,
    inputBg = RedPanel,
    fg = Color(0xFFFCEEEE),
    muted = Color(0xFFC29EA3),
    border = Color(0xFF563439),
    canvas = Color(0xFF180F11),
    canvasAlt = Color(0xFF211417),
    grid = Color(0xFF3F2428),
    selection = RedPrimaryAlt,
    success = Color(0xFF72D19A),
    warning = Color(0xFFE6BD5B),
    danger = Color(0xFFFF747E),
    accentFg = Color.White
)

val GreenDarkPalette = KaraokeThemePalette(
    name = "green_dark",
    isDark = true,
    accent = GreenPrimary,
    accentAlt = GreenPrimaryAlt,
    bg = GreenBg,
    panel = GreenPanel,
    raised = GreenRaised,
    inputBg = GreenPanel,
    fg = Color(0xFFEEFCF1),
    muted = Color(0xFF9EC2A5),
    border = Color(0xFF34563C),
    canvas = Color(0xFF0F1812),
    canvasAlt = Color(0xFF142118),
    grid = Color(0xFF243F2A),
    selection = GreenPrimaryAlt,
    success = Color(0xFF72D19A),
    warning = Color(0xFFE6BD5B),
    danger = Color(0xFFFF747E),
    accentFg = Color.White
)

val YellowDarkPalette = KaraokeThemePalette(
    name = "yellow_dark",
    isDark = true,
    accent = YellowPrimary,
    accentAlt = YellowPrimaryAlt,
    bg = YellowBg,
    panel = YellowPanel,
    raised = YellowRaised,
    inputBg = YellowPanel,
    fg = Color(0xFFFCF9EE),
    muted = Color(0xFFC2BBA0),
    border = Color(0xFF564F34),
    canvas = Color(0xFF18160E),
    canvasAlt = Color(0xFF211E13),
    grid = Color(0xFF3F3924),
    selection = YellowPrimaryAlt,
    success = Color(0xFF72D19A),
    warning = Color(0xFFE6BD5B),
    danger = Color(0xFFFF747E),
    accentFg = Color(0xFF17130A)
)

val VaporDarkPalette = KaraokeThemePalette(
    name = "vapor_dark",
    isDark = true,
    accent = VaporPrimary,
    accentAlt = VaporPrimaryAlt,
    bg = VaporBg,
    panel = VaporPanel,
    raised = VaporRaised,
    inputBg = VaporPanel,
    fg = Color(0xFFF9ECFF),
    muted = Color(0xFFBBA5C8),
    border = Color(0xFF4B3561),
    canvas = Color(0xFF100A19),
    canvasAlt = Color(0xFF191024),
    grid = Color(0xFF352348),
    selection = VaporPrimaryAlt,
    success = Color(0xFF72D19A),
    warning = Color(0xFFE6BD5B),
    danger = Color(0xFFFF747E),
    accentFg = Color(0xFF251026)
)

val CappuccinoDarkPalette = KaraokeThemePalette(
    name = "cappuccino_dark",
    isDark = true,
    accent = CappuccinoPrimary,
    accentAlt = CappuccinoPrimaryAlt,
    bg = CappuccinoBg,
    panel = CappuccinoPanel,
    raised = CappuccinoRaised,
    inputBg = CappuccinoPanel,
    fg = Color(0xFFF1E5DC),
    muted = Color(0xFFB5A398),
    border = Color(0xFF4D3E35),
    canvas = Color(0xFF15110F),
    canvasAlt = Color(0xFF1E1814),
    grid = Color(0xFF392E28),
    selection = CappuccinoPrimaryAlt,
    success = Color(0xFF72D19A),
    warning = Color(0xFFE6BD5B),
    danger = Color(0xFFFF747E),
    accentFg = Color(0xFF21150F)
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
