package com.example.shrnk_it_mobile

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import java.io.File
import java.io.FileOutputStream

/** Encodes a separate cache file, with a bound on decoded memory use. */
object JpegCompressor {
    fun prepare(context: Context, uri: Uri, quality: Int, minimumSavings: Int): Pair<File, Long> {
        require(quality in 1..100 && minimumSavings in 0..100)
        val source = File.createTempFile("source-", ".jpg", context.cacheDir)
        val output = try { File.createTempFile("compressed-", ".jpg", context.cacheDir) } catch (error: Exception) { source.delete(); throw error }
        var success = false
        try {
            (context.contentResolver.openInputStream(uri) ?: error("Cannot read original")).use { input -> source.outputStream().use { input.copyTo(it) } }
            require(source.length() > 0) { "Original file is empty" }
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(source.absolutePath, bounds)
            require(bounds.outMimeType == "image/jpeg" && bounds.outWidth > 0 && bounds.outHeight > 0) { "Not a supported JPEG" }
            require(bounds.outWidth.toLong() * bounds.outHeight <= 16_000_000) { "Photo is too large for this prototype to process safely" }
            val bitmap = BitmapFactory.decodeFile(source.absolutePath) ?: error("Cannot decode photo")
            try {
                FileOutputStream(output).use { stream -> check(bitmap.compress(Bitmap.CompressFormat.JPEG, quality, stream)) { "JPEG encoding failed" }; stream.flush() }
            } finally { bitmap.recycle() }
            val inputExif = ExifInterface(source.absolutePath)
            val outputExif = ExifInterface(output.absolutePath)
            val tags = arrayOf(ExifInterface.TAG_ORIENTATION, ExifInterface.TAG_DATETIME, ExifInterface.TAG_DATETIME_ORIGINAL, ExifInterface.TAG_DATETIME_DIGITIZED, ExifInterface.TAG_MAKE, ExifInterface.TAG_MODEL)
            for (tag in tags) inputExif.getAttribute(tag)?.let { outputExif.setAttribute(tag, it) }
            outputExif.saveAttributes()
            check(output.length() > 0 && output.length() < source.length() && output.length().toDouble() <= source.length().toDouble() * (100 - minimumSavings) / 100.0) { "Compressed copy did not meet the savings threshold; original remains unchanged" }
            success = true
            return output to source.length()
        } finally {
            source.delete()
            if (!success) output.delete()
        }
    }
}
