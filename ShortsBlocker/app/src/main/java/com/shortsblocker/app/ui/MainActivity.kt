package com.shortsblocker.app.ui

import android.Manifest
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.text.TextUtils
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.android.material.button.MaterialButton
import com.shortsblocker.app.Prefs
import com.shortsblocker.app.R
import com.shortsblocker.app.service.ShortsAccessibilityService
import com.shortsblocker.app.service.ShortsGuardService

class MainActivity : AppCompatActivity() {

    private lateinit var statusLine: TextView
    private lateinit var helpLine: TextView
    private lateinit var btnEnable: MaterialButton

    private val notifPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* no-op */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        statusLine = findViewById(R.id.statusLine)
        helpLine = findViewById(R.id.helpLine)
        btnEnable = findViewById(R.id.btnEnable)

        btnEnable.setOnClickListener { oneStepEnable() }
        maybeAskNotificationPermission()
    }

    override fun onResume() {
        super.onResume()
        refreshUi()
        if (isAccessibilityEnabled()) {
            Prefs.setEnabled(this, true)
            startGuard()
            maybeRequestBatteryQuietly()
        }
    }

    /** One tap: arm service + jump straight to this app's accessibility toggle. */
    private fun oneStepEnable() {
        Prefs.setEnabled(this, true)
        startGuard()
        openOurAccessibilityPage()
    }

    private fun openOurAccessibilityPage() {
        val component = ComponentName(this, ShortsAccessibilityService::class.java)

        // 1) Best: jump straight to Shorts Blocker's own accessibility screen
        try {
            val details = Intent("android.settings.ACCESSIBILITY_DETAILS_SETTINGS")
            details.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            details.data = Uri.parse("package:$packageName")
            details.putExtra(Intent.EXTRA_COMPONENT_NAME, component)
            startActivity(details)
            Toast.makeText(this, "Turn Shorts Blocker ON", Toast.LENGTH_LONG).show()
            return
        } catch (_: Exception) {
            // fall through
        }

        // 2) Open Accessibility list and highlight our service so it "appears"
        try {
            val key = component.flattenToString()
            val highlight = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
            highlight.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            highlight.putExtra(EXTRA_FRAGMENT_ARG_KEY, key)
            val bundle = Bundle()
            bundle.putString(EXTRA_FRAGMENT_ARG_KEY, key)
            highlight.putExtra(EXTRA_SHOW_FRAGMENT_ARGUMENTS, bundle)
            startActivity(highlight)
            Toast.makeText(this, "Find Shorts Blocker → turn ON", Toast.LENGTH_LONG).show()
            return
        } catch (_: Exception) {
            // fall through
        }

        // 3) Last resort
        startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        Toast.makeText(this, "Installed apps → Shorts Blocker → ON", Toast.LENGTH_LONG).show()
    }

    private fun refreshUi() {
        val on = isAccessibilityEnabled()
        if (on) {
            statusLine.text = "Status: ON — Shorts are being blocked"
            statusLine.setTextColor(ContextCompat.getColor(this, R.color.ok))
            btnEnable.text = "Open accessibility settings"
            helpLine.text = "You're set. It stays on after reboot. Tap the button only if you need to change the switch."
        } else {
            statusLine.text = "Status: OFF — tap the button once"
            statusLine.setTextColor(ContextCompat.getColor(this, R.color.danger))
            btnEnable.text = "Enable Shorts Blocker"
            helpLine.text =
                "Tap once. It opens the Shorts Blocker accessibility page — flip the switch On.\n\n" +
                "If it says “Controlled by restricted setting”: on that same phone screen go back → App info → ⋮ → Allow restricted settings, then tap this button again."
        }
    }

    private fun startGuard() {
        val intent = Intent(this, ShortsGuardService::class.java)
        try {
            startForegroundService(intent)
        } catch (_: Exception) {
            startService(intent)
        }
    }

    private fun maybeRequestBatteryQuietly() {
        if (isIgnoringBatteryOptimizations()) return
        try {
            startActivity(
                Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = Uri.parse("package:$packageName")
                }
            )
        } catch (_: Exception) {
            // ignore — not required for first enable
        }
    }

    private fun isIgnoringBatteryOptimizations(): Boolean {
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        return pm.isIgnoringBatteryOptimizations(packageName)
    }

    private fun isAccessibilityEnabled(): Boolean {
        val expected = ComponentName(this, ShortsAccessibilityService::class.java)
        val enabled = Settings.Secure.getString(
            contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        ) ?: return false
        val splitter = TextUtils.SimpleStringSplitter(':')
        splitter.setString(enabled)
        while (splitter.hasNext()) {
            val component = ComponentName.unflattenFromString(splitter.next())
            if (component == expected) return true
        }
        return false
    }

    private fun maybeAskNotificationPermission() {
        if (Build.VERSION.SDK_INT < 33) return
        val granted = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) {
            notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    companion object {
        // Undocumented Settings extras — used by many apps to highlight a row.
        private const val EXTRA_FRAGMENT_ARG_KEY = ":settings:fragment_args_key"
        private const val EXTRA_SHOW_FRAGMENT_ARGUMENTS = ":settings:show_fragment_args"
    }
}
