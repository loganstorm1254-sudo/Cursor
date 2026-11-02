package com.tapshare.app.transfer

import android.content.Context
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.util.Log
import com.google.android.gms.nearby.Nearby
import com.google.android.gms.nearby.connection.AdvertisingOptions
import com.google.android.gms.nearby.connection.ConnectionInfo
import com.google.android.gms.nearby.connection.ConnectionLifecycleCallback
import com.google.android.gms.nearby.connection.ConnectionResolution
import com.google.android.gms.nearby.connection.ConnectionsClient
import com.google.android.gms.nearby.connection.ConnectionsStatusCodes
import com.google.android.gms.nearby.connection.DiscoveredEndpointInfo
import com.google.android.gms.nearby.connection.DiscoveryOptions
import com.google.android.gms.nearby.connection.EndpointDiscoveryCallback
import com.google.android.gms.nearby.connection.Payload
import com.google.android.gms.nearby.connection.PayloadCallback
import com.google.android.gms.nearby.connection.PayloadTransferUpdate
import com.google.android.gms.nearby.connection.Strategy
import com.tapshare.app.util.PeerIdentity
import com.tapshare.app.util.ShareSession
import java.io.File
import java.io.FileOutputStream
import java.nio.charset.StandardCharsets
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference

/**
 * Nearby Connections engine. Discovers peers quietly, but ONLY connects / sends
 * when a real phone-top tap triggers [sendAfterTap].
 */
class NearbyEngine(private val context: Context) {

    companion object {
        private const val TAG = "TapShareNearby"
        private const val SERVICE_ID = "com.tapshare.app.SHARE"
        private val STRATEGY = Strategy.P2P_CLUSTER
        private const val BUMP_WINDOW_MS = 3500L
    }

    private val client: ConnectionsClient = Nearby.getConnectionsClient(context)
    private val connected = ConcurrentHashMap.newKeySet<String>()
    private val found = ConcurrentHashMap<String, String>()
    private var onReceived: ((Uri, String) -> Unit)? = null
    private val running = AtomicBoolean(false)

    private var lastMime = "image/jpeg"
    private var lastName = "tapshare.jpg"
    private val incomingFiles = ConcurrentHashMap<Long, Payload>()
    private val outboundDone = AtomicReference<CountDownLatch?>(null)
    private val outboundOk = AtomicBoolean(false)
    private var outboundPayloadId = -1L

    /** Local bump time (ms). Peers exchange this so we only share on a real tap. */
    private val localBumpAt = AtomicLong(0)
    private val peerBumpAt = AtomicLong(0)
    private val peerBumpLatch = AtomicReference<CountDownLatch?>(null)

    fun start(onReceived: (Uri, String) -> Unit) {
        this.onReceived = onReceived
        restart()
    }

    fun stop() {
        running.set(false)
        try {
            client.stopAllEndpoints()
            client.stopAdvertising()
            client.stopDiscovery()
        } catch (_: Exception) {
        }
        connected.clear()
        found.clear()
    }

    fun restart() {
        try {
            client.stopAdvertising()
            client.stopDiscovery()
        } catch (_: Exception) {
        }
        // Keep existing connections if any; just ensure advertise/discover are on.
        running.set(true)
        val name = endpointName()
        client.startAdvertising(
            name,
            SERVICE_ID,
            lifecycleCallback,
            AdvertisingOptions.Builder().setStrategy(STRATEGY).build()
        ).addOnSuccessListener {
            Log.i(TAG, "advertising as $name")
        }.addOnFailureListener {
            Log.e(TAG, "advertise failed", it)
        }

        client.startDiscovery(
            SERVICE_ID,
            discoveryCallback,
            DiscoveryOptions.Builder().setStrategy(STRATEGY).build()
        ).addOnSuccessListener {
            Log.i(TAG, "discovering")
        }.addOnFailureListener {
            Log.e(TAG, "discover failed", it)
        }
    }

    fun hasNearbyPeers(): Boolean = found.isNotEmpty() || connected.isNotEmpty()

    private fun endpointName(): String {
        val model = PeerIdentity.displayName(context).replace(" ", "").take(10)
        val id = PeerIdentity.id(context).take(4)
        return "TS-$model-$id"
    }

    private val discoveryCallback = object : EndpointDiscoveryCallback() {
        override fun onEndpointFound(endpointId: String, info: DiscoveredEndpointInfo) {
            Log.i(TAG, "found ${info.endpointName}")
            found[endpointId] = info.endpointName
            // Do NOT auto-connect — waiting for a physical tap.
        }

        override fun onEndpointLost(endpointId: String) {
            found.remove(endpointId)
        }
    }

    private val lifecycleCallback = object : ConnectionLifecycleCallback() {
        override fun onConnectionInitiated(endpointId: String, info: ConnectionInfo) {
            // Only accept if we (or they) bumped very recently — stops idle pairing.
            val now = System.currentTimeMillis()
            val recentLocal = now - localBumpAt.get() in 0..BUMP_WINDOW_MS * 2
            if (recentLocal) {
                client.acceptConnection(endpointId, payloadCallback)
            } else {
                // Still accept so the tapped sender can push — receiver may not bump as hard.
                // Gate the *send* on dual bump instead.
                client.acceptConnection(endpointId, payloadCallback)
            }
        }

        override fun onConnectionResult(endpointId: String, resolution: ConnectionResolution) {
            if (resolution.status.statusCode == ConnectionsStatusCodes.STATUS_OK) {
                connected.add(endpointId)
            } else {
                connected.remove(endpointId)
            }
        }

        override fun onDisconnected(endpointId: String) {
            connected.remove(endpointId)
        }
    }

    private val payloadCallback = object : PayloadCallback() {
        override fun onPayloadReceived(endpointId: String, payload: Payload) {
            when (payload.type) {
                Payload.Type.BYTES -> {
                    val text = payload.asBytes()?.toString(StandardCharsets.UTF_8) ?: return
                    when {
                        text.startsWith("bump|") -> {
                            val ts = text.removePrefix("bump|").toLongOrNull() ?: return
                            peerBumpAt.set(ts)
                            peerBumpLatch.get()?.countDown()
                        }
                        text.startsWith("meta|") -> {
                            val parts = text.split("|", limit = 3)
                            if (parts.size == 3) {
                                lastMime = parts[1].ifBlank { "image/jpeg" }
                                lastName = parts[2].ifBlank { "tapshare.jpg" }
                            }
                        }
                    }
                }
                Payload.Type.FILE -> incomingFiles[payload.id] = payload
                else -> Unit
            }
        }

        override fun onPayloadTransferUpdate(endpointId: String, update: PayloadTransferUpdate) {
            if (update.payloadId == outboundPayloadId) {
                when (update.status) {
                    PayloadTransferUpdate.Status.SUCCESS -> {
                        outboundOk.set(true)
                        outboundDone.get()?.countDown()
                    }
                    PayloadTransferUpdate.Status.FAILURE,
                    PayloadTransferUpdate.Status.CANCELED -> {
                        outboundOk.set(false)
                        outboundDone.get()?.countDown()
                    }
                    else -> Unit
                }
                return
            }

            if (update.status != PayloadTransferUpdate.Status.SUCCESS) return
            val payload = incomingFiles.remove(update.payloadId) ?: return
            val filePayload = payload.asFile() ?: return
            try {
                val bytes = when {
                    filePayload.asParcelFileDescriptor() != null -> {
                        ParcelFileDescriptor.AutoCloseInputStream(
                            filePayload.asParcelFileDescriptor()!!
                        ).use { it.readBytes() }
                    }
                    filePayload.asJavaFile() != null -> filePayload.asJavaFile()!!.readBytes()
                    else -> return
                }
                val uri = MediaSaver.persist(context, bytes, lastMime, lastName) ?: return
                onReceived?.invoke(uri, lastMime)
            } catch (t: Throwable) {
                Log.e(TAG, "receive failed", t)
            }
        }
    }

    private fun request(endpointId: String) {
        if (connected.contains(endpointId)) return
        client.requestConnection(endpointName(), endpointId, lifecycleCallback)
            .addOnFailureListener { Log.w(TAG, "request failed", it) }
    }

    /**
     * Called only after a real accelerometer tap. Connects, confirms the other
     * phone also tapped (bump ping), then sends the photo.
     */
    fun sendAfterTap(media: ShareSession.ActiveMedia, timeoutMs: Long = 20_000): Boolean {
        val bumpTime = System.currentTimeMillis()
        localBumpAt.set(bumpTime)
        peerBumpAt.set(0)
        if (!running.get()) restart()

        val latch = CountDownLatch(1)
        peerBumpLatch.set(latch)

        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline && connected.isEmpty()) {
            found.keys.forEach { request(it) }
            try {
                Thread.sleep(250)
            } catch (_: InterruptedException) {
                return false
            }
        }
        if (connected.isEmpty()) {
            Log.e(TAG, "no peer after tap")
            return false
        }

        // Tell peers we tapped, and wait for their tap signal.
        val bumpPayload = Payload.fromBytes("bump|$bumpTime".toByteArray(StandardCharsets.UTF_8))
        connected.forEach { id ->
            client.sendPayload(id, bumpPayload)
        }

        // Wait for peer bump — if they tapped tops together it arrives quickly.
        // If not, abort (this stops share-when-not-tapped).
        val peerSignaled = latch.await(BUMP_WINDOW_MS, TimeUnit.MILLISECONDS) ||
            peerBumpAt.get() > 0
        val peerTs = peerBumpAt.get()
        val tapsAligned = peerSignaled &&
            peerTs > 0 &&
            kotlin.math.abs(peerTs - bumpTime) <= BUMP_WINDOW_MS

        // Also accept if peer bumped slightly before us (their signal already arrived).
        if (!tapsAligned && peerTs == 0L) {
            // Give one more short wait — other phone's detector may fire a beat later.
            latch.await(1200, TimeUnit.MILLISECONDS)
        }
        val peerTs2 = peerBumpAt.get()
        val okTap = peerTs2 > 0 && kotlin.math.abs(peerTs2 - bumpTime) <= BUMP_WINDOW_MS + 1200
        if (!okTap) {
            Log.w(TAG, "peer did not tap — aborting send")
            return false
        }

        val endpoint = connected.firstOrNull() ?: return false
        return try {
            val meta = "meta|${media.mimeType}|${media.displayName}"
            client.sendPayload(
                endpoint,
                Payload.fromBytes(meta.toByteArray(StandardCharsets.UTF_8))
            )

            val done = CountDownLatch(1)
            outboundDone.set(done)
            outboundOk.set(false)
            val filePayload = toFilePayload(media) ?: return false
            outboundPayloadId = filePayload.id
            client.sendPayload(endpoint, filePayload)
                .addOnFailureListener {
                    outboundOk.set(false)
                    done.countDown()
                }
            done.await(90, TimeUnit.SECONDS) && outboundOk.get()
        } catch (t: Throwable) {
            Log.e(TAG, "send error", t)
            false
        }
    }

    /** Receiver side: record that this phone was tapped so sender's bump check passes. */
    fun signalLocalTap() {
        val bumpTime = System.currentTimeMillis()
        localBumpAt.set(bumpTime)
        if (!running.get()) restart()
        found.keys.forEach { request(it) }
        val payload = Payload.fromBytes("bump|$bumpTime".toByteArray(StandardCharsets.UTF_8))
        // Send to anyone already connected; also after connections land.
        connected.forEach { id -> client.sendPayload(id, payload) }
        // Retry shortly as connections complete.
        Thread {
            try {
                Thread.sleep(800)
                connected.forEach { id -> client.sendPayload(id, payload) }
                found.keys.forEach { request(it) }
                Thread.sleep(800)
                connected.forEach { id -> client.sendPayload(id, payload) }
            } catch (_: Exception) {
            }
        }.start()
    }

    private fun toFilePayload(media: ShareSession.ActiveMedia): Payload? {
        return try {
            val pfd = context.contentResolver.openFileDescriptor(media.uri, "r")
            if (pfd != null) {
                Payload.fromFile(pfd)
            } else {
                val tmp = File(context.cacheDir, "send_${System.currentTimeMillis()}.bin")
                context.contentResolver.openInputStream(media.uri)?.use { input ->
                    FileOutputStream(tmp).use { output -> input.copyTo(output) }
                } ?: return null
                Payload.fromFile(tmp)
            }
        } catch (t: Throwable) {
            Log.e(TAG, "toFilePayload failed", t)
            null
        }
    }
}
