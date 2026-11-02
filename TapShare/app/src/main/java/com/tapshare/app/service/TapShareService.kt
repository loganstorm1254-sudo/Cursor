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
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.tapshare.app.R
import com.tapshare.app.transfer.BleBeacon
import com.tapshare.app.transfer.MediaPipe
import com.tapshare.app.ui.HomeActivity
import com.tapshare.app.ui.ReceivedMediaActivity
import com.tapshare.app.ui.TapAnimationActivity

/**
 * Always-active TapShare engine. Survives swipe-away via START_STICKY + foreground
 * notification, and restarts on boot via BootCompletedReceiver.
 */
class TapShareService : Service() {

    private lateinit var mediaPipe: MediaPipe
    private lateinit var bleBeacon: BleBeacon
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannels()
        promoteForeground()
        acquireWakeLock()
        mediaPipe = MediaPipe(applicationContext)
        bleBeacon = BleBeacon(applicationContext)
        bleBeacon.startAdvertising()
        mediaPipe.startListening { uri, mime ->
            onMediaReceived(uri, mime)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopSelf()
                return START_NOT_STICKY
            }
        }
        promoteForeground()
        return START_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // User swiped the app away — schedule ourselves back immediately.
        ensureRunning(applicationContext)
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        mediaPipe.stopListening()
        bleBeacon.stopAdvertising()
        wakeLock?.let {
            if (it.isHeld) it.release()
        }
        wakeLock = null
        // Best-effort restart if the system kills us.
        ensureRunning(applicationContext)
        super.onDestroy()
    }

    private fun onMediaReceived(uri: Uri, mime: String) {
        // Full-screen receive animation, then open the photo.
        val anim = Intent(this, TapAnimationActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            putExtra(TapAnimationActivity.EXTRA_MODE, TapAnimationActivity.MODE_RECEIVE)
            putExtra(TapAnimationActivity.EXTRA_URI, uri.toString())
            putExtra(TapAnimationActivity.EXTRA_MIME, mime)
        }
        startActivity(anim)

        val open = Intent(this, ReceivedMediaActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            putExtra(ReceivedMediaActivity.EXTRA_URI, uri.toString())
            putExtra(ReceivedMediaActivity.EXTRA_MIME, mime)
        }
        // ReceivedMediaActivity is also launched from the animation when it finishes;
        // keep a high-priority heads-up as backup.
        val pending = PendingIntent.getActivity(
            this,
            uri.hashCode(),
            open,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(this, CHANNEL_INCOMING)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.received_title))
            .setContentText(getString(R.string.save_open))
            .setContentIntent(pending)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .build()
        getSystemService(NotificationManager::class.java)
            .notify(INCOMING_NOTIFICATION_ID, notification)
    }

    private fun promoteForeground() {
        val notification = buildOngoing()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ServiceCompat.startForeground(
                this,
                SERVICE_NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE or
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
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
        val pm = getSystemService(PowerManager::class.java)
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "TapShare:KeepAlive").apply {
            setReferenceCounted(false)
            acquire(10 * 60 * 60 * 1000L) // refreshed by sticky restarts
        }
    }

    companion object {
        const val ACTION_STOP = "com.tapshare.app.STOP"
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
    }
}
