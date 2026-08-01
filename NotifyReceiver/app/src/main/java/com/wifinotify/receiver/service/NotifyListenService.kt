package com.wifinotify.receiver.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.wifinotify.receiver.Protocol
import com.wifinotify.receiver.R
import com.wifinotify.receiver.net.IncomingNotify
import com.wifinotify.receiver.net.NotifyServer
import com.wifinotify.receiver.net.localIpv4Addresses
import com.wifinotify.receiver.ui.MainActivity

class NotifyListenService : Service() {

    private var server: NotifyServer? = null
    private var notifyId = 1000
    private var multicastLock: WifiManager.MulticastLock? = null
    private var wifiLock: WifiManager.WifiLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannels()
        startAsForeground()
        acquireWifiLocks()
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        server = NotifyServer(
            context = applicationContext,
            deviceNameProvider = {
                prefs.getString(KEY_DEVICE_NAME, null)
                    ?.ifBlank { null }
                    ?: (Build.MODEL ?: "Android")
            },
            onNotify = { payload, remote -> showIncoming(payload, remote) },
            onStatus = { status ->
                sendBroadcast(
                    Intent(ACTION_STATUS).putExtra(EXTRA_STATUS, status)
                        .setPackage(packageName)
                )
            }
        ).also { it.start() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_REFRESH_NAME -> {
                // Name is read live from prefs on each discovery reply.
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        server?.stop()
        server = null
        releaseWifiLocks()
        sendBroadcast(
            Intent(ACTION_STATUS).putExtra(EXTRA_STATUS, "Stopped")
                .setPackage(packageName)
        )
        super.onDestroy()
    }

    private fun acquireWifiLocks() {
        try {
            val wifi = applicationContext.getSystemService(WIFI_SERVICE) as WifiManager
            multicastLock = wifi.createMulticastLock("wifi_notify_receiver").also {
                it.setReferenceCounted(true)
                it.acquire()
            }
            val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                WifiManager.WIFI_MODE_FULL_LOW_LATENCY
            } else {
                @Suppress("DEPRECATION")
                WifiManager.WIFI_MODE_FULL_HIGH_PERF
            }
            wifiLock = wifi.createWifiLock(mode, "wifi_notify_receiver").also {
                it.setReferenceCounted(true)
                it.acquire()
            }
        } catch (_: Exception) {
        }
    }

    private fun releaseWifiLocks() {
        try {
            multicastLock?.takeIf { it.isHeld }?.release()
        } catch (_: Exception) {
        }
        try {
            wifiLock?.takeIf { it.isHeld }?.release()
        } catch (_: Exception) {
        }
        multicastLock = null
        wifiLock = null
    }

    private fun startAsForeground() {
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val ips = localIpv4Addresses().joinToString(", ").ifBlank { "waiting for Wi‑Fi…" }
        val notification = NotificationCompat.Builder(this, Protocol.SERVICE_CHANNEL_ID)
            .setContentTitle(getString(R.string.service_title))
            .setContentText(getString(R.string.service_text, ips))
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(open)
            .setOngoing(true)
            .setSilent(true)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ServiceCompat.startForeground(
                this,
                SERVICE_NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } else {
            startForeground(SERVICE_NOTIFICATION_ID, notification)
        }
    }

    private fun createChannels() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                Protocol.SERVICE_CHANNEL_ID,
                getString(R.string.channel_service),
                NotificationManager.IMPORTANCE_LOW
            )
        )
        manager.createNotificationChannel(
            NotificationChannel(
                Protocol.CHANNEL_ID,
                getString(R.string.channel_incoming),
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = getString(R.string.channel_incoming_desc)
                enableVibration(true)
            }
        )
    }

    private fun showIncoming(payload: IncomingNotify, remote: String) {
        val manager = getSystemService(NotificationManager::class.java)
        val open = PendingIntent.getActivity(
            this,
            notifyId,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val from = payload.from?.takeIf { it.isNotBlank() } ?: remote
        val notification: Notification = NotificationCompat.Builder(this, Protocol.CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(payload.title)
            .setContentText(payload.message)
            .setStyle(
                NotificationCompat.BigTextStyle()
                    .bigText(payload.message)
                    .setSummaryText(getString(R.string.from_label, from))
            )
            .setContentIntent(open)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        manager.notify(notifyId++, notification)

        sendBroadcast(
            Intent(ACTION_MESSAGE)
                .putExtra(EXTRA_TITLE, payload.title)
                .putExtra(EXTRA_MESSAGE, payload.message)
                .putExtra(EXTRA_FROM, from)
                .setPackage(packageName)
        )
    }

    companion object {
        const val PREFS = "receiver_prefs"
        const val KEY_DEVICE_NAME = "device_name"
        const val KEY_AUTO_START = "auto_start"
        const val ACTION_STOP = "com.wifinotify.receiver.STOP"
        const val ACTION_REFRESH_NAME = "com.wifinotify.receiver.REFRESH_NAME"
        const val ACTION_STATUS = "com.wifinotify.receiver.STATUS"
        const val ACTION_MESSAGE = "com.wifinotify.receiver.MESSAGE"
        const val EXTRA_STATUS = "status"
        const val EXTRA_TITLE = "title"
        const val EXTRA_MESSAGE = "message"
        const val EXTRA_FROM = "from"
        private const val SERVICE_NOTIFICATION_ID = 1

        fun start(context: Context) {
            val intent = Intent(context, NotifyListenService::class.java)
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            val intent = Intent(context, NotifyListenService::class.java).apply {
                action = ACTION_STOP
            }
            context.startService(intent)
        }
    }
}
