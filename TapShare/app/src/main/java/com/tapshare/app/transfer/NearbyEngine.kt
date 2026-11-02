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
import java.util.concurrent.atomic.AtomicReference

/**
 * Reliable phone-to-phone share via Google Nearby Connections
 * (Bluetooth + Wi‑Fi under the hood — works on Samsung with Play Services).
 */
class NearbyEngine(private val context: Context) {

    companion object {
        private const val TAG = "TapShareNearby"
        private const val SERVICE_ID = "com.tapshare.app.SHARE"
        // CLUSTER is more reliable when both phones advertise + discover at once.
        private val STRATEGY = Strategy.P2P_CLUSTER
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
        stop()
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

    private fun endpointName(): String {
        val model = PeerIdentity.displayName(context).replace(" ", "").take(10)
        val id = PeerIdentity.id(context).take(4)
        return "TS-$model-$id"
    }

    private val discoveryCallback = object : EndpointDiscoveryCallback() {
        override fun onEndpointFound(endpointId: String, info: DiscoveredEndpointInfo) {
            Log.i(TAG, "found ${info.endpointName}")
            found[endpointId] = info.endpointName
            // Connect immediately so a tap/share can send right away.
            request(endpointId)
        }

        override fun onEndpointLost(endpointId: String) {
            found.remove(endpointId)
        }
    }

    private val lifecycleCallback = object : ConnectionLifecycleCallback() {
        override fun onConnectionInitiated(endpointId: String, info: ConnectionInfo) {
            Log.i(TAG, "accept ${info.endpointName}")
            client.acceptConnection(endpointId, payloadCallback)
        }

        override fun onConnectionResult(endpointId: String, resolution: ConnectionResolution) {
            if (resolution.status.statusCode == ConnectionsStatusCodes.STATUS_OK) {
                Log.i(TAG, "connected $endpointId")
                connected.add(endpointId)
            } else {
                Log.w(TAG, "connect failed ${resolution.status}")
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
                    if (text.startsWith("meta|")) {
                        val parts = text.split("|", limit = 3)
                        if (parts.size == 3) {
                            lastMime = parts[1].ifBlank { "image/jpeg" }
                            lastName = parts[2].ifBlank { "tapshare.jpg" }
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

    /** Wait for a peer, then send the photo. Call from a background thread. */
    fun send(media: ShareSession.ActiveMedia, timeoutMs: Long = 30_000): Boolean {
        if (!running.get()) {
            restart()
        } else {
            // Nudge discovery without tearing down live links.
            found.keys.forEach { request(it) }
        }

        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline && connected.isEmpty()) {
            found.keys.forEach { request(it) }
            try {
                Thread.sleep(300)
            } catch (_: InterruptedException) {
                return false
            }
        }
        val endpoint = connected.firstOrNull()
        if (endpoint == null) {
            Log.e(TAG, "no peer connected in time")
            return false
        }

        return try {
            val meta = "meta|${media.mimeType}|${media.displayName}"
            client.sendPayload(
                endpoint,
                Payload.fromBytes(meta.toByteArray(StandardCharsets.UTF_8))
            )

            val latch = CountDownLatch(1)
            outboundDone.set(latch)
            outboundOk.set(false)

            val filePayload = toFilePayload(media) ?: return false
            outboundPayloadId = filePayload.id
            client.sendPayload(endpoint, filePayload)
                .addOnFailureListener {
                    Log.e(TAG, "sendPayload failed", it)
                    outboundOk.set(false)
                    latch.countDown()
                }

            val finished = latch.await(90, TimeUnit.SECONDS)
            finished && outboundOk.get()
        } catch (t: Throwable) {
            Log.e(TAG, "send error", t)
            false
        }
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
