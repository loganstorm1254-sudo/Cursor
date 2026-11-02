package com.tapshare.app.ui

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.LayoutInflater
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.tapshare.app.R
import com.tapshare.app.databinding.ActivityGalleryBinding
import com.tapshare.app.databinding.ItemPhotoBinding
import com.tapshare.app.gallery.GalleryItem
import com.tapshare.app.gallery.PhotoStore
import com.tapshare.app.nfc.NfcTapController
import com.tapshare.app.service.TapShareService
import com.tapshare.app.transfer.PeerHandshake
import com.tapshare.app.util.PeerIdentity
import com.tapshare.app.util.ShareSession
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class GalleryActivity : AppCompatActivity() {

    private lateinit var binding: ActivityGalleryBinding
    private var nfc: NfcTapController? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityGalleryBinding.inflate(layoutInflater)
        setContentView(binding.root)

        TapShareService.ensureRunning(this)
        handleIncomingShare(intent)

        binding.photoGrid.layoutManager = GridLayoutManager(this, 3)
        lifecycleScope.launch {
            val photos = withContext(Dispatchers.IO) { PhotoStore.loadImages(this@GalleryActivity) }
            if (photos.isEmpty()) {
                binding.emptyText.visibility = android.view.View.VISIBLE
                binding.photoGrid.visibility = android.view.View.GONE
            } else {
                binding.emptyText.visibility = android.view.View.GONE
                binding.photoGrid.adapter = PhotoAdapter(photos) { openViewer(it) }
            }
        }

        nfc = NfcTapController(this) { peer -> onPeerTapped(peer) }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIncomingShare(intent)
    }

    override fun onResume() {
        super.onResume()
        val controller = nfc ?: return
        if (!controller.isAvailable() || !controller.isEnabled()) {
            Toast.makeText(this, R.string.nfc_required, Toast.LENGTH_LONG).show()
        } else {
            controller.start()
        }
    }

    override fun onPause() {
        nfc?.stop()
        super.onPause()
    }

    private fun handleIncomingShare(intent: Intent?) {
        if (intent == null) return
        val uri = when (intent.action) {
            Intent.ACTION_SEND -> intent.getParcelableExtraCompat(Intent.EXTRA_STREAM)
            Intent.ACTION_VIEW -> intent.data
            else -> null
        } ?: return
        val mime = intent.type ?: contentResolver.getType(uri) ?: "image/jpeg"
        val name = uri.lastPathSegment ?: "shared.jpg"
        ShareSession.set(ShareSession.ActiveMedia(uri, mime, name))
        openViewer(
            GalleryItem(
                id = -1,
                uri = uri,
                mimeType = mime,
                displayName = name,
                dateAdded = System.currentTimeMillis() / 1000
            )
        )
    }

    private fun openViewer(item: GalleryItem) {
        ShareSession.set(
            ShareSession.ActiveMedia(item.uri, item.mimeType, item.displayName)
        )
        startActivity(
            Intent(this, PhotoViewerActivity::class.java).apply {
                putExtra(PhotoViewerActivity.EXTRA_URI, item.uri.toString())
                putExtra(PhotoViewerActivity.EXTRA_MIME, item.mimeType)
                putExtra(PhotoViewerActivity.EXTRA_NAME, item.displayName)
            }
        )
    }

    private fun onPeerTapped(peer: PeerHandshake) {
        if (peer.peerId == PeerIdentity.id(this)) return
        val media = ShareSession.get()
        if (media == null) {
            Toast.makeText(this, R.string.no_photo, Toast.LENGTH_SHORT).show()
            return
        }
        startActivity(
            Intent(this, TapAnimationActivity::class.java).apply {
                putExtra(TapAnimationActivity.EXTRA_MODE, TapAnimationActivity.MODE_SEND)
                putExtra(TapAnimationActivity.EXTRA_URI, media.uri.toString())
                putExtra(TapAnimationActivity.EXTRA_MIME, media.mimeType)
                putExtra(TapAnimationActivity.EXTRA_PEER_BT, peer.bluetoothAddress)
                putExtra(TapAnimationActivity.EXTRA_PEER_ID, peer.peerId)
                putExtra(TapAnimationActivity.EXTRA_PEER_NAME, peer.displayName)
            }
        )
    }

    private class PhotoAdapter(
        private val items: List<GalleryItem>,
        private val onClick: (GalleryItem) -> Unit
    ) : RecyclerView.Adapter<PhotoAdapter.Holder>() {

        class Holder(val binding: ItemPhotoBinding) : RecyclerView.ViewHolder(binding.root)

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): Holder {
            val binding = ItemPhotoBinding.inflate(LayoutInflater.from(parent.context), parent, false)
            return Holder(binding)
        }

        override fun getItemCount(): Int = items.size

        override fun onBindViewHolder(holder: Holder, position: Int) {
            val item = items[position]
            holder.binding.thumb.setImageURI(item.uri)
            holder.binding.thumb.scaleType = ImageView.ScaleType.CENTER_CROP
            holder.binding.root.setOnClickListener { onClick(item) }
        }
    }
}

@Suppress("DEPRECATION")
private fun Intent.getParcelableExtraCompat(key: String): Uri? {
    return if (android.os.Build.VERSION.SDK_INT >= 33) {
        getParcelableExtra(key, Uri::class.java)
    } else {
        getParcelableExtra(key) as? Uri
    }
}
