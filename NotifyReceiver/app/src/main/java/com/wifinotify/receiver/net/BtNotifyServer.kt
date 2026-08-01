package com.wifinotify.receiver.net

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothServerSocket
import android.bluetooth.BluetoothSocket
import android.content.Context
import com.wifinotify.receiver.Protocol
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/**
 * Bluetooth RFCOMM listener. Works with no Wi‑Fi, data, hotspot, or IPs —
 * phones just need Bluetooth on and to be near each other.
 */
class BtNotifyServer(
    private val context: Context,
    private val onNotify: (IncomingNotify, String) -> Unit,
    private val onStatus: (String) -> Unit
) {
    private val running = AtomicBoolean(false)
    private var serverSocket: BluetoothServerSocket? = null

    @SuppressLint("MissingPermission")
    fun start() {
        if (!running.compareAndSet(false, true)) return
        val adapter = bluetoothAdapter()
        if (adapter == null) {
            onStatus("This phone has no Bluetooth")
            running.set(false)
            return
        }
        if (!adapter.isEnabled) {
            onStatus("Turn on Bluetooth, then tap Start again")
            running.set(false)
            return
        }
        thread(name = "bt-notify-accept", isDaemon = true) {
            try {
                // Insecure = no PIN dance; SDP record lets the sender find this service.
                val server = adapter.listenUsingInsecureRfcommWithServiceRecord(
                    Protocol.SERVICE_NAME,
                    Protocol.SERVICE_UUID
                ).also { serverSocket = it }
                onStatus("Ready — waiting for sender over Bluetooth")
                while (running.get()) {
                    try {
                        val client = server.accept()
                        thread(name = "bt-notify-client", isDaemon = true) {
                            handleClient(client)
                        }
                    } catch (e: Exception) {
                        if (!running.get()) break
                        onStatus("Accept error: ${e.message}")
                    }
                }
            } catch (e: Exception) {
                onStatus("Could not start Bluetooth listener: ${e.message}")
                running.set(false)
            }
        }
    }

    fun stop() {
        running.set(false)
        try {
            serverSocket?.close()
        } catch (_: Exception) {
        }
        serverSocket = null
        onStatus("Stopped")
    }

    private fun handleClient(socket: BluetoothSocket) {
        socket.use { s ->
            val remote = try {
                s.remoteDevice?.name?.takeIf { it.isNotBlank() }
                    ?: s.remoteDevice?.address
                    ?: "sender"
            } catch (_: SecurityException) {
                "sender"
            }
            val reader = BufferedReader(InputStreamReader(s.inputStream, Charsets.UTF_8))
            val line = reader.readLine() ?: return
            val notify = IncomingNotify.parse(line)
            if (notify != null) {
                onNotify(notify, remote)
                onStatus("Got message from $remote")
            } else {
                onStatus("Ignored invalid message from $remote")
            }
        }
    }

    private fun bluetoothAdapter(): BluetoothAdapter? {
        val manager = context.getSystemService(BluetoothManager::class.java)
        return manager?.adapter
    }
}
