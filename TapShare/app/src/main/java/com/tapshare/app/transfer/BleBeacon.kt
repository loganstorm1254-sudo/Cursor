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
import com.tapshare.app.util.ShareSession
import java.nio.ByteBuffer
import java.nio.charset.StandardCharsets
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong

/**
 * Always-on BLE advertise + scan so TapShare phones find each other over Bluetooth
 * when the tops are tapped together (no NFC required).
 */
class BleBeacon(private val context: Context) {

    data class NearbyPeer(
        val peerId: String,
        val device: BluetoothDevice,
        val rssi: Int,
        val hasMedia: Boolean,
        val bumpEpochSec: Long,
        val displayHint: String
    )

    companion object {
        val ADVERTISE_UUID: UUID = UUID.fromString("a1b2c3d4-1111-2222-3333-abcdef123456")
        private const val FLAG_HAS_MEDIA = 0x01
    }

    private val adapter: BluetoothAdapter?
        get() = context.getSystemService(BluetoothManager::class.java)?.adapter

    private var advertiser: BluetoothLeAdvertiser? = null
    private var advertiseCallback: AdvertiseCallback? = null
    private val lastBumpEpoch = AtomicLong(0)
    private val nearby = ConcurrentHashMap<String, NearbyPeer>()

    @SuppressLint("MissingPermission")
    fun startAdvertising() {
        stopAdvertising()
        val adv = adapter?.bluetoothLeAdvertiser ?: return
        advertiser = adv
        val callback = object : AdvertiseCallback() {}
        advertiseCallback = callback
        try {
            adv.startAdvertising(advertiseSettings(), buildAdvertiseData(), callback)
        } catch (_: Exception) {
        }
    }

    /** Refresh advert payload (media flag / bump time) without tearing down forever. */
    @SuppressLint("MissingPermission")
    fun refreshAdvertising() {
        startAdvertising()
    }

    fun signalBump() {
        lastBumpEpoch.set(System.currentTimeMillis() / 1000L)
        refreshAdvertising()
    }

    @SuppressLint("MissingPermission")
    fun stopAdvertising() {
        try {
            advertiseCallback?.let { advertiser?.stopAdvertising(it) }
        } catch (_: Exception) {
        }
        advertiseCallback = null
    }

    private fun advertiseSettings(): AdvertiseSettings {
        return AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            .setConnectable(true)
            .setTimeout(0)
            .build()
    }

    private fun buildAdvertiseData(): AdvertiseData {
        val shortId = shortPeerId(PeerIdentity.id(context))
        val hasMedia = ShareSession.get() != null
        val bump = lastBumpEpoch.get()
        // payload: shortId(8 ascii) + flags(1) + bumpEpochSec(4) = 13 bytes
        val buf = ByteBuffer.allocate(13)
        buf.put(shortId.toByteArray(StandardCharsets.US_ASCII))
        buf.put((if (hasMedia) FLAG_HAS_MEDIA else 0).toByte())
        buf.putInt(bump.toInt())
        return AdvertiseData.Builder()
            .setIncludeDeviceName(false)
            .addServiceUuid(ParcelUuid(ADVERTISE_UUID))
            .addServiceData(ParcelUuid(ADVERTISE_UUID), buf.array())
            .build()
    }

    private fun shortPeerId(full: String): String {
        return full.replace("-", "").take(8).padEnd(8, 'x')
    }

    /**
     * Scan for nearby TapShare phones and return the best match for a physical tap:
     * prefer peers that bumped in the same ~4s window, else strongest RSSI.
     */
    @SuppressLint("MissingPermission")
    fun findTapPeer(timeoutMs: Long = 4500): NearbyPeer? {
        val scanner: BluetoothLeScanner = adapter?.bluetoothLeScanner ?: return null
        nearby.clear()
        val myShort = shortPeerId(PeerIdentity.id(context))
        val myBump = lastBumpEpoch.get()

        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult?) {
                ingest(result, myShort)
            }

            override fun onBatchScanResults(results: MutableList<ScanResult>?) {
                results?.forEach { ingest(it, myShort) }
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
            // Collect advertisers for a short window, then pick closest / co-bumped peer.
            val step = 400L
            var waited = 0L
            while (waited < timeoutMs) {
                Thread.sleep(step)
                waited += step
                if (pickBest(myBump) != null && waited >= 1200L) break
            }
            pickBest(myBump)
        } catch (_: Exception) {
            pickBest(myBump)
        } finally {
            try {
                scanner.stopScan(callback)
            } catch (_: Exception) {
            }
        }
    }

    /** Continuous lightweight scan while a photo is on screen. */
    @SuppressLint("MissingPermission")
    fun startWatching(onChanged: (List<NearbyPeer>) -> Unit): ScanCallback? {
        val scanner = adapter?.bluetoothLeScanner ?: return null
        val myShort = shortPeerId(PeerIdentity.id(context))
        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult?) {
                ingest(result, myShort)
                onChanged(nearby.values.sortedByDescending { it.rssi })
            }
        }
        return try {
            scanner.startScan(
                listOf(ScanFilter.Builder().setServiceUuid(ParcelUuid(ADVERTISE_UUID)).build()),
                ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(),
                callback
            )
            callback
        } catch (_: Exception) {
            null
        }
    }

    @SuppressLint("MissingPermission")
    fun stopWatching(callback: ScanCallback?) {
        if (callback == null) return
        try {
            adapter?.bluetoothLeScanner?.stopScan(callback)
        } catch (_: Exception) {
        }
    }

    @SuppressLint("MissingPermission")
    private fun ingest(result: ScanResult?, myShort: String) {
        if (result == null) return
        val data = result.scanRecord?.getServiceData(ParcelUuid(ADVERTISE_UUID)) ?: return
        if (data.size < 13) return
        val shortId = String(data, 0, 8, StandardCharsets.US_ASCII)
        if (shortId == myShort) return
        val flags = data[8].toInt() and 0xFF
        val bump = ByteBuffer.wrap(data, 9, 4).int.toLong() and 0xFFFFFFFFL
        val name = try {
            result.device.name?.takeIf { it.isNotBlank() }
        } catch (_: Exception) {
            null
        } ?: "Nearby phone"
        val peer = NearbyPeer(
            peerId = shortId,
            device = result.device,
            rssi = result.rssi,
            hasMedia = flags and FLAG_HAS_MEDIA != 0,
            bumpEpochSec = bump,
            displayHint = name
        )
        nearby[shortId] = peer
    }

    private fun pickBest(myBump: Long): NearbyPeer? {
        val peers = nearby.values.toList()
        if (peers.isEmpty()) return null
        val bumped = peers.filter { peer ->
            myBump > 0 && peer.bumpEpochSec > 0 &&
                kotlin.math.abs(peer.bumpEpochSec - myBump) <= 4
        }
        val pool = bumped.ifEmpty { peers }
        return pool.maxByOrNull { it.rssi }
    }
}
