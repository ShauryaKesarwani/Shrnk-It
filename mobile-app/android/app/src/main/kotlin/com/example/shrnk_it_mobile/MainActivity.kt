package com.example.shrnk_it_mobile

import android.app.Activity
import android.Manifest
import android.content.pm.PackageManager
import android.content.Intent
import android.media.MediaCodecList
import android.os.Build
import android.net.Uri
import androidx.media3.common.util.UnstableApi
import android.provider.OpenableColumns
import android.provider.MediaStore
import java.io.File
import java.security.MessageDigest
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

@UnstableApi
class MainActivity : FlutterActivity() {
    private val videoPreview by lazy { VideoPreview(this) }
    private val backups by lazy { BackupStore(this) }
    private var libraryPending: MethodChannel.Result? = null
    private var pending: MethodChannel.Result? = null
    private var pendingRestore: Pair<String, String>? = null
    private var preparedVideo: File? = null
    private var preparedJpeg: File? = null
    private var jpegPreparing = false
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "shrnk_it/media").setMethodCallHandler { call, result ->
            if (call.method == "listMedia") {
                if (libraryPending != null) { result.error("busy", "Media access is already being requested", null); return@setMethodCallHandler }
                val permissions = when {
                    Build.VERSION.SDK_INT >= 34 -> arrayOf(Manifest.permission.READ_MEDIA_IMAGES, Manifest.permission.READ_MEDIA_VIDEO, Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED)
                    Build.VERSION.SDK_INT >= 33 -> arrayOf(Manifest.permission.READ_MEDIA_IMAGES, Manifest.permission.READ_MEDIA_VIDEO)
                    else -> arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
                }
                if (permissions.any { checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }) loadMedia(result)
                else { libraryPending = result; requestPermissions(permissions, 1004) }
                return@setMethodCallHandler
            }
            if (call.method == "restoreBackupCopy") {
                if (pending != null) { result.error("busy", "A picker is already open.", null); return@setMethodCallHandler }
                val uri = call.argument<String>("uri")
                val hash = call.argument<String>("sha256")
                val name = call.argument<String>("name")
                if (uri == null || hash == null || name == null) { result.error("invalid", "Missing backup details", null); return@setMethodCallHandler }
                pending = result
                pendingRestore = uri to hash
                val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/octet-stream").putExtra(Intent.EXTRA_TITLE, name)
                try { startActivityForResult(intent, 1003) } catch (e: Exception) { pending = null; pendingRestore = null; result.error("picker", e.localizedMessage, null) }
                return@setMethodCallHandler
            }
            if (call.method == "chooseBackupFolder") {
                if (pending != null) { result.error("busy", "A picker is already open.", null); return@setMethodCallHandler }
                pending = result
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
                try { startActivityForResult(intent, 1002) } catch (e: Exception) { pending = null; result.error("picker", e.localizedMessage, null) }
                return@setMethodCallHandler
            }
            if (call.method == "backupMedia") {
                val raw = call.argument<String>("uri")
                val name = call.argument<String>("name")
                if (raw == null || name == null) { result.error("invalid", "Missing file details", null); return@setMethodCallHandler }
                Thread {
                    try {
                        val record = backups.backup(Uri.parse(raw), name)
                        runOnUiThread { result.success(record.getLong("bytes")) }
                    } catch (e: Exception) { runOnUiThread { result.error("backup", e.localizedMessage, null) } }
                }.start()
                return@setMethodCallHandler
            }
            if (call.method == "listBackups") { try { result.success(backups.list()) } catch (e: Exception) { result.error("backups", e.localizedMessage, null) }; return@setMethodCallHandler }
            if (call.method == "hasBackupFolder") { result.success(backups.hasFolder()); return@setMethodCallHandler }
            if (call.method == "prepareVideoCopy") {
                val raw = call.argument<String>("uri")
                val originalBytes = call.argument<Number>("originalBytes")?.toLong() ?: 0L
                val minSavings = call.argument<Int>("minimumSavings") ?: 20
                if (minSavings !in 0..100) { result.error("invalid", "Invalid savings threshold", null); return@setMethodCallHandler }
                if (raw == null || originalBytes <= 0) { result.error("invalid", "Original size is unavailable; cannot check savings", null); return@setMethodCallHandler }
                preparedVideo?.delete(); preparedVideo = null
                val bitrate = (call.argument<Int>("bitrate") ?: 3_000_000).coerceIn(500_000, 20_000_000)
                videoPreview.start(Uri.parse(raw), call.argument<Boolean>("hevc") == true, false, bitrate) { outcome ->
                    outcome.fold(onSuccess = { file ->
                        if (file.length() <= 0 || file.length() >= originalBytes || file.length().toDouble() > originalBytes.toDouble() * (100 - minSavings) / 100.0) { file.delete(); result.error("savings", "Output did not meet the savings threshold; original remains unchanged", null) }
                        else { preparedVideo = file; result.success(mapOf("originalBytes" to originalBytes, "outputBytes" to file.length())) }
                    }, onFailure = { error -> result.error("compress", error.localizedMessage, null) })
                }
                return@setMethodCallHandler
            }
            if (call.method == "saveVideoCopy") {
                val file = preparedVideo
                if (file == null || !file.exists()) { result.error("missing", "Prepare the compressed copy first", null); return@setMethodCallHandler }
                if (pending != null) { result.error("busy", "A picker is already open", null); return@setMethodCallHandler }
                pending = result
                val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("video/mp4").putExtra(Intent.EXTRA_TITLE, "compressed-video.mp4")
                try { startActivityForResult(intent, 1006) } catch (e: Exception) { pending = null; result.error("picker", e.localizedMessage, null) }
                return@setMethodCallHandler
            }
            if (call.method == "prepareJpegCopy") {
                val raw = call.argument<String>("uri")
                val quality = call.argument<Int>("quality")
                if (raw == null || quality == null) { result.error("invalid", "Missing photo or quality", null); return@setMethodCallHandler }
                if (jpegPreparing || pending != null) { result.error("busy", "Another operation is running", null); return@setMethodCallHandler }
                preparedJpeg?.delete(); preparedJpeg = null; jpegPreparing = true
                Thread {
                    try {
                        val (file, sourceSize) = JpegCompressor.prepare(this, Uri.parse(raw), quality, call.argument<Int>("minimumSavings") ?: 20)
                        runOnUiThread { jpegPreparing = false; preparedJpeg = file; result.success(mapOf("originalBytes" to sourceSize, "outputBytes" to file.length())) }
                    } catch (e: Exception) { runOnUiThread { jpegPreparing = false; result.error("compress", e.localizedMessage, null) } }
                }.start()
                return@setMethodCallHandler
            }
            if (call.method == "saveJpegCopy") {
                val file = preparedJpeg
                if (file == null || !file.exists()) { result.error("missing", "Prepare the compressed copy first", null); return@setMethodCallHandler }
                if (pending != null) { result.error("busy", "A picker is already open", null); return@setMethodCallHandler }
                pending = result
                val name = call.argument<String>("name") ?: "compressed.jpg"
                val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("image/jpeg").putExtra(Intent.EXTRA_TITLE, "compressed-$name")
                try { startActivityForResult(intent, 1005) } catch (e: Exception) { pending = null; result.error("picker", e.localizedMessage, null) }
                return@setMethodCallHandler
            }
            if (call.method == "discardJpegCopy") { preparedJpeg?.delete(); preparedJpeg = null; result.success(null); return@setMethodCallHandler }
            if (call.method == "discardVideoCopy") { preparedVideo?.delete(); preparedVideo = null; result.success(null); return@setMethodCallHandler }
            if (call.method == "previewJpeg") {
                val raw = call.argument<String>("uri")
                val quality = call.argument<Int>("quality")
                if (raw == null || quality == null) { result.error("invalid", "Missing photo or quality", null); return@setMethodCallHandler }
                Thread {
                    try { val preview = JpegPreview.create(this, Uri.parse(raw), quality); runOnUiThread { result.success(preview) } }
                    catch (e: Exception) { runOnUiThread { result.error("preview", e.localizedMessage, null) } }
                }.start()
                return@setMethodCallHandler
            }
            if (call.method == "previewVideo") {
                val rawUri = call.argument<String>("uri")
                if (rawUri == null) { result.error("invalid", "Missing media URI", null); return@setMethodCallHandler }
                val uri = Uri.parse(rawUri)
                val bitrate = (call.argument<Int>("bitrate") ?: 3_000_000).coerceIn(500_000, 20_000_000)
                videoPreview.start(uri, call.argument<Boolean>("hevc") == true, true, bitrate) { preview ->
                    preview.fold(onSuccess = { file ->
                        Thread {
                            try {
                                val originalFrame = PreviewFrames.read(this, uri)
                                val outputFrame = PreviewFrames.read(this, file)
                                val sampleBytes = file.length()
                                runOnUiThread { result.success(mapOf("originalFrame" to originalFrame, "outputFrame" to outputFrame, "sampleBytes" to sampleBytes)) }
                            } catch (e: Exception) { runOnUiThread { result.error("preview", e.localizedMessage, null) } }
                            finally { file.delete() }
                        }.start()
                    }, onFailure = { error -> result.error("preview", error.localizedMessage, null) })
                }
                return@setMethodCallHandler
            }
            if (call.method == "wallpaperAccent") {
                result.success(if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) getColor(android.R.color.system_accent1_500).toLong() and 0xffffffffL else null)
                return@setMethodCallHandler
            }
            if (call.method == "codecSupport") {
                val codecs = MediaCodecList(MediaCodecList.REGULAR_CODECS).codecInfos
                fun supports(mime: String, encoder: Boolean) = codecs.any { codec ->
                    codec.isEncoder == encoder && codec.supportedTypes.any { it.equals(mime, ignoreCase = true) }
                }
                result.success(mapOf("hevcEncoder" to supports("video/hevc", true), "hevcDecoder" to supports("video/hevc", false), "avcEncoder" to supports("video/avc", true)))
                return@setMethodCallHandler
            }
            if (call.method != "pickMedia") { result.notImplemented(); return@setMethodCallHandler }
            if (pending != null) { result.error("busy", "The picker is already open.", null); return@setMethodCallHandler }
            pending = result
            val intent = if (Build.VERSION.SDK_INT >= 33) {
                Intent(MediaStore.ACTION_PICK_IMAGES).apply {
                    putExtra(MediaStore.EXTRA_PICK_IMAGES_MAX, minOf(100, MediaStore.getPickImagesMaxLimit()))
                }
            } else {
                Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "*/*"
                    putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("image/jpeg", "video/*"))
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
                }
            }
            try { startActivityForResult(intent, 1001) } catch (e: Exception) {
                pending = null
                result.error("picker", e.localizedMessage, null)
            }
        }
    }
    private fun loadMedia(result: MethodChannel.Result) {
        Thread {
            try { val media = MediaLibrary.list(this); runOnUiThread { result.success(media) } }
            catch (e: Exception) { runOnUiThread { result.error("media", e.localizedMessage, null) } }
        }.start()
    }

    @Deprecated("Android permission result")
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != 1004) return
        val result = libraryPending ?: return
        libraryPending = null
        if (grantResults.any { it == PackageManager.PERMISSION_GRANTED }) loadMedia(result)
        else result.error("permission", "Allow media access to browse your library", null)
    }

    @Deprecated("Android activity result")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 1001 && requestCode != 1002 && requestCode != 1003 && requestCode != 1005 && requestCode != 1006) return
        val result = pending ?: return
        pending = null
        if (requestCode == 1005 || requestCode == 1006) {
            val file = if (requestCode == 1005) preparedJpeg else preparedVideo
            if (requestCode == 1005) preparedJpeg = null else preparedVideo = null
            val destination = if (resultCode == Activity.RESULT_OK) data?.data else null
            if (destination == null || file == null) { file?.delete(); result.success(false); return }
            Thread {
                try {
                    val digest = MessageDigest.getInstance("SHA-256")
                    file.inputStream().use { stream -> val buffer = ByteArray(64 * 1024); while (true) { val n = stream.read(buffer); if (n < 0) break; if (n > 0) digest.update(buffer, 0, n) } }
                    val hash = digest.digest().joinToString("") { "%02x".format(it.toInt() and 0xff) }
                    backups.restoreCopy(Uri.fromFile(file), destination, hash)
                    runOnUiThread { result.success(true) }
                } catch (e: Exception) { runOnUiThread { result.error("save", "${e.localizedMessage ?: "Save failed"}. The new copy may be incomplete; remove it if necessary.", null) } }
                finally { file.delete() }
            }.start()
            return
        }
        if (requestCode == 1003) {
            val details = pendingRestore
            pendingRestore = null
            val destination = if (resultCode == Activity.RESULT_OK) data?.data else null
            if (destination == null || details == null) { result.success(false); return }
            Thread {
                try { backups.restoreCopy(Uri.parse(details.first), destination, details.second); runOnUiThread { result.success(true) } }
                catch (e: Exception) { runOnUiThread { result.error("restore", "${e.localizedMessage ?: "Restore failed"}. The new copy may be incomplete; remove it if necessary.", null) } }
            }.start()
            return
        }
        if (requestCode == 1002) {
            val uri = if (resultCode == Activity.RESULT_OK) data?.data else null
            if (uri == null) { result.success(false); return }
            try { backups.setFolder(uri); result.success(true) } catch (e: Exception) { result.error("folder", e.localizedMessage, null) }
            return
        }
        if (resultCode != Activity.RESULT_OK || data == null) { result.success(emptyList<Map<String, Any>>()); return }
        val uris = if (data.clipData != null) (0 until data.clipData!!.itemCount).map { data.clipData!!.getItemAt(it).uri } else listOfNotNull(data.data)
        try {
        val files = uris.map { uri ->
            try { contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) } catch (_: SecurityException) { }
            var name = "Media"
            var size = 0L
            contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) { name = cursor.getString(0) ?: name; if (!cursor.isNull(1)) size = cursor.getLong(1) }
            }
            mapOf("uri" to uri.toString(), "name" to name, "size" to size, "type" to (contentResolver.getType(uri) ?: ""))
        }
        result.success(files)
        } catch (e: Exception) {
            result.error("picker", e.localizedMessage ?: "Could not read selected media", null)
        }
    }
}
