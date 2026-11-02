package com.tapshare.app.transfer

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattServer
import android.bluetooth.BluetoothGattServerCallback
import android.bluetooth.BluetoothGattService
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.content.Context
import android.net.Uri
import android.os.Build
import android.util.Log
import com.tapshare.app.util.ShareSession
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/**
 * BLE GATT photo transfer — works with the address from a BLE scan (unlike RFCOMM).
 */
class GattTransfer(private val context: Context) {

    companion object {
        val SERVICE_UUID: UUID = UUID.fromString("a1b2c3d4-aaaa-bbbb-cccc-abcdef123456")
        val CTRL_UUID: UUID = UUID.fromString("a1b2c3d4-aaaa-bbbb-cccc-abcdef123457")
        val DATA_UUID: UUID = UUID.fromString("a1b2c3d4-aaaa-bbbb-cccc-abcdef123458")
        private const val TAG = "TapShareGatt"
        private const val MAX_BYTES = 25 * 1024 * 1024
        private const val MAGIC = 0x54534852
    }

    private val manager = context.getSystemService(BluetoothManager::class.java)
    private var gattServer: BluetoothGattServer? = null
    private val receiveBuffer = ByteArrayOutputStream()
    private var expectedSize = -1
    private var incomingMime = "image/jpeg"
    private var incomingName = "tapshare.jpg"
    private var onReceived: ((Uri, String) -> Unit)? = null
    private val receiving = AtomicBoolean(false)

    @SuppressLint("MissingPermission")
    fun startServer(onReceived: (Uri, String) -> Unit) {
        this.onReceived = onReceived
        if (gattServer != null) return
        val server = try {
            manager?.openGattServer(context, serverCallback)
        } catch (t: Throwable) {
            Log.e(TAG, "openGattServer failed", t)
            null
        } ?: return
        gattServer = server
        try {
            val service = BluetoothGattService(SERVICE_UUID, BluetoothGattService.SERVICE_TYPE_PRIMARY)
            val ctrl = BluetoothGattCharacteristic(
                CTRL_UUID,
                BluetoothGattCharacteristic.PROPERTY_WRITE,
                BluetoothGattCharacteristic.PERMISSION_WRITE
            )
            val data = BluetoothGattCharacteristic(
                DATA_UUID,
                BluetoothGattCharacteristic.PROPERTY_WRITE,
                BluetoothGattCharacteristic.PERMISSION_WRITE
            )
            service.addCharacteristic(ctrl)
            service.addCharacteristic(data)
            server.addService(service)
        } catch (t: Throwable) {
            Log.e(TAG, "addService failed", t)
        }
    }

    @SuppressLint("MissingPermission")
    fun stopServer() {
        try {
            gattServer?.close()
        } catch (_: Exception) {
        }
        gattServer = null
    }

    private val serverCallback = object : BluetoothGattServerCallback() {
        @SuppressLint("MissingPermission")
        override fun onCharacteristicWriteRequest(
            device: BluetoothDevice?,
            requestId: Int,
            characteristic: BluetoothGattCharacteristic?,
            preparedWrite: Boolean,
            responseNeeded: Boolean,
            offset: Int,
            value: ByteArray?
        ) {
            try {
                if (value != null && characteristic != null) {
                    when (characteristic.uuid) {
                        CTRL_UUID -> handleCtrl(value)
                        DATA_UUID -> handleData(value)
                    }
                }
                if (responseNeeded) {
                    gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, null)
                }
            } catch (t: Throwable) {
                Log.e(TAG, "write request failed", t)
                if (responseNeeded) {
                    try {
                        gattServer?.sendResponse(
                            device,
                            requestId,
                            BluetoothGatt.GATT_FAILURE,
                            offset,
                            null
                        )
                    } catch (_: Exception) {
                    }
                }
            }
        }
    }

    private fun handleCtrl(value: ByteArray) {
        if (value.size < 12) return
        val buf = ByteBuffer.wrap(value)
        val magic = buf.int
        if (magic != MAGIC) return
        expectedSize = buf.int
        val mimeLen = buf.short.toInt() and 0xFFFF
        val nameLen = buf.short.toInt() and 0xFFFF
        if (value.size < 12 + mimeLen + nameLen) return
        incomingMime = String(value, 12, mimeLen, Charsets.UTF_8)
        incomingName = String(value, 12 + mimeLen, nameLen, Charsets.UTF_8)
        receiveBuffer.reset()
        receiving.set(true)
        if (expectedSize <= 0 || expectedSize > MAX_BYTES) {
            receiving.set(false)
            expectedSize = -1
        }
    }

    private fun handleData(value: ByteArray) {
        if (!receiving.get()) return
        receiveBuffer.write(value)
        if (expectedSize > 0 && receiveBuffer.size() >= expectedSize) {
            receiving.set(false)
            val bytes = receiveBuffer.toByteArray().copyOf(expectedSize)
            receiveBuffer.reset()
            expectedSize = -1
            val uri = MediaSaver.persist(context, bytes, incomingMime, incomingName)
            if (uri != null) {
                try {
                    onReceived?.invoke(uri, incomingMime)
                } catch (t: Throwable) {
                    Log.e(TAG, "callback failed", t)
                }
            }
        }
    }

    @SuppressLint("MissingPermission")
    fun send(device: BluetoothDevice, media: ShareSession.ActiveMedia): Boolean {
        val bytes = try {
            context.contentResolver.openInputStream(media.uri)?.use { it.readBytes() }
        } catch (_: Exception) {
            null
        } ?: return false
        if (bytes.size > MAX_BYTES) return false

        val done = CountDownLatch(1)
        val ok = AtomicBoolean(false)
        val writeLatch = AtomicReference<CountDownLatch?>(null)
        val writeOk = AtomicBoolean(false)
        val mtuPayload = AtomicInteger(20)
        val mimeBytes = media.mimeType.take(60).toByteArray(Charsets.UTF_8)
        val nameBytes = media.displayName.take(80).toByteArray(Charsets.UTF_8)

        val callback = object : BluetoothGattCallback() {
            @Deprecated("Deprecated in Java")
            override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    try {
                        gatt.requestMtu(517)
                    } catch (_: Exception) {
                        gatt.discoverServices()
                    }
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    done.countDown()
                }
            }

            override fun onMtuChanged(gatt: BluetoothGatt, mtu: Int, status: Int) {
                mtuPayload.set((mtu - 3).coerceIn(20, 500))
                gatt.discoverServices()
            }

            override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    done.countDown()
                    return
                }
                Thread({
                    try {
                        val service = gatt.getService(SERVICE_UUID) ?: return@Thread
                        val ctrl = service.getCharacteristic(CTRL_UUID) ?: return@Thread
                        val data = service.getCharacteristic(DATA_UUID) ?: return@Thread

                        val header = ByteBuffer.allocate(12 + mimeBytes.size + nameBytes.size)
                        header.putInt(MAGIC)
                        header.putInt(bytes.size)
                        header.putShort(mimeBytes.size.toShort())
                        header.putShort(nameBytes.size.toShort())
                        header.put(mimeBytes)
                        header.put(nameBytes)
                        if (!writeSync(gatt, ctrl, header.array(), writeLatch, writeOk)) return@Thread

                        var offset = 0
                        val chunk = mtuPayload.get()
                        while (offset < bytes.size) {
                            val end = (offset + chunk).coerceAtMost(bytes.size)
                            if (!writeSync(
                                    gatt,
                                    data,
                                    bytes.copyOfRange(offset, end),
                                    writeLatch,
                                    writeOk
                                )
                            ) {
                                return@Thread
                            }
                            offset = end
                        }
                        ok.set(true)
                    } catch (t: Throwable) {
                        Log.e(TAG, "send failed", t)
                    } finally {
                        try {
                            gatt.disconnect()
                        } catch (_: Exception) {
                        }
                        done.countDown()
                    }
                }, "TapShare-GattSend").start()
            }

            override fun onCharacteristicWrite(
                gatt: BluetoothGatt,
                characteristic: BluetoothGattCharacteristic,
                status: Int
            ) {
                writeOk.set(status == BluetoothGatt.GATT_SUCCESS)
                writeLatch.get()?.countDown()
            }
        }

        return try {
            val gatt = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                device.connectGatt(context, false, callback, BluetoothDevice.TRANSPORT_LE)
            } else {
                @Suppress("DEPRECATION")
                device.connectGatt(context, false, callback)
            }
            done.await(120, TimeUnit.SECONDS)
            try {
                gatt.close()
            } catch (_: Exception) {
            }
            ok.get()
        } catch (t: Throwable) {
            Log.e(TAG, "connectGatt failed", t)
            false
        }
    }

    @SuppressLint("MissingPermission")
    private fun writeSync(
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        value: ByteArray,
        writeLatch: AtomicReference<CountDownLatch?>,
        writeOk: AtomicBoolean
    ): Boolean {
        val latch = CountDownLatch(1)
        writeLatch.set(latch)
        writeOk.set(false)
        val started = try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                gatt.writeCharacteristic(
                    characteristic,
                    value,
                    BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                ) == BluetoothStatusCodes.SUCCESS
            } else {
                @Suppress("DEPRECATION")
                characteristic.value = value
                characteristic.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                @Suppress("DEPRECATION")
                gatt.writeCharacteristic(characteristic)
            }
        } catch (_: Exception) {
            false
        }
        if (!started) return false
        return latch.await(5, TimeUnit.SECONDS) && writeOk.get()
    }
}
