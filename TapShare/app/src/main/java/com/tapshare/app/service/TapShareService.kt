package com.tapshare.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.FileProvider
import com.tapshare.app.R
import com.tapshare.app.transfer.BumpDetector
import com.tapshare.app.transfer.NearbyEngine
import com.tapshare.app.ui.HomeActivity
import com.tapshare.app.ui.ReceivedMediaActivity
import com.tapshare.app.ui.TapAnimationActivity
import com.tapshare.app.util.ShareSession
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Always-on engine. Listens for a real phone-top tap; if Samsung Gallery (or our
 * viewer) is showing a photo, shares it. Does nothing when phones aren't tapped.
 */
class TapShareService : Service() {

    private var nearby: NearbyEngine? = null
    private var bumpDetector: BumpDetector? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private val sharing = AtomicBoolean(false)
    private val mainHandler = Handler(Looper.getMainLooper())

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
            bumpDetector = BumpDetector(applicationContext) {
                mainHandler.post { onPhoneTapped() }
            }.also { it.start() }
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
        }
        try {
            promoteForeground()
            if (nearby == null) {
                val engine = NearbyEngine(applicationContext)
                nearby = engine
                sharedEngine = engine
                engine.start { uri, mime -> onMediaReceived(uri, mime) }
            }
            if (bumpDetector == null) {
                bumpDetector = BumpDetector(applicationContext) {
                    mainHandler.post { onPhoneTapped() }
                }.also { it.start() }
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
            bumpDetector?.stop()
        } catch (_: Exception) {
        }
        bumpDetector = null
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

    /**
     * Physical tops-tap. Only shares when Gallery (or our photo viewer) is up.
     * Always signals the bump so a peer that is sharing can confirm the tap.
     */
    private fun onPhoneTapped() {
        val engine = nearby ?: return
        // Always announce our tap so the sender can verify both phones knocked.
        Thread { engine.signalLocalTap() }.start()
        vibrateTap()

        val galleryUp = GalleryWatchService.isGalleryOnScreen()
        val session = ShareSession.get()
        if (!galleryUp && session == null) {
            Log.i(TAG, "tap ignored — not in gallery")
            return
        }
        if (!sharing.compareAndSet(false, true)) return

        if (session != null && !galleryUp) {
            // In our own viewer with a selected photo.
            beginSend(session)
            return
        }

        // Samsung Gallery / Photos on screen — capture what's showing.
        val watch = GalleryWatchService.instance
        if (watch == null) {
            toast(getString(R.string.enable_accessibility_short))
            sharing.set(false)
            return
        }
        watch.captureScreen { bitmap ->
            if (bitmap == null) {
                // Fallback: use in-app session if any.
                val fallback = ShareSession.get()
                if (fallback != null) {
                    beginSend(fallback)
                } else {
                    toast(getString(R.string.capture_failed))
                    sharing.set(false)
                }
                return@captureScreen
            }
            val uri = saveBitmap(bitmap)
            bitmap.recycle()
            if (uri == null) {
                toast(getString(R.string.capture_failed))
                sharing.set(false)
                return@captureScreen
            }
            val media = ShareSession.ActiveMedia(
                uri = uri,
                mimeType = "image/jpeg",
                displayName = "gallery_tap_${System.currentTimeMillis()}.jpg"
            )
            ShareSession.set(media)
            beginSend(media)
        }
    }

    private fun beginSend(media: ShareSession.ActiveMedia) {
        try {
            val anim = Intent(this, TapAnimationActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                putExtra(TapAnimationActivity.EXTRA_MODE, TapAnimationActivity.MODE_SEND)
                putExtra(TapAnimationActivity.EXTRA_URI, media.uri.toString())
                putExtra(TapAnimationActivity.EXTRA_MIME, media.mimeType)
                putExtra(TapAnimationActivity.EXTRA_AUTO, true)
            }
            startActivity(anim)
        } catch (t: Throwable) {
            Log.e(TAG, "could not open animation", t)
            // Send without UI.
            Thread {
                try {
                    nearby?.sendAfterTap(media)
                } finally {
                    sharing.set(false)
                }
            }.start()
            return
        }
        // Animation activity performs the send; release the lock after a beat.
        mainHandler.postDelayed({ sharing.set(false) }, 12_000)
    }

    private fun saveBitmap(bitmap: Bitmap): Uri? {
        return try {
            val file = File(cacheDir, "tap_capture_${System.currentTimeMillis()}.jpg")
            FileOutputStream(file).use { out ->
                bitmap.compress(Bitmap.CompressFormat.JPEG, 92, out)
            }
            FileProvider.getUriForFile(this, "$packageName.files", file)
        } catch (t: Throwable) {
            Log.e(TAG, "saveBitmap failed", t)
            null
        }
    }

    private fun toast(msg: String) {
        mainHandler.post {
            try {
                Toast.makeText(applicationContext, msg, Toast.LENGTH_SHORT).show()
            } catch (_: Exception) {
            }
        }
    }

    private fun vibrateTap() {
        try {
            val vibrator = if (Build.VERSION.SDK_INT >= 31) {
                getSystemService(VibratorManager::class.java).defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                getSystemService(VIBRATOR_SERVICE) as Vibrator
            }
            vibrator.vibrate(VibrationEffect.createOneShot(35, VibrationEffect.DEFAULT_AMPLITUDE))
        } catch (_: Exception) {
        }
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
        val text = if (GalleryWatchService.isEnabled()) {
            getString(R.string.service_text_ready)
        } else {
            getString(R.string.service_text_need_access)
        }
        return NotificationCompat.Builder(this, CHANNEL_SERVICE)
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
    }
}
