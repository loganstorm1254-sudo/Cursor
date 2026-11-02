package com.tapshare.app.ui

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.tapshare.app.R
import com.tapshare.app.databinding.ActivityPhotoViewerBinding
import com.tapshare.app.nfc.NfcTapController
import com.tapshare.app.service.TapShareService
import com.tapshare.app.transfer.PeerHandshake
import com.tapshare.app.util.PeerIdentity
import com.tapshare.app.util.ShareSession

/**
 * Full-screen photo. NFC reader stays hot here — tap tops with another TapShare
 * phone to fire the NameDrop-style animation and send the file.
 */
class PhotoViewerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPhotoViewerBinding
    private var nfc: NfcTapController? = null
    private var uri: Uri? = null
    private var mime: String = "image/jpeg"
    private var name: String = "photo.jpg"

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
        binding.photoView.setImageURI(mediaUri)
        ShareSession.set(ShareSession.ActiveMedia(mediaUri, mime, name))

        nfc = NfcTapController(this) { peer -> onPeerTapped(peer) }
    }

    override fun onResume() {
        super.onResume()
        uri?.let {
            ShareSession.set(ShareSession.ActiveMedia(it, mime, name))
        }
        val controller = nfc ?: return
        if (!controller.isEnabled()) {
            Toast.makeText(this, R.string.nfc_required, Toast.LENGTH_LONG).show()
        } else {
            controller.start()
        }
    }

    override fun onPause() {
        nfc?.stop()
        super.onPause()
    }

    override fun onDestroy() {
        // Keep session while animation runs; clear only if finishing without share.
        if (isFinishing) {
            // Don't clear if TapAnimation is about to use it — animation copies extras.
        }
        super.onDestroy()
    }

    private fun onPeerTapped(peer: PeerHandshake) {
        if (peer.peerId == PeerIdentity.id(this)) return
        val mediaUri = uri ?: return
        startActivity(
            Intent(this, TapAnimationActivity::class.java).apply {
                putExtra(TapAnimationActivity.EXTRA_MODE, TapAnimationActivity.MODE_SEND)
                putExtra(TapAnimationActivity.EXTRA_URI, mediaUri.toString())
                putExtra(TapAnimationActivity.EXTRA_MIME, mime)
                putExtra(TapAnimationActivity.EXTRA_PEER_BT, peer.bluetoothAddress)
                putExtra(TapAnimationActivity.EXTRA_PEER_ID, peer.peerId)
                putExtra(TapAnimationActivity.EXTRA_PEER_NAME, peer.displayName)
            }
        )
    }

    companion object {
        const val EXTRA_URI = "uri"
        const val EXTRA_MIME = "mime"
        const val EXTRA_NAME = "name"
    }
}
