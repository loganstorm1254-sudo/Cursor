package com.tapshare.app

import android.app.Application
import android.util.Log
import com.tapshare.app.service.TapShareService
import com.tapshare.app.util.PeerIdentity

class TapShareApp : Application() {
    override fun onCreate() {
        super.onCreate()
        try {
            PeerIdentity.ensure(this)
            TapShareService.ensureRunning(this)
        } catch (t: Throwable) {
            Log.e("TapShareApp", "startup failed", t)
        }
    }
}
