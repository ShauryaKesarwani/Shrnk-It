package com.example.shrnk_it_mobile

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import android.net.Uri
import java.io.ByteArrayOutputStream
import java.io.File

/** Extracts comparable frames without modifying either input. */
object PreviewFrames {
    fun read(context: Context, uri: Uri): ByteArray {
        val retriever = MediaMetadataRetriever()
        try {
            retriever.setDataSource(context, uri)
            val frame = retriever.getFrameAtTime(1_000_000, MediaMetadataRetriever.OPTION_CLOSEST_SYNC)
                ?: retriever.getFrameAtTime(0) ?: error("No preview frame available")
            val scale = minOf(1.0, 640.0 / frame.width.coerceAtLeast(1))
            val small = Bitmap.createScaledBitmap(frame, (frame.width * scale).toInt().coerceAtLeast(1), (frame.height * scale).toInt().coerceAtLeast(1), true)
            val bytes = ByteArrayOutputStream()
            small.compress(Bitmap.CompressFormat.JPEG, 85, bytes)
            if (small !== frame) small.recycle()
            frame.recycle()
            return bytes.toByteArray()
        } finally { retriever.release() }
    }
    fun read(context: Context, file: File): ByteArray = read(context, Uri.fromFile(file))
}
