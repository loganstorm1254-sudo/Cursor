package com.shortsblocker.app.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.shortsblocker.app.Prefs
import com.shortsblocker.app.service.ShortsGuardService

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val action = intent?.action ?: return
        if (action != Intent.ACTION_BOOT_COMPLETED &&
            action != Intent.ACTION_LOCKED_BOOT_COMPLETED &&
            action != "android.intent.action.QUICKBOOT_POWERON"
        ) {
            return
        }
        if (!Prefs.isEnabled(context)) return

        val service = Intent(context, ShortsGuardService::class.java)
        try {
            context.startForegroundService(service)
        } catch (_: Exception) {
            context.startService(service)
        }
    }
}
