package com.tapshare.app

import android.app.Application
import android.content.Intent
import android.os.Build
import com.tapshare.app.service.TapShareService
import com.tapshare.app.util.PeerIdentity

class TapShareApp : Application() {
    override fun onCreate() {
        super.onCreate()
        PeerIdentity.ensure(this)
        // Keep TapShare alive from the moment the process starts.
        startService()
    }

    private fun startService() {
        val intent = Intent(this, TapShareService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }
}
