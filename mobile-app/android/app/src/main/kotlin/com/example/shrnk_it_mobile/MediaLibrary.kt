package com.example.shrnk_it_mobile

import android.content.ContentUris
import android.content.Context
import android.os.Build
import android.provider.MediaStore

/** Queries Android's indexed local media without modifying any files. */
object MediaLibrary {
    fun list(context: Context): List<Map<String, Any>> {
        val collection = MediaStore.Files.getContentUri("external")
        val columns = mutableListOf(MediaStore.Files.FileColumns._ID, MediaStore.Files.FileColumns.DISPLAY_NAME, MediaStore.Files.FileColumns.SIZE, MediaStore.Files.FileColumns.MIME_TYPE)
        if (Build.VERSION.SDK_INT >= 29) columns.add(MediaStore.Files.FileColumns.RELATIVE_PATH)
        val selection = "(${MediaStore.Files.FileColumns.MEDIA_TYPE} = ? OR (${MediaStore.Files.FileColumns.MEDIA_TYPE} = ? AND ${MediaStore.Files.FileColumns.MIME_TYPE} = ?))"
        val args = arrayOf(MediaStore.Files.FileColumns.MEDIA_TYPE_VIDEO.toString(), MediaStore.Files.FileColumns.MEDIA_TYPE_IMAGE.toString(), "image/jpeg")
        val entries = mutableListOf<Map<String, Any>>()
        context.contentResolver.query(collection, columns.toTypedArray(), selection, args, null)?.use { cursor ->
            val id = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns._ID)
            val name = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns.DISPLAY_NAME)
            val size = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns.SIZE)
            val type = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns.MIME_TYPE)
            val folder = if (Build.VERSION.SDK_INT >= 29) cursor.getColumnIndex(MediaStore.Files.FileColumns.RELATIVE_PATH) else -1
            while (cursor.moveToNext()) {
                val uri = ContentUris.withAppendedId(collection, cursor.getLong(id))
                entries.add(mapOf("uri" to uri.toString(), "name" to (cursor.getString(name) ?: "Media"), "size" to (if (cursor.isNull(size)) 0L else cursor.getLong(size)), "type" to (cursor.getString(type) ?: ""), "folder" to (if (folder >= 0) cursor.getString(folder) ?: "" else "")))
            }
        } ?: error("Android media library is unavailable")
        return entries
    }
}
