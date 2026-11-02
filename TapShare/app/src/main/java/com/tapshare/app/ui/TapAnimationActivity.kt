package com.tapshare.app.ui

import android.animation.AnimatorSet
import android.animation.ObjectAnimator
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.view.View
import android.view.animation.DecelerateInterpolator
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.tapshare.app.R
import com.tapshare.app.databinding.ActivityTapAnimationBinding
import com.tapshare.app.transfer.MediaPipe
import com.tapshare.app.util.ShareSession
import kotlinx.coroutines.launch

/**
 * Apple NameDrop-style expanding rings while the photo transfers over Bluetooth.
 */
class TapAnimationActivity : AppCompatActivity() {

    private lateinit var binding: ActivityTapAnimationBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityTapAnimationBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val mode = intent.getStringExtra(EXTRA_MODE) ?: MODE_SEND
        val uri = intent.getStringExtra(EXTRA_URI)?.let(Uri::parse)
        val mime = intent.getStringExtra(EXTRA_MIME) ?: "image/jpeg"
        val peerBt = intent.getStringExtra(EXTRA_PEER_BT).orEmpty()
        val peerId = intent.getStringExtra(EXTRA_PEER_ID).orEmpty()
        val peerName = intent.getStringExtra(EXTRA_PEER_NAME).orEmpty()

        if (uri != null) {
            binding.preview.setImageURI(uri)
        }

        binding.label.text = when (mode) {
            MODE_RECEIVE -> getString(R.string.receiving)
            else -> getString(R.string.sharing) + if (peerName.isNotBlank()) " → $peerName" else ""
        }

        vibrateTap()
        playRings()

        if (mode == MODE_SEND) {
            if (uri == null || (peerId.isBlank() && peerBt.isBlank())) {
                Toast.makeText(this, R.string.pairing_failed, Toast.LENGTH_LONG).show()
                finish()
                return
            }
            val media = ShareSession.ActiveMedia(
                uri = uri,
                mimeType = mime,
                displayName = uri.lastPathSegment ?: "photo.jpg"
            )
            lifecycleScope.launch {
                val ok = MediaPipe(applicationContext).sendTo(peerId, peerBt, media)
                binding.label.setText(if (ok) R.string.shared else R.string.pairing_failed)
                binding.root.postDelayed({ finish() }, if (ok) 900L else 1400L)
            }
        } else {
            // Receive path — show animation, then open the photo full screen.
            binding.root.postDelayed({
                if (uri != null) {
                    startActivity(
                        Intent(this, ReceivedMediaActivity::class.java).apply {
                            putExtra(ReceivedMediaActivity.EXTRA_URI, uri.toString())
                            putExtra(ReceivedMediaActivity.EXTRA_MIME, mime)
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                        }
                    )
                }
                finish()
            }, 1600L)
        }
    }

    private fun playRings() {
        listOf(binding.ring1 to 0L, binding.ring2 to 180L, binding.ring3 to 360L).forEach { (ring, delay) ->
            expand(ring, delay)
        }
        ObjectAnimator.ofFloat(binding.preview, View.SCALE_X, 0.6f, 1f).apply {
            duration = 700
            start()
        }
        ObjectAnimator.ofFloat(binding.preview, View.SCALE_Y, 0.6f, 1f).apply {
            duration = 700
            start()
        }
        ObjectAnimator.ofFloat(binding.preview, View.ALPHA, 0f, 1f).apply {
            duration = 500
            start()
        }
    }

    private fun expand(ring: View, startDelay: Long) {
        ring.scaleX = 0.4f
        ring.scaleY = 0.4f
        ring.alpha = 0.9f
        val set = AnimatorSet()
        set.playTogether(
            ObjectAnimator.ofFloat(ring, View.SCALE_X, 0.4f, 3.2f),
            ObjectAnimator.ofFloat(ring, View.SCALE_Y, 0.4f, 3.2f),
            ObjectAnimator.ofFloat(ring, View.ALPHA, 0.9f, 0f)
        )
        set.duration = 1400
        set.startDelay = startDelay
        set.interpolator = DecelerateInterpolator()
        set.start()
        // Loop soft pulses
        ring.postDelayed({ if (!isFinishing) expand(ring, 0L) }, 1500 + startDelay)
    }

    private fun vibrateTap() {
        try {
            val vibrator = if (android.os.Build.VERSION.SDK_INT >= 31) {
                getSystemService(VibratorManager::class.java).defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                getSystemService(VIBRATOR_SERVICE) as Vibrator
            }
            vibrator.vibrate(
                VibrationEffect.createWaveform(longArrayOf(0, 40, 60, 40), -1)
            )
        } catch (_: Exception) {
        }
    }

    companion object {
        const val EXTRA_MODE = "mode"
        const val EXTRA_URI = "uri"
        const val EXTRA_MIME = "mime"
        const val EXTRA_PEER_BT = "peer_bt"
        const val EXTRA_PEER_ID = "peer_id"
        const val EXTRA_PEER_NAME = "peer_name"
        const val MODE_SEND = "send"
        const val MODE_RECEIVE = "receive"
    }
}
