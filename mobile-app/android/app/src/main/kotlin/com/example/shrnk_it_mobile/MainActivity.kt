package com.example.shrnk_it_mobile

import android.app.Activity
import android.content.Intent
import android.provider.OpenableColumns
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var pending: MethodChannel.Result? = null
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "shrnk_it/media").setMethodCallHandler { call, result ->
            if (call.method != "pickMedia") { result.notImplemented(); return@setMethodCallHandler }
            if (pending != null) { result.error("busy", "The picker is already open.", null); return@setMethodCallHandler }
            pending = result
            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "*/*"
                putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("image/jpeg", "video/*"))
                putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
            }
            try { startActivityForResult(intent, 1001) } catch (e: Exception) {
                pending = null
                result.error("picker", e.localizedMessage, null)
            }
        }
    }
    @Deprecated("Android activity result")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 1001) return
        val result = pending ?: return
        pending = null
        if (resultCode != Activity.RESULT_OK || data == null) { result.success(emptyList<Map<String, Any>>()); return }
        val uris = if (data.clipData != null) (0 until data.clipData!!.itemCount).map { data.clipData!!.getItemAt(it).uri } else listOfNotNull(data.data)
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
    }
}
