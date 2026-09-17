package com.shortsblocker.app.service

import android.content.Context
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.os.Build
import android.util.DisplayMetrics
import android.util.TypedValue
import android.view.Gravity
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.accessibilityservice.AccessibilityService
import com.shortsblocker.app.Prefs

/**
 * Covers only the short-video region. Leaves TikTok's top tabs and bottom nav
 * free so the user can switch to Inbox / Profile / Friends / etc.
 */
class FeedCoverOverlay(private val service: AccessibilityService) {

    private val windowManager =
        service.getSystemService(Context.WINDOW_SERVICE) as WindowManager

    private var root: FrameLayout? = null
    private var showing = false
    private var countedThisShow = false

    fun show(message: String = "Short feed blocked") {
        if (showing) return
        val metrics = displayMetrics()
        val density = metrics.density
        val topReserve = (TOP_RESERVE_DP * density).toInt()
        val bottomReserve = (BOTTOM_RESERVE_DP * density).toInt()
        val height = (metrics.heightPixels - topReserve - bottomReserve).coerceAtLeast(1)

        val panel = FrameLayout(service).apply {
            setBackgroundColor(0xF20F1C14.toInt())
            isClickable = true
            isFocusable = false
        }

        val column = LinearLayout(service).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(28), dp(24), dp(28), dp(24))
        }

        val title = TextView(service).apply {
            text = message
            setTextColor(0xFF7CFFB2.toInt())
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 22f)
            typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
            gravity = Gravity.CENTER
        }
        val body = TextView(service).apply {
            text = "Use the tabs above or the bar below — Inbox, Friends, Profile, Search, and LIVE still work."
            setTextColor(0xFF9BB5A4.toInt())
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            gravity = Gravity.CENTER
            setPadding(0, dp(12), 0, 0)
        }
        column.addView(title)
        column.addView(body)
        panel.addView(
            column,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.CENTER
            )
        )

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            height,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP
            y = topReserve
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                layoutInDisplayCutoutMode =
                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
            }
        }

        try {
            windowManager.addView(panel, params)
            root = panel
            showing = true
            if (!countedThisShow) {
                Prefs.incrementBlocks(service)
                countedThisShow = true
            }
        } catch (_: Exception) {
            root = null
            showing = false
        }
    }

    fun hide() {
        val view = root ?: run {
            showing = false
            countedThisShow = false
            return
        }
        try {
            windowManager.removeView(view)
        } catch (_: Exception) {
            // already gone
        }
        root = null
        showing = false
        countedThisShow = false
    }

    fun isShowing(): Boolean = showing

    private fun displayMetrics(): DisplayMetrics {
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        windowManager.defaultDisplay.getRealMetrics(metrics)
        return metrics
    }

    private fun dp(value: Int): Int =
        TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP,
            value.toFloat(),
            service.resources.displayMetrics
        ).toInt()

    companion object {
        // Leave TikTok top tabs (For You / Following) and status area free.
        private const val TOP_RESERVE_DP = 108f
        // Leave TikTok bottom nav (Home / Friends / + / Inbox / Profile) free.
        private const val BOTTOM_RESERVE_DP = 84f
    }
}
