package com.tapshare.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.tapshare.app.R
import com.tapshare.app.transfer.NearbyEngine
import com.tapshare.app.ui.HomeActivity
import com.tapshare.app.ui.ReceivedMediaActivity
import com.tapshare.app.ui.TapAnimationActivity
import com.tapshare.app.util.ShareSession

/**
 * Always-on TapShare engine using Nearby Connections (Bluetooth/Wi‑Fi).
 */
class TapShareService : Service() {

    private var nearby: NearbyEngine? = null
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        try {
            createChannels()
            promoteForeground()
            acquireWakeLock()
            val engine = NearbyEngine(applicationContext)
            nearby = engine
            sharedEngine = engine
            engine.start { uri, mime -> onMediaReceived(uri, mime) }
        } catch (t: Throwable) {
            Log.e(TAG, "onCreate failed", t)
            try {
                promoteForeground()
            } catch (_: Exception) {
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_RESTART_NEARBY -> {
                try {
                    val engine = nearby ?: NearbyEngine(applicationContext).also {
                        nearby = it
                        sharedEngine = it
                        it.start { uri, mime -> onMediaReceived(uri, mime) }
                    }
                    engine.restart()
                } catch (t: Throwable) {
                    Log.e(TAG, "restart nearby failed", t)
                }
            }
        }
        try {
            promoteForeground()
            if (nearby == null) {
                val engine = NearbyEngine(applicationContext)
                nearby = engine
                sharedEngine = engine
                engine.start { uri, mime -> onMediaReceived(uri, mime) }
            }
        } catch (t: Throwable) {
            Log.e(TAG, "onStartCommand failed", t)
        }
        return START_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        try {
            ensureRunning(applicationContext)
        } catch (_: Exception) {
        }
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        try {
            nearby?.stop()
        } catch (_: Exception) {
        }
        nearby = null
        sharedEngine = null
        try {
            wakeLock?.let { if (it.isHeld) it.release() }
        } catch (_: Exception) {
        }
        wakeLock = null
        try {
            ensureRunning(applicationContext)
        } catch (_: Exception) {
        }
        super.onDestroy()
    }

    private fun onMediaReceived(uri: Uri, mime: String) {
        try {
            ShareSession.clear()
            val anim = Intent(this, TapAnimationActivity::class.java).apply {
                addFlags(
                    Intent.FLAG_ACTIVITY_NEW_TASK or
                        Intent.FLAG_ACTIVITY_CLEAR_TOP or
                        Intent.FLAG_ACTIVITY_SINGLE_TOP
                )
                putExtra(TapAnimationActivity.EXTRA_MODE, TapAnimationActivity.MODE_RECEIVE)
                putExtra(TapAnimationActivity.EXTRA_URI, uri.toString())
                putExtra(TapAnimationActivity.EXTRA_MIME, mime)
            }
            try {
                startActivity(anim)
            } catch (t: Throwable) {
                Log.w(TAG, "launch anim failed", t)
            }

            val open = Intent(this, ReceivedMediaActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                putExtra(ReceivedMediaActivity.EXTRA_URI, uri.toString())
                putExtra(ReceivedMediaActivity.EXTRA_MIME, mime)
            }
            val pending = PendingIntent.getActivity(
                this,
                uri.hashCode(),
                open,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val fullScreen = PendingIntent.getActivity(
                this,
                uri.hashCode() + 1,
                anim,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val notification = NotificationCompat.Builder(this, CHANNEL_INCOMING)
                .setSmallIcon(R.drawable.ic_notification)
                .setContentTitle(getString(R.string.received_title))
                .setContentText(getString(R.string.save_open))
                .setContentIntent(pending)
                .setFullScreenIntent(fullScreen, true)
                .setAutoCancel(true)
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .build()
            getSystemService(NotificationManager::class.java)
                .notify(INCOMING_NOTIFICATION_ID, notification)
        } catch (t: Throwable) {
            Log.e(TAG, "onMediaReceived failed", t)
        }
    }

    private fun promoteForeground() {
        val notification = buildOngoing()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ServiceCompat.startForeground(
                this,
                SERVICE_NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE
            )
        } else {
            startForeground(SERVICE_NOTIFICATION_ID, notification)
        }
    }

    private fun buildOngoing(): Notification {
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, HomeActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_SERVICE)
            .setContentTitle(getString(R.string.service_title))
            .setContentText(getString(R.string.service_text))
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(open)
            .setOngoing(true)
            .setSilent(true)
            .build()
    }

    private fun createChannels() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_SERVICE,
                getString(R.string.service_channel),
                NotificationManager.IMPORTANCE_LOW
            )
        )
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_INCOMING,
                getString(R.string.incoming_channel),
                NotificationManager.IMPORTANCE_HIGH
            )
        )
    }

    private fun acquireWakeLock() {
        try {
            val pm = getSystemService(PowerManager::class.java)
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "TapShare:KeepAlive").apply {
                setReferenceCounted(false)
                acquire(6 * 60 * 60 * 1000L)
            }
        } catch (_: Exception) {
        }
    }

    companion object {
        private const val TAG = "TapShareService"
        const val ACTION_STOP = "com.tapshare.app.STOP"
        const val ACTION_RESTART_NEARBY = "com.tapshare.app.RESTART_NEARBY"
        const val CHANNEL_SERVICE = "tapshare_service"
        const val CHANNEL_INCOMING = "tapshare_incoming"
        private const val SERVICE_NOTIFICATION_ID = 42
        private const val INCOMING_NOTIFICATION_ID = 43

        @Volatile
        var sharedEngine: NearbyEngine? = null

        fun ensureRunning(context: Context) {
            val intent = Intent(context, TapShareService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun restartNearby(context: Context) {
            val intent = Intent(context, TapShareService::class.java).apply {
                action = ACTION_RESTART_NEARBY
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}
