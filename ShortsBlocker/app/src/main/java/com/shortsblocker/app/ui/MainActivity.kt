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
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.android.material.button.MaterialButton
import com.shortsblocker.app.Prefs
import com.shortsblocker.app.R
import com.shortsblocker.app.service.ShortsAccessibilityService
import com.shortsblocker.app.service.ShortsGuardService

class MainActivity : AppCompatActivity() {

    private lateinit var statusAccessibility: TextView
    private lateinit var statusService: TextView
    private lateinit var statusBattery: TextView
    private lateinit var statusBlocks: TextView
    private lateinit var btnToggle: MaterialButton

    private val notifPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { refreshUi() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        statusAccessibility = findViewById(R.id.statusAccessibility)
        statusService = findViewById(R.id.statusService)
        statusBattery = findViewById(R.id.statusBattery)
        statusBlocks = findViewById(R.id.statusBlocks)
        btnToggle = findViewById(R.id.btnToggle)

        findViewById<MaterialButton>(R.id.btnAccessibility).setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        findViewById<MaterialButton>(R.id.btnBattery).setOnClickListener {
            requestBatteryExemption()
        }
        btnToggle.setOnClickListener { toggleBlocking() }

        maybeAskNotificationPermission()
    }

    override fun onResume() {
        super.onResume()
        refreshUi()
        if (Prefs.isEnabled(this) && isAccessibilityEnabled()) {
            startGuard()
        }
    }

    private fun toggleBlocking() {
        val next = !Prefs.isEnabled(this)
        Prefs.setEnabled(this, next)
        if (next) {
            startGuard()
        } else {
            stopService(Intent(this, ShortsGuardService::class.java))
        }
        refreshUi()
    }

    private fun startGuard() {
        val intent = Intent(this, ShortsGuardService::class.java)
        try {
            startForegroundService(intent)
        } catch (_: Exception) {
            startService(intent)
        }
    }

    private fun refreshUi() {
        val a11y = isAccessibilityEnabled()
        statusAccessibility.text = if (a11y) {
            "Accessibility: ON ✓"
        } else {
            "Accessibility: OFF — tap step 1 (required)"
        }
        statusAccessibility.setTextColor(
            ContextCompat.getColor(this, if (a11y) R.color.ok else R.color.danger)
        )

        val enabled = Prefs.isEnabled(this)
        statusService.text = if (enabled) {
            "Background: armed — will auto-start on boot"
        } else {
            "Background: paused"
        }
        statusService.setTextColor(
            ContextCompat.getColor(this, if (enabled) R.color.ok else R.color.accent)
        )

        val batteryOk = isIgnoringBatteryOptimizations()
        statusBattery.text = if (batteryOk) {
            "Battery: unrestricted ✓"
        } else {
            "Battery: restricted — tap step 2 so it stays online"
        }
        statusBattery.setTextColor(
            ContextCompat.getColor(this, if (batteryOk) R.color.ok else R.color.accent)
        )

        statusBlocks.text = "Blocks so far: ${Prefs.blockCount(this)}"

        btnToggle.text = if (enabled) "Pause blocking" else "3. Start blocking"
        btnToggle.setBackgroundColor(
            ContextCompat.getColor(this, if (enabled) R.color.accent else R.color.brand)
        )
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

    private fun isIgnoringBatteryOptimizations(): Boolean {
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        return pm.isIgnoringBatteryOptimizations(packageName)
    }

    private fun requestBatteryExemption() {
        if (isIgnoringBatteryOptimizations()) return
        try {
            val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                data = Uri.parse("package:$packageName")
            }
            startActivity(intent)
        } catch (_: Exception) {
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        }
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
}
