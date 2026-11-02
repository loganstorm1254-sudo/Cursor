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
import com.tapshare.app.transfer.BleBeacon
import com.tapshare.app.transfer.GattTransfer
import com.tapshare.app.transfer.MediaPipe
import com.tapshare.app.ui.HomeActivity
import com.tapshare.app.ui.ReceivedMediaActivity
import com.tapshare.app.ui.TapAnimationActivity
import com.tapshare.app.util.ShareSession

/**
 * Always-active TapShare engine: BLE beacon + Bluetooth listener.
 * Survives swipe-away via START_STICKY and restarts on boot.
 */
class TapShareService : Service() {

    private var mediaPipe: MediaPipe? = null
    private var bleBeacon: BleBeacon? = null
    private var gattTransfer: GattTransfer? = null
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        try {
            createChannels()
            promoteForeground()
            acquireWakeLock()
            val pipe = MediaPipe(applicationContext)
            val beacon = BleBeacon(applicationContext)
            val gatt = GattTransfer(applicationContext)
            mediaPipe = pipe
            bleBeacon = beacon
            gattTransfer = gatt
            beacon.startAdvertising()
            gatt.startServer { uri, mime -> onMediaReceived(uri, mime) }
            pipe.startListening { uri, mime ->
                onMediaReceived(uri, mime)
            }
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
            ACTION_REFRESH_BEACON -> {
                try {
                    bleBeacon?.refreshAdvertising()
                } catch (_: Exception) {
                }
            }
        }
        try {
            promoteForeground()
            if (bleBeacon == null || mediaPipe == null || gattTransfer == null) {
                if (bleBeacon == null) {
                    bleBeacon = BleBeacon(applicationContext).also { it.startAdvertising() }
                }
                if (gattTransfer == null) {
                    gattTransfer = GattTransfer(applicationContext).also { gatt ->
                        gatt.startServer { uri, mime -> onMediaReceived(uri, mime) }
                    }
                }
                if (mediaPipe == null) {
                    mediaPipe = MediaPipe(applicationContext).also { pipe ->
                        pipe.startListening { uri, mime -> onMediaReceived(uri, mime) }
                    }
                }
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
            mediaPipe?.stopListening()
        } catch (_: Exception) {
        }
        try {
            gattTransfer?.stopServer()
        } catch (_: Exception) {
        }
        try {
            bleBeacon?.stopAdvertising()
        } catch (_: Exception) {
        }
        mediaPipe = null
        gattTransfer = null
        bleBeacon = null
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
            bleBeacon?.refreshAdvertising()

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
                Log.w(TAG, "Could not launch animation from service", t)
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
                .setCategory(NotificationCompat.CATEGORY_MESSAGE)
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
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
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
        const val ACTION_REFRESH_BEACON = "com.tapshare.app.REFRESH_BEACON"
        const val CHANNEL_SERVICE = "tapshare_service"
        const val CHANNEL_INCOMING = "tapshare_incoming"
        private const val SERVICE_NOTIFICATION_ID = 42
        private const val INCOMING_NOTIFICATION_ID = 43

        fun ensureRunning(context: Context) {
            val intent = Intent(context, TapShareService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun refreshBeacon(context: Context) {
            val intent = Intent(context, TapShareService::class.java).apply {
                action = ACTION_REFRESH_BEACON
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}
