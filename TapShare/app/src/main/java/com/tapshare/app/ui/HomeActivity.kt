package com.tapshare.app.ui

import android.Manifest
import android.animation.ObjectAnimator
import android.animation.PropertyValuesHolder
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.view.animation.AccelerateDecelerateInterpolator
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.tapshare.app.R
import com.tapshare.app.databinding.ActivityHomeBinding
import com.tapshare.app.service.GalleryWatchService
import com.tapshare.app.service.TapShareService

class HomeActivity : AppCompatActivity() {

    private lateinit var binding: ActivityHomeBinding

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        if (results.values.any { !it }) {
            Toast.makeText(this, R.string.permissions_needed, Toast.LENGTH_LONG).show()
        }
        TapShareService.ensureRunning(this)
        refreshStatus()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityHomeBinding.inflate(layoutInflater)
        setContentView(binding.root)

        startPulse(binding.pulseOuter, 1.55f, 2200L)
        startPulse(binding.pulseInner, 1.25f, 1600L)

        binding.accessButton.setOnClickListener {
            Toast.makeText(this, R.string.enable_accessibility_short, Toast.LENGTH_LONG).show()
            GalleryWatchService.openSettings(this)
        }
        binding.galleryButton.setOnClickListener {
            startActivity(Intent(this, GalleryActivity::class.java))
        }
        binding.batteryButton.setOnClickListener { requestBatteryExemption() }

        askPermissions()
        TapShareService.ensureRunning(this)
    }

    override fun onResume() {
        super.onResume()
        TapShareService.ensureRunning(this)
        refreshStatus()
    }

    private fun refreshStatus() {
        val accessOn = GalleryWatchService.isEnabled()
        binding.statusText.setText(
            if (accessOn) R.string.status_active else R.string.status_need_access
        )
        binding.accessButton.setText(
            if (accessOn) R.string.access_enabled else R.string.enable_gallery_access
        )
        val pm = getSystemService(PowerManager::class.java)
        val ignoring = pm.isIgnoringBatteryOptimizations(packageName)
        binding.batteryButton.setText(
            if (ignoring) R.string.battery_exempt_done else R.string.battery_exempt
        )
    }

    private fun askPermissions() {
        val needed = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            listOf(
                Manifest.permission.READ_MEDIA_IMAGES,
                Manifest.permission.READ_MEDIA_VIDEO,
                Manifest.permission.POST_NOTIFICATIONS
            ).forEach { if (!granted(it)) needed += it }
        } else {
            if (!granted(Manifest.permission.READ_EXTERNAL_STORAGE)) {
                needed += Manifest.permission.READ_EXTERNAL_STORAGE
            }
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            listOf(
                Manifest.permission.BLUETOOTH_CONNECT,
                Manifest.permission.BLUETOOTH_SCAN,
                Manifest.permission.BLUETOOTH_ADVERTISE
            ).forEach { if (!granted(it)) needed += it }
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (!granted(Manifest.permission.NEARBY_WIFI_DEVICES)) {
                needed += Manifest.permission.NEARBY_WIFI_DEVICES
            }
        }
        if (!granted(Manifest.permission.ACCESS_FINE_LOCATION)) {
            needed += Manifest.permission.ACCESS_FINE_LOCATION
        }
        if (needed.isNotEmpty()) permissionLauncher.launch(needed.toTypedArray())
    }

    private fun granted(permission: String): Boolean {
        return ContextCompat.checkSelfPermission(this, permission) ==
            PackageManager.PERMISSION_GRANTED
    }

    @SuppressLint("BatteryLife")
    private fun requestBatteryExemption() {
        val pm = getSystemService(PowerManager::class.java)
        if (pm.isIgnoringBatteryOptimizations(packageName)) {
            Toast.makeText(this, R.string.battery_exempt_done, Toast.LENGTH_SHORT).show()
            return
        }
        try {
            startActivity(
                Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = Uri.parse("package:$packageName")
                }
            )
        } catch (_: Exception) {
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        }
    }

    private fun startPulse(target: android.view.View, scale: Float, duration: Long) {
        ObjectAnimator.ofPropertyValuesHolder(
            target,
            PropertyValuesHolder.ofFloat("scaleX", 1f, scale),
            PropertyValuesHolder.ofFloat("scaleY", 1f, scale),
            PropertyValuesHolder.ofFloat("alpha", 0.75f, 0f)
        ).apply {
            this.duration = duration
            repeatCount = ObjectAnimator.INFINITE
            interpolator = AccelerateDecelerateInterpolator()
            start()
        }
    }
}
