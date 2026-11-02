package com.tapshare.app.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityManager
import java.util.concurrent.Executor
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicReference

/**
 * Watches when Samsung Gallery is on screen and can capture what's showing
 * after a phone-top tap. Kept crash-proof so Android/Samsung don't revoke access.
 */
class GalleryWatchService : AccessibilityService() {

    private val mainHandler = Handler(Looper.getMainLooper())

    override fun onCreate() {
        super.onCreate()
        instance = this
        Log.i(TAG, "onCreate")
    }

    override fun onServiceConnected() {
        // Never throw from here — Samsung will show "denied access" and flip the toggle off.
        try {
            instance = this
            val info = serviceInfo ?: AccessibilityServiceInfo()
            info.eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED or
                AccessibilityEvent.TYPE_WINDOWS_CHANGED or
                AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
            info.feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
            info.notificationTimeout = 200
            info.flags = info.flags or
                AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or
                AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS or
                AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
            serviceInfo = info
            Log.i(TAG, "Gallery watch connected")

            // Soft nudge the share service later — never startForegroundService
            // synchronously here (Android 12+ can crash us and revoke accessibility).
            mainHandler.postDelayed({
                try {
                    val running = Intent(applicationContext, TapShareService::class.java)
                    // startService is safer from background than startForegroundService
                    // if the FGS is already up; ensureRunning handles O+.
                    TapShareService.ensureRunning(applicationContext)
                } catch (t: Throwable) {
                    Log.w(TAG, "deferred ensureRunning failed", t)
                }
            }, 1500L)
        } catch (t: Throwable) {
            Log.e(TAG, "onServiceConnected failed", t)
        }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        try {
            if (event == null) return
            val pkg = event.packageName?.toString() ?: return
            when (event.eventType) {
                AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED,
                AccessibilityEvent.TYPE_WINDOWS_CHANGED,
                AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> {
                    foregroundPackage.set(pkg)
                }
            }
        } catch (t: Throwable) {
            Log.w(TAG, "onAccessibilityEvent", t)
        }
    }

    override fun onInterrupt() = Unit

    override fun onUnbind(intent: Intent?): Boolean {
        if (instance === this) instance = null
        return super.onUnbind(intent)
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    fun captureScreen(onResult: (Bitmap?) -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            onResult(null)
            return
        }
        try {
            takeScreenshot(
                Display.DEFAULT_DISPLAY,
                screenshotExecutor,
                object : TakeScreenshotCallback {
                    override fun onSuccess(screenshot: ScreenshotResult) {
                        try {
                            val buffer = screenshot.hardwareBuffer
                            val colorSpace = screenshot.colorSpace
                            val bitmap = Bitmap.wrapHardwareBuffer(buffer, colorSpace)
                                ?.copy(Bitmap.Config.ARGB_8888, false)
                            buffer.close()
                            onResult(bitmap)
                        } catch (t: Throwable) {
                            Log.e(TAG, "screenshot wrap failed", t)
                            onResult(null)
                        }
                    }

                    override fun onFailure(errorCode: Int) {
                        Log.w(TAG, "screenshot failed code=$errorCode")
                        onResult(null)
                    }
                }
            )
        } catch (t: Throwable) {
            Log.e(TAG, "takeScreenshot threw", t)
            onResult(null)
        }
    }

    companion object {
        private const val TAG = "TapShareGalleryWatch"
        private val foregroundPackage = AtomicReference("")
        private val screenshotExecutor: Executor = Executors.newSingleThreadExecutor()

        @Volatile
        var instance: GalleryWatchService? = null
            private set

        private val GALLERY_PACKAGES = setOf(
            "com.sec.android.gallery3d",
            "com.samsung.android.gallery3d",
            "com.samsung.android.app.gallery",
            "com.google.android.apps.photos",
            "com.android.gallery3d",
            "com.miui.gallery",
            "com.oneplus.gallery",
            "com.coloros.gallery3d",
            "com.tapshare.app"
        )

        fun isEnabled(context: Context): Boolean {
            if (instance != null) return true
            return try {
                val expected = ComponentName(context, GalleryWatchService::class.java)
                    .flattenToString()
                val enabled = Settings.Secure.getString(
                    context.contentResolver,
                    Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
                ) ?: return false
                enabled.split(':').any { piece ->
                    piece.equals(expected, ignoreCase = true) ||
                        piece.contains(context.packageName, ignoreCase = true) &&
                        piece.contains("GalleryWatchService", ignoreCase = true)
                }
            } catch (_: Exception) {
                false
            }
        }

        /** Soft check via AccessibilityManager. */
        fun isEnabledViaManager(context: Context): Boolean {
            return try {
                val am = context.getSystemService(AccessibilityManager::class.java) ?: return false
                val expected = ComponentName(context, GalleryWatchService::class.java)
                am.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
                    .any { it.resolveInfo?.serviceInfo?.let { si ->
                        si.packageName == expected.packageName && si.name == expected.className
                    } == true }
            } catch (_: Exception) {
                false
            }
        }

        fun isGalleryOnScreen(): Boolean {
            val pkg = foregroundPackage.get()
            if (pkg.isBlank()) return false
            if (GALLERY_PACKAGES.contains(pkg)) return true
            return pkg.contains("gallery", ignoreCase = true) ||
                pkg.contains("photos", ignoreCase = true)
        }

        fun openAccessibilitySettings(context: Context) {
            try {
                // Try to deep-link straight to our service on some Samsungs.
                val component = ComponentName(context, GalleryWatchService::class.java)
                val intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    putExtra(":settings:fragment_args_key", component.flattenToString())
                    val bundle = android.os.Bundle().apply {
                        putString(":settings:fragment_args_key", component.flattenToString())
                    }
                    putExtra(":settings:show_fragment_args", bundle)
                }
                context.startActivity(intent)
            } catch (_: Exception) {
                context.startActivity(
                    Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                )
            }
        }

        /** Required on Android 13+ for sideloaded apps before Accessibility will stick. */
        fun openAppDetails(context: Context) {
            try {
                context.startActivity(
                    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                        data = Uri.parse("package:${context.packageName}")
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                )
            } catch (_: Exception) {
            }
        }

        fun openSettings(context: Context) = openAccessibilitySettings(context)
    }
}
