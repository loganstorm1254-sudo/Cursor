package com.walkietalkie.b.net

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
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.atomic.AtomicBoolean
import javax.crypto.Cipher
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * Push-to-talk engine.
 *
 * Both phones connect to a public MQTT broker over the internet (works on
 * mobile data or any Wi-Fi — the phones never talk to each other directly).
 * The PIN picks the channel (a topic derived from its hash) AND encrypts the
 * audio with AES-256, so only phones that typed the same PIN can listen.
 */
class WalkieEngine(private val listener: Listener) {

    interface Listener {
        fun onStatus(status: Status, detail: String)
        fun onPeerSeen()
        fun onReceiving(receiving: Boolean)
    }

    enum class Status { DISCONNECTED, CONNECTING, CONNECTED }

    companion object {
        // Public brokers, tried in order. No account or server setup needed.
        private val BROKERS = listOf(
            "tcp://broker.hivemq.com:1883",
            "tcp://broker.emqx.io:1883",
        )
        private const val SAMPLE_RATE = 16000
        private const val FRAME_BYTES = 3200 // 100 ms of 16-bit mono @ 16 kHz
        private const val VERSION: Byte = 1
        private const val HEADER_BYTES = 1 + 8 + 16 // version + senderId + IV
        private const val PING_INTERVAL_MS = 10_000L
        private const val RX_IDLE_MS = 350L
    }

    private val random = SecureRandom()
    private val senderId = ByteArray(8).also { random.nextBytes(it) }
    private val main = Handler(Looper.getMainLooper())

    private var client: MqttClient? = null
    private var key: SecretKeySpec? = null
    private var audioTopic = ""
    private var presenceTopic = ""

    @Volatile private var connected = false
    private val talking = AtomicBoolean(false)
    private var recordThread: Thread? = null
    private var pingThread: Thread? = null
    private var track: AudioTrack? = null
    @Volatile private var receiving = false

    private val rxIdleRunnable = Runnable {
        receiving = false
        listener.onReceiving(false)
    }

    fun connect(pin: String) {
        disconnect()
        listener.onStatus(Status.CONNECTING, "Connecting…")

        val digest = MessageDigest.getInstance("SHA-256")
            .digest("walkie-talkie-v1:$pin".toByteArray(Charsets.UTF_8))
        key = SecretKeySpec(digest, "AES")
        val channel = digest.joinToString("") { "%02x".format(it) }.substring(0, 20)
        audioTopic = "walkietalkie/v1/$channel/audio"
        presenceTopic = "walkietalkie/v1/$channel/presence"

        Thread({
            var lastError = "no broker reachable"
            for (broker in BROKERS) {
                try {
                    val c = MqttClient(
                        broker,
                        "wt-" + senderId.joinToString("") { "%02x".format(it) },
                        MemoryPersistence()
                    )
                    c.setCallback(object : MqttCallbackExtended {
                        override fun connectComplete(reconnect: Boolean, serverURI: String) {
                            connected = true
                            c.subscribe(arrayOf(audioTopic, presenceTopic), intArrayOf(0, 0))
                            publishPresence()
                            main.post { listener.onStatus(Status.CONNECTED, "Connected") }
                        }

                        override fun connectionLost(cause: Throwable?) {
                            connected = false
                            main.post { listener.onStatus(Status.CONNECTING, "Reconnecting…") }
                        }

                        override fun messageArrived(topic: String, message: MqttMessage) {
                            handleIncoming(topic, message.payload)
                        }

                        override fun deliveryComplete(token: org.eclipse.paho.client.mqttv3.IMqttDeliveryToken?) {}
                    })
                    val opts = MqttConnectOptions().apply {
                        isCleanSession = true
                        isAutomaticReconnect = true
                        keepAliveInterval = 30
                        connectionTimeout = 10
                    }
                    c.connect(opts)
                    client = c
                    startPinger()
                    return@Thread
                } catch (e: Exception) {
                    lastError = e.message ?: e.javaClass.simpleName
                }
            }
            main.post { listener.onStatus(Status.DISCONNECTED, "Couldn't connect: $lastError") }
        }, "walkie-connect").start()
    }

    fun disconnect() {
        stopTalking()
        connected = false
        pingThread?.interrupt()
        pingThread = null
        val c = client
        client = null
        if (c != null) {
            Thread({
                try { c.disconnectForcibly(500, 500) } catch (_: Exception) {}
                try { c.close(true) } catch (_: Exception) {}
            }, "walkie-close").start()
        }
        main.removeCallbacks(rxIdleRunnable)
        receiving = false
        track?.let { t -> try { t.release() } catch (_: Exception) {} }
        track = null
        listener.onStatus(Status.DISCONNECTED, "Not connected")
    }

    val isConnected: Boolean get() = connected

    // ---------------------------------------------------------------- talking

    fun startTalking(): Boolean {
        if (!connected || !talking.compareAndSet(false, true)) return false
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
                while (talking.get() && connected) {
                    var off = 0
                    while (off < buf.size && talking.get()) {
                        val n = recorder.read(buf, off, buf.size - off)
                        if (n <= 0) break
                        off += n
                    }
                    if (off > 0) publish(audioTopic, seal(buf, off))
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
        val pcm = open(payload) ?: return // wrong PIN traffic, own echo, or garbage
        main.post { listener.onPeerSeen() }
        if (topic != audioTopic) return
        if (!receiving) {
            receiving = true
            main.post { listener.onReceiving(true) }
        }
        main.removeCallbacks(rxIdleRunnable)
        main.postDelayed(rxIdleRunnable, RX_IDLE_MS)
        try {
            playbackTrack().write(pcm, 0, pcm.size)
        } catch (_: Exception) {
        }
    }

    private fun playbackTrack(): AudioTrack {
        track?.let { if (it.state == AudioTrack.STATE_INITIALIZED) return it }
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
        track = t
        return t
    }

    // ---------------------------------------------------------------- plumbing

    private fun startPinger() {
        pingThread = Thread({
            try {
                while (connected) {
                    publishPresence()
                    Thread.sleep(PING_INTERVAL_MS)
                }
            } catch (_: InterruptedException) {
            }
        }, "walkie-ping").also { it.isDaemon = true; it.start() }
    }

    private fun publishPresence() {
        publish(presenceTopic, seal("PING".toByteArray(Charsets.UTF_8), 4))
    }

    private fun publish(topic: String, payload: ByteArray) {
        val c = client ?: return
        try {
            c.publish(topic, payload, 0, false)
        } catch (_: Exception) {
        }
    }

    /** Envelope: [version][senderId(8)][iv(16)][AES-256-CTR ciphertext]. */
    private fun seal(data: ByteArray, len: Int): ByteArray {
        val iv = ByteArray(16).also { random.nextBytes(it) }
        val cipher = Cipher.getInstance("AES/CTR/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key, IvParameterSpec(iv))
        val ct = cipher.doFinal(data, 0, len)
        return ByteArray(HEADER_BYTES + ct.size).also {
            it[0] = VERSION
            System.arraycopy(senderId, 0, it, 1, 8)
            System.arraycopy(iv, 0, it, 9, 16)
            System.arraycopy(ct, 0, it, HEADER_BYTES, ct.size)
        }
    }

    /** Returns plaintext, or null for own messages / malformed payloads. */
    private fun open(payload: ByteArray): ByteArray? {
        if (payload.size <= HEADER_BYTES || payload[0] != VERSION) return null
        var own = true
        for (i in 0 until 8) if (payload[1 + i] != senderId[i]) { own = false; break }
        if (own) return null
        return try {
            val iv = payload.copyOfRange(9, 25)
            val cipher = Cipher.getInstance("AES/CTR/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key, IvParameterSpec(iv))
            cipher.doFinal(payload, HEADER_BYTES, payload.size - HEADER_BYTES)
        } catch (_: Exception) {
            null
        }
    }
}
