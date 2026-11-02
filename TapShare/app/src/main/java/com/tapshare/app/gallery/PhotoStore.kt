package com.tapshare.app.gallery

import android.content.ContentUris
import android.content.Context
import android.net.Uri
import android.os.Build
import android.provider.MediaStore

data class GalleryItem(
    val id: Long,
    val uri: Uri,
    val mimeType: String,
    val displayName: String,
    val dateAdded: Long
)

object PhotoStore {
    fun loadImages(context: Context, limit: Int = 400): List<GalleryItem> {
        val items = mutableListOf<GalleryItem>()
        val collection = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL)
        } else {
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI
        }
        val projection = arrayOf(
            MediaStore.Images.Media._ID,
            MediaStore.Images.Media.DISPLAY_NAME,
            MediaStore.Images.Media.MIME_TYPE,
            MediaStore.Images.Media.DATE_ADDED
        )
        val sort = "${MediaStore.Images.Media.DATE_ADDED} DESC"
        context.contentResolver.query(collection, projection, null, null, sort)?.use { cursor ->
            val idCol = cursor.getColumnIndexOrThrow(MediaStore.Images.Media._ID)
            val nameCol = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DISPLAY_NAME)
            val mimeCol = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.MIME_TYPE)
            val dateCol = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DATE_ADDED)
            var count = 0
            while (cursor.moveToNext() && count < limit) {
                val id = cursor.getLong(idCol)
                items += GalleryItem(
                    id = id,
                    uri = ContentUris.withAppendedId(collection, id),
                    mimeType = cursor.getString(mimeCol) ?: "image/jpeg",
                    displayName = cursor.getString(nameCol) ?: "photo_$id.jpg",
                    dateAdded = cursor.getLong(dateCol)
                )
                count++
            }
        }
        return items
    }
}
