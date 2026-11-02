package com.tapshare.app.transfer

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.bluetooth.le.BluetoothLeAdvertiser
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.ParcelUuid
import com.tapshare.app.util.PeerIdentity
import java.nio.charset.StandardCharsets
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/**
 * BLE beacon so peers can find each other after an NFC tap even when the
 * classic Bluetooth MAC is hidden (02:00:00:00:00:00 on modern Android).
 */
class BleBeacon(private val context: Context) {

    companion object {
        val ADVERTISE_UUID: UUID = UUID.fromString("a1b2c3d4-1111-2222-3333-abcdef123456")
    }

    private val adapter: BluetoothAdapter?
        get() = context.getSystemService(BluetoothManager::class.java)?.adapter

    private var advertiser: BluetoothLeAdvertiser? = null
    private var advertiseCallback: AdvertiseCallback? = null

    @SuppressLint("MissingPermission")
    fun startAdvertising() {
        val adv = adapter?.bluetoothLeAdvertiser ?: return
        advertiser = adv
        val peerId = PeerIdentity.id(context).take(18)
        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            .setConnectable(true)
            .setTimeout(0)
            .build()
        val data = AdvertiseData.Builder()
            .setIncludeDeviceName(false)
            .addServiceUuid(ParcelUuid(ADVERTISE_UUID))
            .addServiceData(ParcelUuid(ADVERTISE_UUID), peerId.toByteArray(StandardCharsets.UTF_8))
            .build()
        val callback = object : AdvertiseCallback() {}
        advertiseCallback = callback
        try {
            adv.startAdvertising(settings, data, callback)
        } catch (_: Exception) {
        }
    }

    @SuppressLint("MissingPermission")
    fun stopAdvertising() {
        try {
            advertiseCallback?.let { advertiser?.stopAdvertising(it) }
        } catch (_: Exception) {
        }
        advertiseCallback = null
    }

    /**
     * Scan briefly for a TapShare BLE beacon whose service data matches [peerId].
     */
    @SuppressLint("MissingPermission")
    fun findDevice(peerId: String, timeoutMs: Long = 8_000): BluetoothDevice? {
        val scanner: BluetoothLeScanner = adapter?.bluetoothLeScanner ?: return null
        val found = AtomicReference<BluetoothDevice?>(null)
        val latch = CountDownLatch(1)
        val needle = peerId.take(18).toByteArray(StandardCharsets.UTF_8)
        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult?) {
                val record = result?.scanRecord ?: return
                val data = record.getServiceData(ParcelUuid(ADVERTISE_UUID)) ?: return
                if (data.contentEquals(needle)) {
                    found.set(result.device)
                    latch.countDown()
                }
            }
        }
        val filter = ScanFilter.Builder()
            .setServiceUuid(ParcelUuid(ADVERTISE_UUID))
            .build()
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()
        return try {
            scanner.startScan(listOf(filter), settings, callback)
            latch.await(timeoutMs, TimeUnit.MILLISECONDS)
            found.get()
        } catch (_: Exception) {
            null
        } finally {
            try {
                scanner.stopScan(callback)
            } catch (_: Exception) {
            }
        }
    }
}
