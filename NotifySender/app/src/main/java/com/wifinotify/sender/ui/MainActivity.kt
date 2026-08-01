package com.wifinotify.sender.ui

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.wifinotify.sender.R
import com.wifinotify.sender.databinding.ActivityMainBinding
import com.wifinotify.sender.net.BtNotifyClient

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        if (results.values.any { !it }) {
            Toast.makeText(this, R.string.permission_needed, Toast.LENGTH_LONG).show()
        }
    }

    private val enableBtLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { /* returned from BT enable */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        ensurePermissions()

        val prefs = getSharedPreferences("sender_prefs", MODE_PRIVATE)
        binding.fromInput.setText(
            prefs.getString("from_name", null) ?: (Build.MODEL ?: "Sender")
        )

        refreshLinkedLabel()

        binding.linkButton.setOnClickListener { linkReceiver() }
        binding.clearLinkButton.setOnClickListener {
            BtNotifyClient.clearReceiver(this)
            refreshLinkedLabel()
            binding.statusText.text = getString(R.string.link_cleared)
        }
        binding.sendButton.setOnClickListener { send() }
    }

    private fun refreshLinkedLabel() {
        val linked = BtNotifyClient.savedReceiver(this)
        binding.linkedText.text = if (linked == null) {
            getString(R.string.not_linked)
        } else {
            getString(R.string.linked_to, linked.name, linked.address)
        }
    }

    private fun linkReceiver() {
        if (!ensureReadyForBluetooth()) return
        binding.linkButton.isEnabled = false
        binding.statusText.text = getString(R.string.linking)
        BtNotifyClient.linkReceiver(
            context = this,
            onStatus = { msg -> runOnUiThread { binding.statusText.text = msg } },
            onLinked = { linked ->
                runOnUiThread {
                    binding.linkButton.isEnabled = true
                    refreshLinkedLabel()
                    binding.statusText.text = getString(R.string.linked_ok, linked.name)
                    Toast.makeText(this, R.string.linked_toast, Toast.LENGTH_SHORT).show()
                }
            },
            onError = { err ->
                runOnUiThread {
                    binding.linkButton.isEnabled = true
                    binding.statusText.text = err
                }
            }
        )
    }

    private fun send() {
        if (BtNotifyClient.savedReceiver(this) == null) {
            Toast.makeText(this, R.string.link_first, Toast.LENGTH_LONG).show()
            return
        }
        if (!ensureReadyForBluetooth()) return

        val title = binding.titleInput.text?.toString()?.trim().orEmpty()
        val message = binding.messageInput.text?.toString()?.trim().orEmpty()
        val from = binding.fromInput.text?.toString()?.trim().orEmpty()
            .ifBlank { Build.MODEL ?: "Sender" }

        if (title.isEmpty() || message.isEmpty()) {
            Toast.makeText(this, R.string.fill_title_message, Toast.LENGTH_SHORT).show()
            return
        }

        getSharedPreferences("sender_prefs", MODE_PRIVATE)
            .edit()
            .putString("from_name", from)
            .apply()

        binding.sendButton.isEnabled = false
        binding.statusText.text = getString(R.string.sending)

        BtNotifyClient.send(
            context = this,
            title = title,
            message = message,
            from = from,
            onSuccess = {
                runOnUiThread {
                    binding.sendButton.isEnabled = true
                    binding.statusText.text = getString(R.string.sent_ok)
                    Toast.makeText(this, R.string.sent_toast, Toast.LENGTH_SHORT).show()
                }
            },
            onError = { err ->
                runOnUiThread {
                    binding.sendButton.isEnabled = true
                    binding.statusText.text = err
                }
            }
        )
    }

    private fun ensureReadyForBluetooth(): Boolean {
        if (!hasBluetoothPermissions()) {
            ensurePermissions()
            Toast.makeText(this, R.string.permission_needed, Toast.LENGTH_LONG).show()
            return false
        }
        val adapter = getSystemService(android.bluetooth.BluetoothManager::class.java)?.adapter
        if (adapter == null) {
            Toast.makeText(this, R.string.no_bluetooth, Toast.LENGTH_LONG).show()
            return false
        }
        if (!adapter.isEnabled) {
            enableBtLauncher.launch(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
            Toast.makeText(this, R.string.turn_on_bluetooth, Toast.LENGTH_LONG).show()
            return false
        }
        return true
    }

    private fun ensurePermissions() {
        val needed = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            listOf(
                Manifest.permission.BLUETOOTH_CONNECT,
                Manifest.permission.BLUETOOTH_SCAN
            ).forEach {
                if (ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED) {
                    needed += it
                }
            }
        } else {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED
            ) {
                needed += Manifest.permission.ACCESS_FINE_LOCATION
            }
        }
        if (needed.isNotEmpty()) permissionLauncher.launch(needed.toTypedArray())
    }

    private fun hasBluetoothPermissions(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) ==
                PackageManager.PERMISSION_GRANTED &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_SCAN) ==
                PackageManager.PERMISSION_GRANTED
        } else {
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) ==
                PackageManager.PERMISSION_GRANTED
        }
    }
}
