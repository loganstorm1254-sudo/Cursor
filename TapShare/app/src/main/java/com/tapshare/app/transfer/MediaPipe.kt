package com.tapshare.app.transfer

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothServerSocket
import android.bluetooth.BluetoothSocket
import android.content.Context
import android.net.Uri
import android.util.Log
import com.tapshare.app.util.ShareSession
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.DataInputStream
import java.io.DataOutputStream
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Bluetooth RFCOMM pipe for shipping the on-screen photo between two TapShare phones.
 */
class MediaPipe(private val context: Context) {

    companion object {
        val SERVICE_UUID: UUID = UUID.fromString("a1b2c3d4-5555-6666-7777-abcdef123456")
        private const val MAGIC = 0x54534852 // "TSHR"
        private const val MAX_BYTES = 40 * 1024 * 1024
        private const val TAG = "TapSharePipe"
    }

    private val running = AtomicBoolean(false)
    private var serverSocket: BluetoothServerSocket? = null

    @SuppressLint("MissingPermission")
    fun adapter(): BluetoothAdapter? {
        return try {
            context.getSystemService(BluetoothManager::class.java)?.adapter
        } catch (_: Exception) {
            null
        }
    }

    @SuppressLint("MissingPermission")
    fun startListening(onReceived: (Uri, String) -> Unit) {
        if (!running.compareAndSet(false, true)) return
        Thread({
            val adapter = adapter() ?: run {
                running.set(false)
                return@Thread
            }
            while (running.get()) {
                try {
                    // Insecure is far more reliable across unpaired Samsung phones.
                    serverSocket = try {
                        adapter.listenUsingInsecureRfcommWithServiceRecord("TapShare", SERVICE_UUID)
                    } catch (_: Exception) {
                        adapter.listenUsingRfcommWithServiceRecord("TapShare", SERVICE_UUID)
                    }
                    while (running.get()) {
                        val socket = try {
                            serverSocket?.accept()
                        } catch (_: Exception) {
                            null
                        } ?: break
                        try {
                            val result = readIncoming(socket)
                            if (result != null) {
                                try {
                                    onReceived(result.first, result.second)
                                } catch (t: Throwable) {
                                    Log.e(TAG, "receive callback failed", t)
                                }
                            }
                        } catch (t: Throwable) {
                            Log.e(TAG, "read failed", t)
                        } finally {
                            try {
                                socket.close()
                            } catch (_: Exception) {
                            }
                        }
                    }
                } catch (t: Throwable) {
                    Log.e(TAG, "listen loop error", t)
                    try {
                        Thread.sleep(1500)
                    } catch (_: Exception) {
                    }
                } finally {
                    try {
                        serverSocket?.close()
                    } catch (_: Exception) {
                    }
                    serverSocket = null
                }
            }
        }, "TapShare-Listen").also { it.isDaemon = true }.start()
    }

    fun stopListening() {
        running.set(false)
        try {
            serverSocket?.close()
        } catch (_: Exception) {
        }
        serverSocket = null
    }

    /** Find nearest bumped / strongest TapShare peer over BLE, then send via Bluetooth. */
    suspend fun sendAfterTap(media: ShareSession.ActiveMedia, beacon: BleBeacon): Boolean =
        withContext(Dispatchers.IO) {
            val adapter = adapter() ?: return@withContext false
            if (!adapter.isEnabled) return@withContext false
            beacon.signalBump()
            val peer = beacon.findTapPeer(4500) ?: return@withContext false
            // RFCOMM often fails with BLE-random addresses; GATT is the reliable path.
            val gattOk = try {
                GattTransfer(context).send(peer.device, media)
            } catch (t: Throwable) {
                Log.w(TAG, "gatt send failed", t)
                false
            }
            if (gattOk) return@withContext true
            connectAndSend(adapter, peer.device, media)
        }

    suspend fun sendToDevice(device: BluetoothDevice, media: ShareSession.ActiveMedia): Boolean =
        withContext(Dispatchers.IO) {
            val adapter = adapter() ?: return@withContext false
            connectAndSend(adapter, device, media)
        }

    @SuppressLint("MissingPermission")
    private fun connectAndSend(
        adapter: BluetoothAdapter,
        device: BluetoothDevice,
        media: ShareSession.ActiveMedia
    ): Boolean {
        // Try insecure first (no pairing dialog), then secure, then channel-1 fallback.
        val attempts = listOf(
            {
                device.createInsecureRfcommSocketToServiceRecord(SERVICE_UUID)
            },
            {
                device.createRfcommSocketToServiceRecord(SERVICE_UUID)
            },
            {
                val m = device.javaClass.getMethod(
                    "createInsecureRfcommSocket",
                    Int::class.javaPrimitiveType
                )
                m.invoke(device, 1) as BluetoothSocket
            }
        )
        for (factory in attempts) {
            var socket: BluetoothSocket? = null
            try {
                adapter.cancelDiscovery()
                socket = factory()
                socket.connect()
                writeOutgoing(socket, media)
                return true
            } catch (t: Throwable) {
                Log.w(TAG, "connect attempt failed: ${t.message}")
                try {
                    socket?.close()
                } catch (_: Exception) {
                }
            }
        }
        return false
    }

    private fun writeOutgoing(socket: BluetoothSocket, media: ShareSession.ActiveMedia) {
        val bytes = context.contentResolver.openInputStream(media.uri)?.use { it.readBytes() }
            ?: error("Cannot read media")
        require(bytes.size <= MAX_BYTES) { "File too large" }
        val out = DataOutputStream(socket.outputStream.buffered())
        out.writeInt(MAGIC)
        out.writeUTF(media.mimeType.take(80))
        out.writeUTF(media.displayName.take(180))
        out.writeInt(bytes.size)
        out.write(bytes)
        out.flush()
    }

    private fun readIncoming(socket: BluetoothSocket): Pair<Uri, String>? {
        val input = DataInputStream(socket.inputStream.buffered())
        val magic = input.readInt()
        if (magic != MAGIC) return null
        val mime = input.readUTF()
        val name = input.readUTF().ifBlank { "tapshare_${System.currentTimeMillis()}" }
        val size = input.readInt()
        if (size <= 0 || size > MAX_BYTES) return null
        val bytes = ByteArray(size)
        input.readFully(bytes)
        val uri = MediaSaver.persist(context, bytes, mime, name) ?: return null
        return uri to mime
    }
}
