package com.tapshare.app.ui

import android.net.Uri
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.tapshare.app.databinding.ActivityReceivedBinding

/** Opens a just-received photo full screen on the receiving phone. */
class ReceivedMediaActivity : AppCompatActivity() {

    private lateinit var binding: ActivityReceivedBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityReceivedBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val uri = intent.getStringExtra(EXTRA_URI)?.let(Uri::parse)
        if (uri == null) {
            finish()
            return
        }
        binding.receivedImage.setImageURI(uri)
        binding.receivedImage.alpha = 0f
        binding.receivedImage.animate().alpha(1f).setDuration(500).start()
        binding.root.setOnClickListener { finish() }
    }

    companion object {
        const val EXTRA_URI = "uri"
        const val EXTRA_MIME = "mime"
    }
}
