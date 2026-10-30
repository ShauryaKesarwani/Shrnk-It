package com.example.shrnk_it_mobile

import android.content.Context
import android.net.Uri
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.util.UnstableApi
import androidx.media3.transformer.Composition
import androidx.media3.transformer.EditedMediaItem
import androidx.media3.transformer.ExportException
import androidx.media3.transformer.ExportResult
import androidx.media3.transformer.Transformer
import androidx.media3.transformer.DefaultEncoderFactory
import androidx.media3.transformer.VideoEncoderSettings
import java.io.File

/** Produces a disposable sample in app cache; never writes to the original URI. */
@UnstableApi
class VideoPreview(private val context: Context) {
    private var transformer: Transformer? = null

    fun start(uri: Uri, useHevc: Boolean, sample: Boolean = true, bitrate: Int = 3_000_000, complete: (Result<File>) -> Unit) {
        if (transformer != null) {
            complete(Result.failure(IllegalStateException("A preview is already running")))
            return
        }
        val output = try {
            File.createTempFile("preview-", ".mp4", context.cacheDir)
        } catch (error: Exception) {
            complete(Result.failure(error))
            return
        }
        // Transformer expects a path which does not already exist.
        if (!output.delete()) {
            complete(Result.failure(IllegalStateException("Cannot prepare preview file")))
            return
        }
        try {
            val sourceBuilder = MediaItem.Builder().setUri(uri)
            if (sample) sourceBuilder.setClippingConfiguration(MediaItem.ClippingConfiguration.Builder().setEndPositionMs(5000).build())
            val source = sourceBuilder.build()
            val edited = EditedMediaItem.Builder(source).build()
            val listener = object : Transformer.Listener {
                override fun onCompleted(composition: Composition, result: ExportResult) {
                    transformer = null
                    if (output.length() > 0) complete(Result.success(output))
                    else { output.delete(); complete(Result.failure(IllegalStateException("Preview output was empty"))) }
                }
                override fun onError(composition: Composition, result: ExportResult, exception: ExportException) {
                    transformer = null
                    output.delete()
                    complete(Result.failure(exception))
                }
            }
            val encoderSettings = VideoEncoderSettings.Builder().setBitrate(bitrate).build()
            val encoderFactory = DefaultEncoderFactory.Builder(context).setRequestedVideoEncoderSettings(encoderSettings).build()
            transformer = Transformer.Builder(context)
                .setVideoMimeType(if (useHevc) MimeTypes.VIDEO_H265 else MimeTypes.VIDEO_H264)
                .setEncoderFactory(encoderFactory)
                .addListener(listener).build()
            transformer!!.start(edited, output.absolutePath)
        } catch (error: Exception) {
            transformer = null
            output.delete()
            complete(Result.failure(error))
        }
    }
}
