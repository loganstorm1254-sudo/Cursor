package com.wifinotify.receiver.ui

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.wifinotify.receiver.databinding.ActivityMainBinding
import com.wifinotify.receiver.net.localIpv4Addresses
import com.wifinotify.receiver.service.NotifyListenService

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val prefs by lazy {
        getSharedPreferences(NotifyListenService.PREFS, MODE_PRIVATE)
    }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        val granted = results.values.all { it }
        if (!granted) {
            Toast.makeText(this, "Notification permission is needed to show alerts", Toast.LENGTH_LONG).show()
        }
    }

    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                NotifyListenService.ACTION_STATUS -> {
                    binding.statusText.text = intent.getStringExtra(NotifyListenService.EXTRA_STATUS)
                        ?: "—"
                    refreshIp()
                }
                NotifyListenService.ACTION_MESSAGE -> {
                    val title = intent.getStringExtra(NotifyListenService.EXTRA_TITLE).orEmpty()
                    val message = intent.getStringExtra(NotifyListenService.EXTRA_MESSAGE).orEmpty()
                    val from = intent.getStringExtra(NotifyListenService.EXTRA_FROM).orEmpty()
                    val line = "From $from — $title: $message"
                    val existing = binding.logText.text?.toString().orEmpty()
                    binding.logText.text = if (existing.isBlank() || existing == getString(com.wifinotify.receiver.R.string.log_empty)) {
                        line
                    } else {
                        "$line\n$existing"
                    }
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        ensurePermissions()

        val savedName = prefs.getString(NotifyListenService.KEY_DEVICE_NAME, null)
        binding.nameInput.setText(savedName ?: (Build.MODEL ?: "Android"))
        binding.autoStartSwitch.isChecked =
            prefs.getBoolean(NotifyListenService.KEY_AUTO_START, false)

        binding.saveNameButton.setOnClickListener {
            val name = binding.nameInput.text?.toString()?.trim().orEmpty()
            if (name.isEmpty()) {
                Toast.makeText(this, "Enter a device name", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            prefs.edit().putString(NotifyListenService.KEY_DEVICE_NAME, name).apply()
            Toast.makeText(this, "Name saved", Toast.LENGTH_SHORT).show()
        }

        binding.autoStartSwitch.setOnCheckedChangeListener { _, checked ->
            prefs.edit().putBoolean(NotifyListenService.KEY_AUTO_START, checked).apply()
        }

        binding.startButton.setOnClickListener {
            prefs.edit()
                .putString(
                    NotifyListenService.KEY_DEVICE_NAME,
                    binding.nameInput.text?.toString()?.trim().orEmpty().ifBlank {
                        Build.MODEL ?: "Android"
                    }
                )
                .apply()
            NotifyListenService.start(this)
            binding.statusText.text = "Starting…"
            refreshIp()
        }

        binding.stopButton.setOnClickListener {
            NotifyListenService.stop(this)
            binding.statusText.text = "Stopped"
        }

        refreshIp()
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter().apply {
            addAction(NotifyListenService.ACTION_STATUS)
            addAction(NotifyListenService.ACTION_MESSAGE)
        }
        ContextCompat.registerReceiver(
            this,
            statusReceiver,
            filter,
            ContextCompat.RECEIVER_NOT_EXPORTED
        )
    }

    override fun onStop() {
        unregisterReceiver(statusReceiver)
        super.onStop()
    }

    private fun refreshIp() {
        val ips = localIpv4Addresses()
        binding.ipText.text = if (ips.isEmpty()) {
            "Not on Wi‑Fi (or no IPv4 address yet)"
        } else {
            "This phone: ${ips.joinToString(", ")}"
        }
    }

    private fun ensurePermissions() {
        val needed = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                needed += Manifest.permission.POST_NOTIFICATIONS
            }
        }
        if (needed.isNotEmpty()) {
            permissionLauncher.launch(needed.toTypedArray())
        }
    }
}
