package com.darthmotzkus.pcmplayer

import android.content.Context
import androidx.preference.PreferenceManager

enum class AppTheme(
    val key: String,
    val displayName: String,
    val primary: Int,   // accent
    val primaryLight: Int,
    val background: Int,
    val surface: Int,
    val border: Int,
) {
    OCEAN(
        key = "ocean", displayName = "Ocean",
        primary = 0xFF4FA3D1.toInt(), primaryLight = 0xFF8FD0F2.toInt(),
        background = 0xFF0D1B2A.toInt(), surface = 0xFF142838.toInt(), border = 0xFF1F3A52.toInt(),
    ),
    FOREST(
        key = "forest", displayName = "Forest",
        primary = 0xFF4EAC5B.toInt(), primaryLight = 0xFF8FD89A.toInt(),
        background = 0xFF0C1810.toInt(), surface = 0xFF14241A.toInt(), border = 0xFF1F3A28.toInt(),
    ),
    SUNSET(
        key = "sunset", displayName = "Sunset",
        primary = 0xFFEF9F27.toInt(), primaryLight = 0xFFFAC775.toInt(),
        background = 0xFF1A1410.toInt(), surface = 0xFF241A14.toInt(), border = 0xFF3A2A1F.toInt(),
    ),
    GRAPHITE(
        key = "graphite", displayName = "Graphite",
        primary = 0xFFC8C8C8.toInt(), primaryLight = 0xFFE8E8E8.toInt(),
        background = 0xFF101010.toInt(), surface = 0xFF1A1A1A.toInt(), border = 0xFF2A2A2A.toInt(),
    );

    companion object {
        fun byKey(k: String?): AppTheme = entries.firstOrNull { it.key == k } ?: OCEAN
    }
}

object ThemeManager {
    private const val KEY_THEME = "selected_theme"

    fun current(ctx: Context): AppTheme {
        val prefs = PreferenceManager.getDefaultSharedPreferences(ctx)
        return AppTheme.byKey(prefs.getString(KEY_THEME, AppTheme.OCEAN.key))
    }

    fun set(ctx: Context, theme: AppTheme) {
        PreferenceManager.getDefaultSharedPreferences(ctx)
            .edit()
            .putString(KEY_THEME, theme.key)
            .apply()
    }
}
