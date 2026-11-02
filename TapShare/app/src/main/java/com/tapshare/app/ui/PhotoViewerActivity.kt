package com.tapshare.app.ui

import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.tapshare.app.R
import com.tapshare.app.databinding.ActivityPhotoViewerBinding
import com.tapshare.app.service.TapShareService
import com.tapshare.app.transfer.BumpDetector
import com.tapshare.app.util.ShareSession

/**
 * Full-screen photo. Detects a physical top-tap via accelerometer, then hands
 * off to Bluetooth discovery + transfer. Share button is a reliable backup.
 */
class PhotoViewerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPhotoViewerBinding
    private var uri: Uri? = null
    private var mime: String = "image/jpeg"
    private var name: String = "photo.jpg"
    private var bumpDetector: BumpDetector? = null
    private var sharing = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPhotoViewerBinding.inflate(layoutInflater)
        setContentView(binding.root)

        TapShareService.ensureRunning(this)

        uri = intent.getStringExtra(EXTRA_URI)?.let(Uri::parse)
        mime = intent.getStringExtra(EXTRA_MIME) ?: "image/jpeg"
        name = intent.getStringExtra(EXTRA_NAME) ?: "photo.jpg"
        val mediaUri = uri
        if (mediaUri == null) {
            finish()
            return
        }
        try {
            binding.photoView.setImageURI(mediaUri)
        } catch (_: Exception) {
            Toast.makeText(this, R.string.pairing_failed, Toast.LENGTH_SHORT).show()
            finish()
            return
        }
        ShareSession.set(ShareSession.ActiveMedia(mediaUri, mime, name))
        TapShareService.refreshBeacon(this)

        binding.tapHint.setOnClickListener { beginShare() }
        bumpDetector = BumpDetector(this) {
            runOnUiThread { beginShare() }
        }
    }

    override fun onResume() {
        super.onResume()
        uri?.let {
            ShareSession.set(ShareSession.ActiveMedia(it, mime, name))
            TapShareService.refreshBeacon(this)
        }
        ensureBluetoothOn()
        bumpDetector?.start()
    }

    override fun onPause() {
        bumpDetector?.stop()
        super.onPause()
    }

    override fun onDestroy() {
        bumpDetector?.stop()
        bumpDetector = null
        super.onDestroy()
    }

    private fun ensureBluetoothOn() {
        val adapter = getSystemService(BluetoothManager::class.java)?.adapter
        if (adapter == null) {
            Toast.makeText(this, R.string.no_bluetooth, Toast.LENGTH_LONG).show()
            return
        }
        if (!adapter.isEnabled) {
            try {
                @Suppress("DEPRECATION")
                startActivity(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
            } catch (_: Exception) {
            }
            Toast.makeText(this, R.string.turn_on_bluetooth, Toast.LENGTH_LONG).show()
        }
    }

    private fun beginShare() {
        if (sharing) return
        val mediaUri = uri ?: return
        ShareSession.set(ShareSession.ActiveMedia(mediaUri, mime, name))
        TapShareService.refreshBeacon(this)
        sharing = true
        startActivity(
            Intent(this, TapAnimationActivity::class.java).apply {
                putExtra(TapAnimationActivity.EXTRA_MODE, TapAnimationActivity.MODE_SEND)
                putExtra(TapAnimationActivity.EXTRA_URI, mediaUri.toString())
                putExtra(TapAnimationActivity.EXTRA_MIME, mime)
            }
        )
        binding.root.postDelayed({ sharing = false }, 2500)
    }

    companion object {
        const val EXTRA_URI = "uri"
        const val EXTRA_MIME = "mime"
        const val EXTRA_NAME = "name"
    }
}
