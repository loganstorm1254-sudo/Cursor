package com.tapshare.app.util

import android.net.Uri
import java.util.concurrent.atomic.AtomicReference

/**
 * Holds the photo currently on screen so a top-of-phone tap can share it.
 * Written by Gallery / PhotoViewer; read by the NFC + transfer pipeline.
 */
object ShareSession {
    data class ActiveMedia(
        val uri: Uri,
        val mimeType: String,
        val displayName: String
    )

    private val current = AtomicReference<ActiveMedia?>(null)

    fun set(media: ActiveMedia?) {
        current.set(media)
    }

    fun get(): ActiveMedia? = current.get()

    fun clear() {
        current.set(null)
    }
}
