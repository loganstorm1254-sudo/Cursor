package com.tapshare.app.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Starts TapShare on every boot / package replace. Always on — no user toggle.
 */
class BootCompletedReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val action = intent?.action ?: return
        val relevant = action == Intent.ACTION_BOOT_COMPLETED ||
            action == Intent.ACTION_LOCKED_BOOT_COMPLETED ||
            action == Intent.ACTION_MY_PACKAGE_REPLACED ||
            action == "android.intent.action.QUICKBOOT_POWERON" ||
            action == "com.htc.intent.action.QUICKBOOT_POWERON"
        if (!relevant) return
        TapShareService.ensureRunning(context)
    }
}
