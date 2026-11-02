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
import com.tapshare.app.service.TapShareService
import com.tapshare.app.transfer.BleBeacon
import com.tapshare.app.transfer.MediaPipe
import com.tapshare.app.util.ShareSession
import kotlinx.coroutines.launch

/**
 * Expanding rings while Bluetooth finds the other phone and transfers the photo.
 */
class TapAnimationActivity : AppCompatActivity() {

    private lateinit var binding: ActivityTapAnimationBinding
    private var finished = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityTapAnimationBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val mode = intent.getStringExtra(EXTRA_MODE) ?: MODE_SEND
        val uri = intent.getStringExtra(EXTRA_URI)?.let(Uri::parse)
        val mime = intent.getStringExtra(EXTRA_MIME) ?: "image/jpeg"

        if (uri != null) {
            try {
                binding.preview.setImageURI(uri)
            } catch (_: Exception) {
            }
        }

        binding.label.text = when (mode) {
            MODE_RECEIVE -> getString(R.string.receiving)
            else -> getString(R.string.sharing_bluetooth)
        }

        vibrateTap()
        playRings()

        if (mode == MODE_SEND) {
            if (uri == null) {
                Toast.makeText(this, R.string.pairing_failed, Toast.LENGTH_LONG).show()
                finishSafe()
                return
            }
            val media = ShareSession.ActiveMedia(
                uri = uri,
                mimeType = mime,
                displayName = uri.lastPathSegment ?: "photo.jpg"
            )
            ShareSession.set(media)
            TapShareService.refreshBeacon(this)

            lifecycleScope.launch {
                val beacon = BleBeacon(applicationContext)
                beacon.signalBump()
                val ok = try {
                    MediaPipe(applicationContext).sendAfterTap(media, beacon)
                } catch (_: Exception) {
                    false
                }
                if (isFinishing || finished) return@launch
                binding.label.setText(if (ok) R.string.shared else R.string.pairing_failed)
                if (!ok) {
                    Toast.makeText(
                        this@TapAnimationActivity,
                        R.string.bluetooth_retry_hint,
                        Toast.LENGTH_LONG
                    ).show()
                }
                binding.root.postDelayed({ finishSafe() }, if (ok) 800L else 1600L)
            }
        } else {
            binding.root.postDelayed({
                if (uri != null) {
                    try {
                        startActivity(
                            Intent(this, ReceivedMediaActivity::class.java).apply {
                                putExtra(ReceivedMediaActivity.EXTRA_URI, uri.toString())
                                putExtra(ReceivedMediaActivity.EXTRA_MIME, mime)
                                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                            }
                        )
                    } catch (_: Exception) {
                    }
                }
                finishSafe()
            }, 1400L)
        }
    }

    private fun finishSafe() {
        if (finished || isFinishing) return
        finished = true
        finish()
    }

    private fun playRings() {
        listOf(binding.ring1 to 0L, binding.ring2 to 180L, binding.ring3 to 360L).forEach { (ring, delay) ->
            expand(ring, delay)
        }
        ObjectAnimator.ofFloat(binding.preview, View.SCALE_X, 0.6f, 1f).setDuration(700).start()
        ObjectAnimator.ofFloat(binding.preview, View.SCALE_Y, 0.6f, 1f).setDuration(700).start()
        ObjectAnimator.ofFloat(binding.preview, View.ALPHA, 0f, 1f).setDuration(500).start()
    }

    private fun expand(ring: View, startDelay: Long) {
        if (finished || isFinishing) return
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
        ring.postDelayed({ if (!finished && !isFinishing) expand(ring, 0L) }, 1500 + startDelay)
    }

    private fun vibrateTap() {
        try {
            val vibrator = if (android.os.Build.VERSION.SDK_INT >= 31) {
                getSystemService(VibratorManager::class.java).defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                getSystemService(VIBRATOR_SERVICE) as Vibrator
            }
            vibrator.vibrate(VibrationEffect.createWaveform(longArrayOf(0, 40, 60, 40), -1))
        } catch (_: Exception) {
        }
    }

    companion object {
        const val EXTRA_MODE = "mode"
        const val EXTRA_URI = "uri"
        const val EXTRA_MIME = "mime"
        const val EXTRA_REASON = "reason"
        const val MODE_SEND = "send"
        const val MODE_RECEIVE = "receive"
    }
}
