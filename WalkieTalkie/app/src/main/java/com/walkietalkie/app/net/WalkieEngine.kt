package com.walkietalkie.app.net

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.os.Handler
import android.os.Looper
import org.eclipse.paho.client.mqttv3.MqttCallbackExtended
import org.eclipse.paho.client.mqttv3.MqttClient
import org.eclipse.paho.client.mqttv3.MqttConnectOptions
import org.eclipse.paho.client.mqttv3.MqttMessage
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence
import java.nio.ByteBuffer
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import javax.crypto.Cipher
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * Push-to-talk engine for any number of devices.
 *
 * Every device connects out to PUBLIC MQTT brokers over the internet (works
 * on mobile data or any Wi-Fi — devices never talk to each other directly).
 * The PIN picks the channel (a topic derived from its hash) AND encrypts all
 * audio with AES-256, so only devices that typed the same PIN can listen.
 *
 * The public brokers are independent networks (not bridged to each other),
 * so devices on different brokers would never hear each other. To make any
 * mix of networks work, each device connects to EVERY reachable broker and
 * transmits on all of them; receivers drop duplicate frames using a per-
 * sender sequence number. Whichever brokers each phone can reach, there is
 * always at least one in common.
 */
class WalkieEngine(private val listener: Listener) {

    interface Listener {
        fun onStatus(status: Status, detail: String)
        fun onPeers(count: Int)
        fun onReceiving(receiving: Boolean)
    }

    enum class Status { DISCONNECTED, CONNECTING, CONNECTED }

    companion object {
        // One group per independent broker network; transports within a group
        // are fallbacks for firewalled ports (TLS/WebSocket get through most).
        private val BROKER_GROUPS = listOf(
            listOf(
                "tcp://broker.emqx.io:1883",
                "ssl://broker.emqx.io:8883",
                "wss://broker.emqx.io:8084/mqtt",
            ),
            listOf(
                "tcp://broker.hivemq.com:1883",
                "ws://broker.hivemq.com:8000/mqtt",
            ),
            listOf(
                "tcp://test.mosquitto.org:1883",
                "ws://test.mosquitto.org:8080/mqtt",
            ),
        )
        private const val SAMPLE_RATE = 16000
        private const val FRAME_BYTES = 3200 // 100 ms of 16-bit mono @ 16 kHz
        private const val VERSION: Byte = 2
        private const val HEADER_BYTES = 1 + 8 + 4 + 16 // version + senderId + seq + IV
        private const val PING_INTERVAL_MS = 8_000L
        private const val PEER_TIMEOUT_MS = 25_000L
        private const val RX_IDLE_MS = 350L
        private const val CONNECT_TIMEOUT_S = 8
        private const val OP_TIMEOUT_MS = 15_000L
    }

    private val random = SecureRandom()
    private val senderId = ByteArray(8).also { random.nextBytes(it) }
    private val seqCounter = AtomicInteger(random.nextInt(1 shl 20))
    private val main = Handler(Looper.getMainLooper())

    /** Bumped on every connect/disconnect so stale attempts abort themselves. */
    private val generation = AtomicInteger()

    /** One live connection per reachable broker network. */
    private val clients = CopyOnWriteArrayList<MqttClient>()

    private var key: SecretKeySpec? = null
    private var audioTopic = ""
    private var presenceTopic = ""

    @Volatile private var connecting = false
    private val talking = AtomicBoolean(false)
    private var recordThread: Thread? = null
    private var pingThread: Thread? = null
    private var playThread: Thread? = null
    /**
     * Frames wait here for the single playback thread. Each broker connection
     * delivers messages on its own thread, and AudioTrack is NOT thread-safe:
     * creating/writing it concurrently from several broker threads crashes
     * the app natively. Only the playback thread ever touches the AudioTrack.
     */
    private val playQueue = java.util.concurrent.LinkedBlockingQueue<ByteArray>(64)
    @Volatile private var receiving = false

    /** senderId -> last time we heard them (for the device counter). */
    private val peers = ConcurrentHashMap<Long, Long>()
    /** senderId -> highest sequence number seen (drops cross-broker duplicates). */
    private val lastSeq = ConcurrentHashMap<Long, Int>()
    @Volatile private var lastPostedPeerCount = -1

    private val rxIdleRunnable = Runnable {
        receiving = false
        listener.onReceiving(false)
    }

    fun connect(pin: String) {
        disconnectInternal(notify = false)
        val gen = generation.incrementAndGet()
        connecting = true
        listener.onStatus(Status.CONNECTING, "Connecting…")

        startPlayback(gen)

        val digest = MessageDigest.getInstance("SHA-256")
            .digest("walkie-talkie-v2:$pin".toByteArray(Charsets.UTF_8))
        key = SecretKeySpec(digest, "AES")
        val channel = digest.joinToString("") { "%02x".format(it) }.substring(0, 20)
        audioTopic = "walkietalkie/v2/$channel/audio"
        presenceTopic = "walkietalkie/v2/$channel/presence"

        val groupsDone = AtomicInteger(0)
        val lastErrorHolder = arrayOfNulls<String>(1)
        for ((groupIndex, group) in BROKER_GROUPS.withIndex()) {
            Thread({
                var joined = false
                for ((epIndex, endpoint) in group.withIndex()) {
                    if (generation.get() != gen) return@Thread
                    var c: MqttClient? = null
                    try {
                        c = MqttClient(
                            endpoint,
                            "wt-" + senderId.joinToString("") { "%02x".format(it) } + "-$groupIndex$epIndex",
                            MemoryPersistence()
                        )
                        c.timeToWait = OP_TIMEOUT_MS // hard cap on every blocking call
                        c.setCallback(makeCallback(c, gen))
                        val opts = MqttConnectOptions().apply {
                            isCleanSession = true
                            isAutomaticReconnect = true
                            keepAliveInterval = 30
                            connectionTimeout = CONNECT_TIMEOUT_S
                        }
                        c.connect(opts)
                        if (generation.get() != gen) {
                            quietClose(c)
                            return@Thread
                        }
                        c.subscribe(arrayOf(audioTopic, presenceTopic), intArrayOf(0, 0))
                        clients.add(c)
                        joined = true
                        connecting = false
                        publishPresence()
                        if (pingThread == null) startPinger(gen)
                        main.post {
                            if (generation.get() == gen) {
                                listener.onStatus(
                                    Status.CONNECTED,
                                    "Connected · ${clients.size} server" + if (clients.size > 1) "s" else ""
                                )
                            }
                        }
                        break
                    } catch (e: Exception) {
                        lastErrorHolder[0] = e.message ?: e.javaClass.simpleName
                        c?.let { quietClose(it) }
                    }
                }
                if (groupsDone.incrementAndGet() == BROKER_GROUPS.size &&
                    clients.isEmpty() && generation.get() == gen
                ) {
                    connecting = false
                    main.post {
                        if (generation.get() == gen) {
                            listener.onStatus(
                                Status.DISCONNECTED,
                                "Couldn't reach any server (${lastErrorHolder[0] ?: "unreachable"}). " +
                                    "Check the internet connection and try again."
                            )
                        }
                    }
                }
            }, "walkie-connect-$groupIndex").start()
        }
    }

    private fun quietClose(c: MqttClient) {
        try { c.disconnectForcibly(300, 300) } catch (_: Exception) {}
        try { c.close(true) } catch (_: Exception) {}
    }

    private fun makeCallback(c: MqttClient, gen: Int) = object : MqttCallbackExtended {
        override fun connectComplete(reconnect: Boolean, serverURI: String) {
            // Initial subscribe happens in the connect flow; this only needs
            // to re-subscribe after Paho's automatic reconnect (cleanSession
            // drops subscriptions). Never let an exception escape: Paho would
            // tear the connection down and loop reconnect -> fail forever.
            if (!reconnect || generation.get() != gen || !clients.contains(c)) return
            for (attempt in 1..5) {
                try {
                    c.subscribe(arrayOf(audioTopic, presenceTopic), intArrayOf(0, 0))
                    break
                } catch (_: Exception) {
                    try { Thread.sleep(400) } catch (_: InterruptedException) { break }
                    if (generation.get() != gen || !c.isConnected) break
                }
            }
            try { publishPresence() } catch (_: Exception) {}
            main.post {
                if (generation.get() == gen && clients.isNotEmpty()) {
                    listener.onStatus(Status.CONNECTED, "Connected")
                }
            }
        }

        override fun connectionLost(cause: Throwable?) {
            // Other brokers may still be up; only alarm when the last one drops.
            if (generation.get() != gen || !clients.contains(c)) return
            val anyUp = clients.any { it.isConnected }
            main.post {
                if (generation.get() == gen) {
                    if (anyUp) {
                        listener.onStatus(Status.CONNECTED, "Connected")
                    } else {
                        listener.onStatus(Status.CONNECTING, "Connection lost — reconnecting…")
                    }
                }
            }
        }

        override fun messageArrived(topic: String, message: MqttMessage) {
            // Catch everything: an escaped Throwable on a broker thread kills the app.
            try {
                handleIncoming(topic, message.payload)
            } catch (_: Throwable) {
            }
        }

        override fun deliveryComplete(token: org.eclipse.paho.client.mqttv3.IMqttDeliveryToken?) {}
    }

    fun disconnect() = disconnectInternal(notify = true)

    private fun disconnectInternal(notify: Boolean) {
        generation.incrementAndGet()
        stopTalking()
        connecting = false
        pingThread?.interrupt()
        pingThread = null
        playThread?.interrupt()
        playThread = null
        playQueue.clear()
        val old = clients.toList()
        clients.clear()
        if (old.isNotEmpty()) {
            Thread({ old.forEach { quietClose(it) } }, "walkie-close").start()
        }
        peers.clear()
        lastSeq.clear()
        lastPostedPeerCount = -1
        main.removeCallbacks(rxIdleRunnable)
        receiving = false
        if (notify) {
            listener.onStatus(Status.DISCONNECTED, "Not connected")
            listener.onPeers(0)
        }
    }

    val isConnected: Boolean get() = clients.isNotEmpty()
    val isBusy: Boolean get() = connecting || clients.isNotEmpty()

    // ---------------------------------------------------------------- talking

    fun startTalking(): Boolean {
        if (clients.isEmpty() || !talking.compareAndSet(false, true)) return false
        val minBuf = AudioRecord.getMinBufferSize(
            SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
        )
        val recorder = try {
            AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                maxOf(minBuf, FRAME_BYTES * 4)
            )
        } catch (_: Exception) {
            talking.set(false)
            return false
        }
        if (recorder.state != AudioRecord.STATE_INITIALIZED) {
            recorder.release()
            talking.set(false)
            return false
        }
        recordThread = Thread({
            val buf = ByteArray(FRAME_BYTES)
            try {
                recorder.startRecording()
                while (talking.get() && clients.isNotEmpty()) {
                    var off = 0
                    while (off < buf.size && talking.get()) {
                        val n = recorder.read(buf, off, buf.size - off)
                        if (n <= 0) break
                        off += n
                    }
                    if (off > 0) publishAll(audioTopic, seal(buf, off))
                }
            } catch (_: Exception) {
            } finally {
                try { recorder.stop() } catch (_: Exception) {}
                recorder.release()
            }
        }, "walkie-record")
        recordThread!!.start()
        return true
    }

    fun stopTalking() {
        talking.set(false)
        recordThread?.join(500)
        recordThread = null
    }

    // --------------------------------------------------------------- receiving

    private fun handleIncoming(topic: String, payload: ByteArray) {
        val frame = open(payload) ?: return // own echo, wrong PIN, or garbage
        val now = System.currentTimeMillis()
        peers[frame.sender] = now
        postPeerCount(now)

        // Same frame arrives once per broker we share with the sender — only
        // accept sequence numbers STRICTLY above what we already played
        // (equal = the duplicate copy from another broker).
        val isNew = booleanArrayOf(false)
        lastSeq.compute(frame.sender) { _, prev ->
            if (prev == null || frame.seq > prev) {
                isNew[0] = true
                frame.seq
            } else {
                prev
            }
        }
        if (!isNew[0]) return

        if (topic != audioTopic) return
        if (!receiving) {
            receiving = true
            main.post { listener.onReceiving(true) }
        }
        main.removeCallbacks(rxIdleRunnable)
        main.postDelayed(rxIdleRunnable, RX_IDLE_MS)
        // Hand off to the playback thread; if it can't keep up, drop the
        // oldest frame rather than blocking the broker thread.
        if (!playQueue.offer(frame.pcm)) {
            playQueue.poll()
            playQueue.offer(frame.pcm)
        }
    }

    private fun postPeerCount(now: Long) {
        val count = peers.values.count { now - it < PEER_TIMEOUT_MS }
        if (count != lastPostedPeerCount) {
            lastPostedPeerCount = count
            main.post { listener.onPeers(count) }
        }
    }

    /** The only place the AudioTrack is created, written, or released. */
    private fun startPlayback(gen: Int) {
        playQueue.clear()
        playThread = Thread({
            var track: AudioTrack? = null
            try {
                while (generation.get() == gen) {
                    val pcm = playQueue.poll(500, java.util.concurrent.TimeUnit.MILLISECONDS)
                        ?: continue
                    if (track == null) track = createTrack()
                    try {
                        track?.write(pcm, 0, pcm.size)
                    } catch (_: Exception) {
                        try { track?.release() } catch (_: Exception) {}
                        track = null
                    }
                }
            } catch (_: InterruptedException) {
            } finally {
                try { track?.release() } catch (_: Exception) {}
            }
        }, "walkie-play").also { it.isDaemon = true; it.start() }
    }

    private fun createTrack(): AudioTrack? = try {
        val minBuf = AudioTrack.getMinBufferSize(
            SAMPLE_RATE, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT
        )
        val t = AudioTrack(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .setLegacyStreamType(AudioManager.STREAM_MUSIC)
                .build(),
            AudioFormat.Builder()
                .setSampleRate(SAMPLE_RATE)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .build(),
            maxOf(minBuf, FRAME_BYTES * 6),
            AudioTrack.MODE_STREAM,
            AudioManager.AUDIO_SESSION_ID_GENERATE
        )
        t.play()
        t
    } catch (_: Exception) {
        null
    }

    // ---------------------------------------------------------------- plumbing

    private fun startPinger(gen: Int) {
        pingThread = Thread({
            try {
                while (generation.get() == gen) {
                    if (clients.isNotEmpty()) publishPresence()
                    postPeerCount(System.currentTimeMillis())
                    Thread.sleep(PING_INTERVAL_MS)
                }
            } catch (_: InterruptedException) {
            }
        }, "walkie-ping").also { it.isDaemon = true; it.start() }
    }

    private fun publishPresence() {
        publishAll(presenceTopic, seal("PING".toByteArray(Charsets.UTF_8), 4))
    }

    /** Send on every connected broker so all devices hear it regardless of broker. */
    private fun publishAll(topic: String, payload: ByteArray) {
        for (c in clients) {
            try {
                if (c.isConnected) c.publish(topic, payload, 0, false)
            } catch (_: Exception) {
            }
        }
    }

    /** Envelope: [version][senderId(8)][seq(4)][iv(16)][AES-256-CTR ciphertext]. */
    private fun seal(data: ByteArray, len: Int): ByteArray {
        val seq = seqCounter.incrementAndGet()
        val iv = ByteArray(16).also { random.nextBytes(it) }
        val cipher = Cipher.getInstance("AES/CTR/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key, IvParameterSpec(iv))
        val ct = cipher.doFinal(data, 0, len)
        return ByteBuffer.allocate(HEADER_BYTES + ct.size)
            .put(VERSION)
            .put(senderId)
            .putInt(seq)
            .put(iv)
            .put(ct)
            .array()
    }

    private class Frame(val sender: Long, val seq: Int, val pcm: ByteArray)

    /** Returns the parsed frame, or null for own messages / malformed payloads. */
    private fun open(payload: ByteArray): Frame? {
        if (payload.size <= HEADER_BYTES || payload[0] != VERSION) return null
        val buf = ByteBuffer.wrap(payload, 1, payload.size - 1)
        val sid = buf.long
        val seq = buf.int
        if (sid == ByteBuffer.wrap(senderId).long) return null
        return try {
            val iv = ByteArray(16).also { buf.get(it) }
            val cipher = Cipher.getInstance("AES/CTR/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key, IvParameterSpec(iv))
            Frame(sid, seq, cipher.doFinal(payload, HEADER_BYTES, payload.size - HEADER_BYTES))
        } catch (_: Exception) {
            null
        }
    }
}
