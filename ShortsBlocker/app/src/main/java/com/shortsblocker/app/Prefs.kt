package com.shortsblocker.app

import android.content.Context
import android.content.SharedPreferences

object Prefs {
    private const val NAME = "shorts_blocker"
    private const val KEY_ENABLED = "enabled"
    private const val KEY_BLOCKS = "blocks"
    private const val KEY_YOUTUBE = "block_youtube"
    private const val KEY_TIKTOK = "block_tiktok"

    private fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(NAME, Context.MODE_PRIVATE)

    fun isEnabled(context: Context): Boolean =
        prefs(context).getBoolean(KEY_ENABLED, true)

    fun setEnabled(context: Context, value: Boolean) {
        prefs(context).edit().putBoolean(KEY_ENABLED, value).apply()
    }

    fun blockYoutube(context: Context): Boolean =
        prefs(context).getBoolean(KEY_YOUTUBE, true)

    fun blockTiktok(context: Context): Boolean =
        prefs(context).getBoolean(KEY_TIKTOK, true)

    fun blockCount(context: Context): Int =
        prefs(context).getInt(KEY_BLOCKS, 0)

    fun incrementBlocks(context: Context): Int {
        val next = blockCount(context) + 1
        prefs(context).edit().putInt(KEY_BLOCKS, next).apply()
        return next
    }
}
