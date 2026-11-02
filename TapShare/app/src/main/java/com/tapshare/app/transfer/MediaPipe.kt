package com.tapshare.app.transfer

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothServerSocket
import android.bluetooth.BluetoothSocket
import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import com.tapshare.app.util.ShareSession
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.File
import java.io.FileOutputStream
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Bluetooth RFCOMM pipe for shipping the on-screen photo between two TapShare phones.
 * One side listens forever (service); the other connects right after an NFC tap.
 */
class MediaPipe(private val context: Context) {

    companion object {
        val SERVICE_UUID: UUID = UUID.fromString("a1b2c3d4-5555-6666-7777-abcdef123456")
        private const val MAGIC = 0x54534852 // "TSHR"
        private const val MAX_BYTES = 80 * 1024 * 1024
    }

    private val running = AtomicBoolean(false)
    private var serverSocket: BluetoothServerSocket? = null

    @SuppressLint("MissingPermission")
    fun adapter(): BluetoothAdapter? {
        return context.getSystemService(BluetoothManager::class.java)?.adapter
    }

    @SuppressLint("MissingPermission")
    fun bluetoothAddress(): String {
        val adapter = adapter() ?: return "00:00:00:00:00:00"
        return try {
            @Suppress("DEPRECATION")
            adapter.address ?: "00:00:00:00:00:00"
        } catch (_: Exception) {
            "00:00:00:00:00:00"
        }
    }

    @SuppressLint("MissingPermission")
    fun startListening(onReceived: (Uri, String) -> Unit) {
        if (!running.compareAndSet(false, true)) return
        Thread({
            val adapter = adapter() ?: return@Thread
            try {
                serverSocket = adapter.listenUsingRfcommWithServiceRecord("TapShare", SERVICE_UUID)
                while (running.get()) {
                    val socket = try {
                        serverSocket?.accept()
                    } catch (_: Exception) {
                        null
                    } ?: break
                    try {
                        val result = readIncoming(socket)
                        if (result != null) {
                            onReceived(result.first, result.second)
                        }
                    } catch (_: Exception) {
                    } finally {
                        try {
                            socket.close()
                        } catch (_: Exception) {
                        }
                    }
                }
            } catch (_: Exception) {
            }
        }, "TapShare-Listen").start()
    }

    fun stopListening() {
        running.set(false)
        try {
            serverSocket?.close()
        } catch (_: Exception) {
        }
        serverSocket = null
    }

    /**
     * Resolve the peer by BLE beacon ([peerId]) first, then fall back to a
     * classic address from NFC if the OS still exposes a real MAC.
     */
    @SuppressLint("MissingPermission")
    suspend fun sendTo(
        peerId: String,
        peerAddress: String,
        media: ShareSession.ActiveMedia
    ): Boolean = withContext(Dispatchers.IO) {
        val adapter = adapter() ?: return@withContext false
        val beacon = BleBeacon(context)
        val fromBle = beacon.findDevice(peerId)
        val device = fromBle ?: run {
            if (peerAddress.isBlank() || peerAddress.startsWith("02:00:00")) {
                null
            } else {
                try {
                    adapter.getRemoteDevice(peerAddress)
                } catch (_: Exception) {
                    null
                }
            }
        } ?: return@withContext false

        connectAndSend(adapter, device, media)
    }

    @SuppressLint("MissingPermission")
    private fun connectAndSend(
        adapter: BluetoothAdapter,
        device: BluetoothDevice,
        media: ShareSession.ActiveMedia
    ): Boolean {
        var socket: BluetoothSocket? = null
        return try {
            socket = device.createRfcommSocketToServiceRecord(SERVICE_UUID)
            adapter.cancelDiscovery()
            socket.connect()
            writeOutgoing(socket, media)
            true
        } catch (_: Exception) {
            try {
                socket?.close()
                val m = device.javaClass.getMethod(
                    "createRfcommSocket",
                    Int::class.javaPrimitiveType
                )
                socket = m.invoke(device, 1) as BluetoothSocket
                socket.connect()
                writeOutgoing(socket, media)
                true
            } catch (_: Exception) {
                false
            }
        } finally {
            try {
                socket?.close()
            } catch (_: Exception) {
            }
        }
    }

    private fun writeOutgoing(socket: BluetoothSocket, media: ShareSession.ActiveMedia) {
        val bytes = context.contentResolver.openInputStream(media.uri)?.use { it.readBytes() }
            ?: error("Cannot read media")
        require(bytes.size <= MAX_BYTES) { "File too large" }
        val out = DataOutputStream(socket.outputStream)
        out.writeInt(MAGIC)
        out.writeUTF(media.mimeType)
        out.writeUTF(media.displayName)
        out.writeInt(bytes.size)
        out.write(bytes)
        out.flush()
    }

    private fun readIncoming(socket: BluetoothSocket): Pair<Uri, String>? {
        val input = DataInputStream(socket.inputStream)
        val magic = input.readInt()
        if (magic != MAGIC) return null
        val mime = input.readUTF()
        val name = input.readUTF().ifBlank { "tapshare_${System.currentTimeMillis()}" }
        val size = input.readInt()
        if (size <= 0 || size > MAX_BYTES) return null
        val bytes = ByteArray(size)
        input.readFully(bytes)
        val uri = persistReceived(bytes, mime, name) ?: return null
        return uri to mime
    }

    private fun persistReceived(bytes: ByteArray, mime: String, displayName: String): Uri? {
        val isVideo = mime.startsWith("video/")
        val safeName = displayName.replace(Regex("[^A-Za-z0-9._-]"), "_")
            .ifBlank { if (isVideo) "tapshare.mp4" else "tapshare.jpg" }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val collection = if (isVideo) {
                MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
            } else {
                MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
            }
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, safeName)
                put(MediaStore.MediaColumns.MIME_TYPE, mime)
                put(
                    MediaStore.MediaColumns.RELATIVE_PATH,
                    if (isVideo) Environment.DIRECTORY_MOVIES + "/TapShare"
                    else Environment.DIRECTORY_PICTURES + "/TapShare"
                )
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
            val resolver = context.contentResolver
            val uri = resolver.insert(collection, values) ?: return null
            resolver.openOutputStream(uri)?.use { it.write(bytes) } ?: return null
            values.clear()
            values.put(MediaStore.MediaColumns.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
            return uri
        }

        val dir = File(
            Environment.getExternalStoragePublicDirectory(
                if (isVideo) Environment.DIRECTORY_MOVIES else Environment.DIRECTORY_PICTURES
            ),
            "TapShare"
        )
        if (!dir.exists()) dir.mkdirs()
        val file = File(dir, safeName)
        FileOutputStream(file).use { it.write(bytes) }
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DATA, file.absolutePath)
            put(MediaStore.MediaColumns.MIME_TYPE, mime)
            put(MediaStore.MediaColumns.DISPLAY_NAME, safeName)
        }
        val uri = context.contentResolver.insert(
            if (isVideo) MediaStore.Video.Media.EXTERNAL_CONTENT_URI
            else MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            values
        )
        return uri ?: Uri.fromFile(file)
    }
}
