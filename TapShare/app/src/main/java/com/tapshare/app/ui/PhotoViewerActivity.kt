package com.tapshare.app.ui

import android.net.Uri
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.tapshare.app.databinding.ActivityPhotoViewerBinding
import com.tapshare.app.service.TapShareService
import com.tapshare.app.util.ShareSession

/**
 * Optional in-app viewer. Sharing is done by physically tapping phone tops —
 * handled by TapShareService + GalleryWatchService, not a Share button.
 */
class PhotoViewerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPhotoViewerBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPhotoViewerBinding.inflate(layoutInflater)
        setContentView(binding.root)

        TapShareService.ensureRunning(this)

        val uri = intent.getStringExtra(EXTRA_URI)?.let(Uri::parse)
        val mime = intent.getStringExtra(EXTRA_MIME) ?: "image/jpeg"
        val name = intent.getStringExtra(EXTRA_NAME) ?: "photo.jpg"
        if (uri == null) {
            finish()
            return
        }
        try {
            binding.photoView.setImageURI(uri)
        } catch (_: Exception) {
            finish()
            return
        }
        ShareSession.set(ShareSession.ActiveMedia(uri, mime, name))
        binding.tapHint.text = getString(com.tapshare.app.R.string.tap_phones_now)
        // No click-to-share — physical tap only (service accelerometer).
        binding.tapHint.isClickable = false
        binding.tapHint.isFocusable = false
    }

    override fun onResume() {
        super.onResume()
        intent.getStringExtra(EXTRA_URI)?.let { raw ->
            val uri = Uri.parse(raw)
            ShareSession.set(
                ShareSession.ActiveMedia(
                    uri,
                    intent.getStringExtra(EXTRA_MIME) ?: "image/jpeg",
                    intent.getStringExtra(EXTRA_NAME) ?: "photo.jpg"
                )
            )
        }
        TapShareService.ensureRunning(this)
    }

    override fun onDestroy() {
        if (isFinishing) {
            // Keep session briefly so an in-flight tap can still read it.
        }
        super.onDestroy()
    }

    companion object {
        const val EXTRA_URI = "uri"
        const val EXTRA_MIME = "mime"
        const val EXTRA_NAME = "name"
    }
}
