package com.tapshare.app.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Intent
import android.graphics.Bitmap
import android.os.Build
import android.util.Log
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import java.util.concurrent.Executor
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicReference

/**
 * Watches when Samsung Gallery (or Photos) is on screen, and can capture
 * what's showing so a top-tap can share it without leaving Gallery.
 */
class GalleryWatchService : AccessibilityService() {

    override fun onServiceConnected() {
        instance = this
        serviceInfo = serviceInfo?.apply {
            eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED or
                AccessibilityEvent.TYPE_WINDOWS_CHANGED
            feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
            flags = flags or
                AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or
                AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            notificationTimeout = 100
        }
        Log.i(TAG, "Gallery watch connected")
        // Keep the share engine alive once accessibility is on.
        TapShareService.ensureRunning(applicationContext)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        val pkg = event.packageName?.toString() ?: return
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
            event.eventType == AccessibilityEvent.TYPE_WINDOWS_CHANGED
        ) {
            foregroundPackage.set(pkg)
        }
    }

    override fun onInterrupt() = Unit

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    /**
     * Capture the current display. Returns null if API/permission unavailable.
     */
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
            "com.tapshare.app" // our own viewer counts too
        )

        fun isEnabled(): Boolean = instance != null

        fun isGalleryOnScreen(): Boolean {
            val pkg = foregroundPackage.get()
            if (pkg.isBlank()) return false
            if (GALLERY_PACKAGES.contains(pkg)) return true
            // Some OEMs use package names containing "gallery" / "photos"
            return pkg.contains("gallery", ignoreCase = true) ||
                pkg.contains("photos", ignoreCase = true)
        }

        fun currentPackage(): String = foregroundPackage.get()

        fun openSettings(context: android.content.Context) {
            context.startActivity(
                Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        }
    }
}
