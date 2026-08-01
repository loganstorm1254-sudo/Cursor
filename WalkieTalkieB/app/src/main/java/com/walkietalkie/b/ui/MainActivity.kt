package com.walkietalkie.b.ui

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Bundle
import android.view.MotionEvent
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.walkietalkie.b.R
import com.walkietalkie.b.databinding.ActivityMainBinding
import com.walkietalkie.b.net.WalkieEngine

class MainActivity : AppCompatActivity(), WalkieEngine.Listener {

    private lateinit var binding: ActivityMainBinding
    private lateinit var engine: WalkieEngine
    private var peerOnline = false

    private val clearPeerRunnable = Runnable {
        peerOnline = false
        refreshStatusLine()
    }

    private val micPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) connect()
        else binding.statusText.text = getString(R.string.mic_permission_needed)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        engine = WalkieEngine(this)
        volumeControlStream = AudioManager.STREAM_MUSIC

        binding.pinInput.setText(
            getPreferences(MODE_PRIVATE).getString("pin", "") ?: ""
        )

        binding.connectButton.setOnClickListener {
            if (engine.isBusy) {
                engine.disconnect()
            } else if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED
            ) {
                connect()
            } else {
                micPermission.launch(Manifest.permission.RECORD_AUDIO)
            }
        }

        setupTalkButton()
        onStatus(WalkieEngine.Status.DISCONNECTED, getString(R.string.not_connected))
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun setupTalkButton() {
        binding.talkButton.setOnTouchListener { v, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    if (engine.startTalking()) {
                        beep(ToneGenerator.TONE_PROP_ACK)
                        v.isPressed = true
                        binding.talkButton.text = getString(R.string.talking)
                    }
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    engine.stopTalking()
                    v.isPressed = false
                    binding.talkButton.text = getString(R.string.hold_to_talk)
                    if (event.actionMasked == MotionEvent.ACTION_UP) v.performClick()
                    true
                }
                else -> false
            }
        }
    }

    private fun connect() {
        val pin = binding.pinInput.text?.toString()?.trim() ?: ""
        if (pin.length < 4) {
            binding.pinLayout.error = getString(R.string.pin_too_short)
            return
        }
        binding.pinLayout.error = null
        getPreferences(MODE_PRIVATE).edit().putString("pin", pin).apply()
        currentFocus?.let {
            (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager)
                .hideSoftInputFromWindow(it.windowToken, 0)
        }
        engine.connect(pin)
    }

    // ------------------------------------------------------- engine callbacks

    override fun onStatus(status: WalkieEngine.Status, detail: String) {
        val connected = status == WalkieEngine.Status.CONNECTED
        binding.connectButton.text = getString(
            when (status) {
                WalkieEngine.Status.CONNECTED -> R.string.disconnect
                WalkieEngine.Status.CONNECTING -> R.string.cancel
                WalkieEngine.Status.DISCONNECTED -> R.string.connect
            }
        )
        binding.pinInput.isEnabled = status == WalkieEngine.Status.DISCONNECTED
        binding.talkButton.isEnabled = connected
        binding.talkButton.alpha = if (connected) 1f else 0.4f
        binding.statusText.text = detail
        if (connected) {
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            peerOnline = false
        }
        refreshStatusLine()
    }

    override fun onPeerSeen() {
        val firstSeen = !peerOnline
        peerOnline = true
        binding.root.removeCallbacks(clearPeerRunnable)
        binding.root.postDelayed(clearPeerRunnable, 30_000)
        if (firstSeen) refreshStatusLine()
    }

    override fun onReceiving(receiving: Boolean) {
        binding.receivingText.text =
            getString(if (receiving) R.string.receiving else R.string.idle)
        binding.receivingDot.isActivated = receiving
        if (!receiving) beep(ToneGenerator.TONE_PROP_BEEP)
    }

    private fun refreshStatusLine() {
        binding.peerText.text = getString(
            when {
                !engine.isConnected -> R.string.peer_unknown
                peerOnline -> R.string.peer_online
                else -> R.string.peer_waiting
            }
        )
    }

    private fun beep(tone: Int) {
        try {
            val tg = ToneGenerator(AudioManager.STREAM_MUSIC, 60)
            tg.startTone(tone, 120)
            binding.root.postDelayed({ tg.release() }, 250)
        } catch (_: Exception) {
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        engine.disconnect()
    }
}
