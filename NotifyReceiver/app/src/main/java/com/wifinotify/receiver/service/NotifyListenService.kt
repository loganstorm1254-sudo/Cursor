package com.wifinotify.receiver.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.wifinotify.receiver.Protocol
import com.wifinotify.receiver.R
import com.wifinotify.receiver.net.BtNotifyServer
import com.wifinotify.receiver.net.IncomingNotify
import com.wifinotify.receiver.ui.MainActivity

class NotifyListenService : Service() {

    private var server: BtNotifyServer? = null
    private var notifyId = 1000

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannels()
        startAsForeground()
        server = BtNotifyServer(
            context = applicationContext,
            onNotify = { payload, remote -> showIncoming(payload, remote) },
            onStatus = { status ->
                sendBroadcast(
                    Intent(ACTION_STATUS).putExtra(EXTRA_STATUS, status)
                        .setPackage(packageName)
                )
                updateForegroundText(status)
            }
        ).also { it.start() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_MAKE_DISCOVERABLE -> {
                // Activity handles the system discoverable intent; nothing here.
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        server?.stop()
        server = null
        sendBroadcast(
            Intent(ACTION_STATUS).putExtra(EXTRA_STATUS, "Stopped")
                .setPackage(packageName)
        )
        super.onDestroy()
    }

    private fun startAsForeground() {
        val notification = buildServiceNotification(getString(R.string.service_text_starting))
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

    private fun updateForegroundText(status: String) {
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(SERVICE_NOTIFICATION_ID, buildServiceNotification(status))
    }

    private fun buildServiceNotification(text: String): Notification {
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, Protocol.SERVICE_CHANNEL_ID)
            .setContentTitle(getString(R.string.service_title))
            .setContentText(text)
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
        const val ACTION_MAKE_DISCOVERABLE = "com.wifinotify.receiver.DISCOVERABLE"
        const val ACTION_STATUS = "com.wifinotify.receiver.STATUS"
        const val ACTION_MESSAGE = "com.wifinotify.receiver.MESSAGE"
        const val EXTRA_STATUS = "status"
        const val EXTRA_TITLE = "title"
        const val EXTRA_MESSAGE = "message"
        const val EXTRA_FROM = "from"
        private const val SERVICE_NOTIFICATION_ID = 1

        fun start(context: Context) {
            context.startForegroundService(Intent(context, NotifyListenService::class.java))
        }

        fun stop(context: Context) {
            context.startService(
                Intent(context, NotifyListenService::class.java).apply { action = ACTION_STOP }
            )
        }

        fun bluetoothEnabled(context: Context): Boolean {
            val adapter = context.getSystemService(BluetoothManager::class.java)?.adapter
            return adapter?.isEnabled == true
        }

        fun bluetoothAdapter(context: Context): BluetoothAdapter? {
            return context.getSystemService(BluetoothManager::class.java)?.adapter
        }
    }
}
