package com.tapshare.app.transfer

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import java.io.File
import java.io.FileOutputStream

object MediaSaver {
    private const val TAG = "TapShareSaver"

    fun persist(context: Context, bytes: ByteArray, mime: String, displayName: String): Uri? {
        return try {
            val isVideo = mime.startsWith("video/")
            val safeName = displayName.replace(Regex("[^A-Za-z0-9._-]"), "_")
                .ifBlank { if (isVideo) "tapshare.mp4" else "tapshare.jpg" }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val collection = if (isVideo) {
                    MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
                } else {
                    MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
                }
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, safeName)
                    put(MediaStore.MediaColumns.MIME_TYPE, mime)
                    put(
                        MediaStore.MediaColumns.RELATIVE_PATH,
                        if (isVideo) Environment.DIRECTORY_MOVIES + "/TapShare"
                        else Environment.DIRECTORY_PICTURES + "/TapShare"
                    )
                    put(MediaStore.MediaColumns.IS_PENDING, 1)
                }
                val resolver = context.contentResolver
                val uri = resolver.insert(collection, values) ?: return cacheFallback(context, bytes)
                resolver.openOutputStream(uri)?.use { it.write(bytes) }
                    ?: return cacheFallback(context, bytes)
                values.clear()
                values.put(MediaStore.MediaColumns.IS_PENDING, 0)
                resolver.update(uri, values, null, null)
                return uri
            }

            val dir = File(
                Environment.getExternalStoragePublicDirectory(
                    if (isVideo) Environment.DIRECTORY_MOVIES else Environment.DIRECTORY_PICTURES
                ),
                "TapShare"
            )
            if (!dir.exists()) dir.mkdirs()
            val file = File(dir, safeName)
            FileOutputStream(file).use { it.write(bytes) }
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DATA, file.absolutePath)
                put(MediaStore.MediaColumns.MIME_TYPE, mime)
                put(MediaStore.MediaColumns.DISPLAY_NAME, safeName)
            }
            context.contentResolver.insert(
                if (isVideo) MediaStore.Video.Media.EXTERNAL_CONTENT_URI
                else MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                values
            ) ?: Uri.fromFile(file)
        } catch (t: Throwable) {
            Log.e(TAG, "persist failed", t)
            cacheFallback(context, bytes)
        }
    }

    private fun cacheFallback(context: Context, bytes: ByteArray): Uri? {
        return try {
            val file = File(context.cacheDir, "recv_${System.currentTimeMillis()}.bin")
            FileOutputStream(file).use { it.write(bytes) }
            Uri.fromFile(file)
        } catch (_: Exception) {
            null
        }
    }
}
