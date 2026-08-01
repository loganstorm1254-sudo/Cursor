package com.wifinotify.receiver.ui

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
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
import com.wifinotify.receiver.R
import com.wifinotify.receiver.databinding.ActivityMainBinding
import com.wifinotify.receiver.service.NotifyListenService

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val prefs by lazy {
        getSharedPreferences(NotifyListenService.PREFS, MODE_PRIVATE)
    }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        if (results.values.any { !it }) {
            Toast.makeText(this, R.string.permission_needed, Toast.LENGTH_LONG).show()
        }
    }

    private val enableBtLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) {
        // User returned from Bluetooth enable prompt.
    }

    private val discoverableLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) {
        // Discoverable prompt finished.
    }

    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                NotifyListenService.ACTION_STATUS -> {
                    binding.statusText.text = intent.getStringExtra(NotifyListenService.EXTRA_STATUS)
                        ?: "—"
                }
                NotifyListenService.ACTION_MESSAGE -> {
                    val title = intent.getStringExtra(NotifyListenService.EXTRA_TITLE).orEmpty()
                    val message = intent.getStringExtra(NotifyListenService.EXTRA_MESSAGE).orEmpty()
                    val from = intent.getStringExtra(NotifyListenService.EXTRA_FROM).orEmpty()
                    val line = "From $from — $title: $message"
                    val existing = binding.logText.text?.toString().orEmpty()
                    binding.logText.text =
                        if (existing.isBlank() || existing == getString(R.string.log_empty)) {
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
                Toast.makeText(this, R.string.enter_name, Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            prefs.edit().putString(NotifyListenService.KEY_DEVICE_NAME, name).apply()
            maybeRenameBluetooth(name)
            Toast.makeText(this, R.string.name_saved, Toast.LENGTH_SHORT).show()
        }

        binding.autoStartSwitch.setOnCheckedChangeListener { _, checked ->
            prefs.edit().putBoolean(NotifyListenService.KEY_AUTO_START, checked).apply()
        }

        binding.startButton.setOnClickListener { startListening() }
        binding.stopButton.setOnClickListener {
            NotifyListenService.stop(this)
            binding.statusText.text = getString(R.string.status_idle)
        }
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

    private fun startListening() {
        if (!hasBluetoothPermissions()) {
            ensurePermissions()
            Toast.makeText(this, R.string.permission_needed, Toast.LENGTH_LONG).show()
            return
        }
        val adapter = NotifyListenService.bluetoothAdapter(this)
        if (adapter == null) {
            Toast.makeText(this, R.string.no_bluetooth, Toast.LENGTH_LONG).show()
            return
        }
        if (!adapter.isEnabled) {
            enableBtLauncher.launch(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
            Toast.makeText(this, R.string.turn_on_bluetooth, Toast.LENGTH_LONG).show()
            return
        }

        val name = binding.nameInput.text?.toString()?.trim().orEmpty()
            .ifBlank { Build.MODEL ?: "Android" }
        prefs.edit().putString(NotifyListenService.KEY_DEVICE_NAME, name).apply()
        maybeRenameBluetooth(name)

        // Make this phone visible so the sender can find it the first time.
        requestDiscoverable()

        NotifyListenService.start(this)
        binding.statusText.text = getString(R.string.status_starting)
    }

    private fun requestDiscoverable() {
        try {
            val intent = Intent(BluetoothAdapter.ACTION_REQUEST_DISCOVERABLE).apply {
                putExtra(BluetoothAdapter.EXTRA_DISCOVERABLE_DURATION, 300)
            }
            discoverableLauncher.launch(intent)
        } catch (_: Exception) {
        }
    }

    @SuppressLint("MissingPermission")
    private fun maybeRenameBluetooth(name: String) {
        if (!hasBluetoothPermissions()) return
        try {
            val adapter = NotifyListenService.bluetoothAdapter(this) ?: return
            @Suppress("DEPRECATION")
            adapter.name = name
        } catch (_: Exception) {
        }
    }

    private fun ensurePermissions() {
        val needed = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            listOf(
                Manifest.permission.BLUETOOTH_CONNECT,
                Manifest.permission.BLUETOOTH_SCAN,
                Manifest.permission.BLUETOOTH_ADVERTISE
            ).forEach {
                if (ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED) {
                    needed += it
                }
            }
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                needed += Manifest.permission.POST_NOTIFICATIONS
            }
        }
        if (needed.isNotEmpty()) permissionLauncher.launch(needed.toTypedArray())
    }

    private fun hasBluetoothPermissions(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        return ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) ==
            PackageManager.PERMISSION_GRANTED &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_SCAN) ==
            PackageManager.PERMISSION_GRANTED
    }
}
