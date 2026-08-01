package com.wifinotify.sender.net

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothSocket
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import com.wifinotify.sender.Protocol
import java.io.PrintWriter
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

data class LinkedReceiver(
    val name: String,
    val address: String
)

object BtNotifyClient {

    private const val PREFS = "bt_sender_prefs"
    private const val KEY_ADDRESS = "receiver_address"
    private const val KEY_NAME = "receiver_name"

    fun savedReceiver(context: Context): LinkedReceiver? {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val address = prefs.getString(KEY_ADDRESS, null)?.ifBlank { null } ?: return null
        val name = prefs.getString(KEY_NAME, null)?.ifBlank { null } ?: "Receiver"
        return LinkedReceiver(name = name, address = address)
    }

    fun saveReceiver(context: Context, receiver: LinkedReceiver) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_ADDRESS, receiver.address)
            .putString(KEY_NAME, receiver.name)
            .apply()
    }

    fun clearReceiver(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().apply()
    }

    @SuppressLint("MissingPermission")
    fun linkReceiver(
        context: Context,
        onStatus: (String) -> Unit,
        onLinked: (LinkedReceiver) -> Unit,
        onError: (String) -> Unit
    ) {
        val app = context.applicationContext
        thread(name = "bt-link", isDaemon = true) {
            val adapter = adapter(app)
            if (adapter == null) {
                onError("This phone has no Bluetooth")
                return@thread
            }
            if (!adapter.isEnabled) {
                onError("Turn on Bluetooth and try again")
                return@thread
            }

            // 1) Try already-bonded devices first (fast, no scan UI).
            for (device in adapter.bondedDevices.orEmpty()) {
                onStatus("Trying paired: ${deviceName(device)}…")
                if (tryConnect(device, timeoutMs = 4000) { socket ->
                        // Just proving the service exists; close without sending.
                        socket.close()
                    }
                ) {
                    val linked = LinkedReceiver(deviceName(device), device.address)
                    saveReceiver(app, linked)
                    onLinked(linked)
                    return@thread
                }
            }

            // 2) Discovery scan for a phone running Notify Receiver.
            onStatus("Scanning for Notify Receiver…")
            val found = discoverDevices(app, adapter, timeoutMs = 12_000, onStatus)
            if (found.isEmpty()) {
                onError(
                    "No receiver found. On the other phone: open Notify Receiver, " +
                        "turn Bluetooth ON, tap Start, then try Link again (keep phones close)."
                )
                return@thread
            }

            for (device in found) {
                onStatus("Connecting to ${deviceName(device)}…")
                if (tryConnect(device, timeoutMs = 6000) { it.close() }) {
                    val linked = LinkedReceiver(deviceName(device), device.address)
                    saveReceiver(app, linked)
                    onLinked(linked)
                    return@thread
                }
            }
            onError(
                "Found Bluetooth phones nearby, but none are running Notify Receiver. " +
                    "Tap Start on the receiver phone, then Link again."
            )
        }
    }

    @SuppressLint("MissingPermission")
    fun send(
        context: Context,
        title: String,
        message: String,
        from: String,
        onSuccess: () -> Unit,
        onError: (String) -> Unit
    ) {
        val app = context.applicationContext
        thread(name = "bt-send", isDaemon = true) {
            val adapter = adapter(app)
            if (adapter == null) {
                onError("This phone has no Bluetooth")
                return@thread
            }
            if (!adapter.isEnabled) {
                onError("Turn on Bluetooth and try again")
                return@thread
            }

            var receiver = savedReceiver(app)
            val device: BluetoothDevice? = when {
                receiver != null -> try {
                    adapter.getRemoteDevice(receiver.address)
                } catch (_: Exception) {
                    null
                }
                else -> null
            }

            if (device == null) {
                onError("No receiver linked yet. Tap “Link receiver” once.")
                return@thread
            }

            val ok = tryConnect(device, timeoutMs = 8000) { socket ->
                val json = buildJson(title, message, from)
                PrintWriter(socket.outputStream, true, Charsets.UTF_8).use { out ->
                    out.println(json)
                    out.flush()
                }
            }

            if (ok) {
                // Refresh saved name if we can read it.
                try {
                    val name = deviceName(device)
                    saveReceiver(app, LinkedReceiver(name, device.address))
                } catch (_: Exception) {
                }
                onSuccess()
            } else {
                onError(
                    "Could not reach the receiver over Bluetooth.\n\n" +
                        "• Keep phones close (about room distance)\n" +
                        "• Bluetooth ON on both\n" +
                        "• Notify Receiver is open and Start is on\n" +
                        "• Tap “Link receiver” again if you switched phones"
                )
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun tryConnect(
        device: BluetoothDevice,
        timeoutMs: Long,
        block: (BluetoothSocket) -> Unit
    ): Boolean {
        var socket: BluetoothSocket? = null
        return try {
            socket = device.createInsecureRfcommSocketToServiceRecord(Protocol.SERVICE_UUID)
            // connect() can hang; do it with a watchdog.
            val done = CountDownLatch(1)
            val success = AtomicBoolean(false)
            val error = AtomicBoolean(false)
            thread(name = "bt-connect", isDaemon = true) {
                try {
                    socket.connect()
                    success.set(true)
                } catch (_: Exception) {
                    error.set(true)
                } finally {
                    done.countDown()
                }
            }
            done.await(timeoutMs, TimeUnit.MILLISECONDS)
            if (!success.get()) {
                try {
                    socket.close()
                } catch (_: Exception) {
                }
                return false
            }
            block(socket)
            true
        } catch (_: Exception) {
            false
        } finally {
            try {
                socket?.close()
            } catch (_: Exception) {
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun discoverDevices(
        context: Context,
        adapter: BluetoothAdapter,
        timeoutMs: Long,
        onStatus: (String) -> Unit
    ): List<BluetoothDevice> {
        val found = linkedMapOf<String, BluetoothDevice>()
        // Include bonded so we don't miss them if discovery is flaky.
        adapter.bondedDevices.orEmpty().forEach { found[it.address] = it }

        val latch = CountDownLatch(1)
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context?, intent: Intent?) {
                when (intent?.action) {
                    BluetoothDevice.ACTION_FOUND -> {
                        val device = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                            intent.getParcelableExtra(
                                BluetoothDevice.EXTRA_DEVICE,
                                BluetoothDevice::class.java
                            )
                        } else {
                            @Suppress("DEPRECATION")
                            intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE)
                        } ?: return
                        found[device.address] = device
                        onStatus("Saw ${deviceName(device)}…")
                    }
                    BluetoothAdapter.ACTION_DISCOVERY_FINISHED -> latch.countDown()
                }
            }
        }
        val filter = IntentFilter().apply {
            addAction(BluetoothDevice.ACTION_FOUND)
            addAction(BluetoothAdapter.ACTION_DISCOVERY_FINISHED)
        }
        context.registerReceiver(receiver, filter)
        try {
            if (adapter.isDiscovering) adapter.cancelDiscovery()
            val started = adapter.startDiscovery()
            if (!started) {
                onStatus("Bluetooth scan did not start — check permission")
            }
            latch.await(timeoutMs, TimeUnit.MILLISECONDS)
            if (adapter.isDiscovering) adapter.cancelDiscovery()
        } catch (_: Exception) {
        } finally {
            try {
                context.unregisterReceiver(receiver)
            } catch (_: Exception) {
            }
        }
        return found.values.toList()
    }

    @SuppressLint("MissingPermission")
    private fun deviceName(device: BluetoothDevice): String {
        return try {
            device.name?.takeIf { it.isNotBlank() } ?: device.address
        } catch (_: SecurityException) {
            device.address
        }
    }

    private fun adapter(context: Context): BluetoothAdapter? {
        val manager = context.getSystemService(BluetoothManager::class.java)
        return manager?.adapter
    }

    private fun buildJson(title: String, message: String, from: String): String {
        fun esc(s: String): String = buildString {
            for (c in s) {
                when (c) {
                    '\\' -> append("\\\\")
                    '"' -> append("\\\"")
                    '\n' -> append("\\n")
                    '\r' -> append("\\r")
                    '\t' -> append("\\t")
                    else -> append(c)
                }
            }
        }
        return """{"title":"${esc(title)}","message":"${esc(message)}","from":"${esc(from)}"}"""
    }
}
