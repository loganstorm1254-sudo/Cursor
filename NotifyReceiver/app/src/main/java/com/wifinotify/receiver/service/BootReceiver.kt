package com.wifinotify.receiver.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != Intent.ACTION_BOOT_COMPLETED) return
        val prefs = context.getSharedPreferences(NotifyListenService.PREFS, Context.MODE_PRIVATE)
        if (prefs.getBoolean(NotifyListenService.KEY_AUTO_START, false)) {
            NotifyListenService.start(context)
        }
    }
}
