package com.tapshare.app.util

import android.content.Context
import android.os.Build
import java.util.UUID

object PeerIdentity {
    private const val PREFS = "tapshare_identity"
    private const val KEY_ID = "peer_id"
    private const val KEY_NAME = "display_name"

    fun ensure(context: Context) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        if (!prefs.contains(KEY_ID)) {
            prefs.edit()
                .putString(KEY_ID, UUID.randomUUID().toString())
                .putString(KEY_NAME, Build.MODEL ?: "Samsung")
                .apply()
        }
    }

    fun id(context: Context): String {
        ensure(context)
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_ID, "")!!
    }

    fun displayName(context: Context): String {
        ensure(context)
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_NAME, Build.MODEL ?: "Samsung")!!
    }

    fun setDisplayName(context: Context, name: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_NAME, name.trim().ifBlank { Build.MODEL ?: "Samsung" })
            .apply()
    }
}
