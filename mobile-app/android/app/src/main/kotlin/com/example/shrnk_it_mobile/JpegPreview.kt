package com.example.shrnk_it_mobile

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import java.io.ByteArrayOutputStream

/** Generate a memory-bounded visual comparison; no file is modified. */
object JpegPreview {
    fun create(context: Context, uri: Uri, quality: Int): Map<String, Any> {
        require(quality in 1..100) { "JPEG quality must be between 1 and 100" }
        val resolver = context.contentResolver
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        (resolver.openInputStream(uri) ?: error("Cannot read photo")).use { BitmapFactory.decodeStream(it, null, bounds) }
        require(bounds.outWidth > 0 && bounds.outHeight > 0) { "Could not read JPEG dimensions" }
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / sample > 2048) sample *= 2
        val options = BitmapFactory.Options().apply { inSampleSize = sample }
        val bitmap = (resolver.openInputStream(uri) ?: error("Cannot read photo")).use { BitmapFactory.decodeStream(it, null, options) } ?: error("Cannot decode photo")
        try {
            fun encode(q: Int): ByteArray {
                val out = ByteArrayOutputStream()
                check(bitmap.compress(Bitmap.CompressFormat.JPEG, q, out)) { "JPEG encoding failed" }
                return out.toByteArray()
            }
            val original = encode(100)
            val output = encode(quality)
            return mapOf("originalFrame" to original, "outputFrame" to output, "sampleBytes" to output.size, "sampled" to (sample > 1))
        } finally { bitmap.recycle() }
    }
}
