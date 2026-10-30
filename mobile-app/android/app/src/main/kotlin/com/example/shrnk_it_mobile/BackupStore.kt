package com.example.shrnk_it_mobile

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.util.UUID

/** Stores originals in a user-authorized folder. Never overwrites a source. */
class BackupStore(private val context: Context) {
    private val prefs = context.getSharedPreferences("shrnk_backups", Context.MODE_PRIVATE)
    private val resolver get() = context.contentResolver

    fun setFolder(uri: Uri) {
        resolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        check(prefs.edit().putString("folder", uri.toString()).commit()) { "Could not save backup folder" }
    }

    @Synchronized
    fun list(): List<Map<String, Any>> {
        val records = JSONArray(prefs.getString("records", "[]"))
        return (0 until records.length()).map { index ->
            val record = records.getJSONObject(index)
            mapOf("name" to record.getString("name"), "backup" to record.getString("backup"), "bytes" to record.getLong("bytes"), "created" to record.getLong("created"), "sha256" to record.getString("sha256"))
        }.asReversed()
    }

    /** Restore into a newly created document, validating both backup and resulting copy. */
    fun restoreCopy(backup: Uri, destination: Uri, expectedHash: String) {
        fun hash(uri: Uri): String {
            val digest = MessageDigest.getInstance("SHA-256")
            (resolver.openInputStream(uri) ?: error("Cannot read file for verification")).use { stream ->
                val buffer = ByteArray(64 * 1024)
                while (true) { val count = stream.read(buffer); if (count < 0) break; if (count > 0) digest.update(buffer, 0, count) }
            }
            return digest.digest().joinToString("") { "%02x".format(it.toInt() and 0xff) }
        }
        check(hash(backup) == expectedHash) { "Backup verification failed; no copy was written" }
        (resolver.openInputStream(backup) ?: error("Cannot read backup")).use { source ->
            (resolver.openOutputStream(destination, "w") ?: error("Cannot write restored copy")).use { output -> source.copyTo(output); output.flush() }
        }
        check(hash(destination) == expectedHash) { "Restored copy did not pass verification; remove the incomplete copy" }
    }

    fun hasFolder(): Boolean = prefs.getString("folder", null) != null

    @Synchronized
    fun backup(source: Uri, name: String): JSONObject {
        val tree = Uri.parse(prefs.getString("folder", null) ?: error("Choose a backup folder first"))
        val root = DocumentsContract.buildDocumentUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree))
        val safeName = name.replace('/', '_').replace('\\', '_')
        val target = DocumentsContract.createDocument(resolver, root, "application/octet-stream", "${UUID.randomUUID()}-$safeName") ?: error("Could not create backup")
        var complete = false
        var sidecar: Uri? = null
        try {
            val originalHash = MessageDigest.getInstance("SHA-256")
            var length = 0L
            val input = resolver.openInputStream(source) ?: error("Cannot read original")
            input.use { sourceStream -> (resolver.openOutputStream(target, "w") ?: error("Cannot write backup")).use { targetStream ->
                val buffer = ByteArray(64 * 1024)
                while (true) {
                    val count = sourceStream.read(buffer)
                    if (count < 0) break
                    if (count == 0) continue
                    targetStream.write(buffer, 0, count)
                    originalHash.update(buffer, 0, count)
                    length += count
                }
                targetStream.flush()
            } }
            check(length > 0) { "Original was empty" }
            val backupHash = MessageDigest.getInstance("SHA-256")
            var copied = 0L
            (resolver.openInputStream(target) ?: error("Cannot verify backup")).use { stream ->
                val buffer = ByteArray(64 * 1024)
                while (true) {
                    val count = stream.read(buffer)
                    if (count < 0) break
                    if (count == 0) continue
                    backupHash.update(buffer, 0, count)
                    copied += count
                }
            }
            val digest = originalHash.digest()
            check(copied == length && digest.contentEquals(backupHash.digest())) { "Backup verification failed" }
            val hash = digest.joinToString("") { "%02x".format(it.toInt() and 0xff) }
            val record = JSONObject().put("name", name).put("source", source.toString()).put("backup", target.toString()).put("bytes", length).put("sha256", hash).put("created", System.currentTimeMillis())
            val recordUri = DocumentsContract.createDocument(resolver, root, "application/json", "${UUID.randomUUID()}-backup.json") ?: error("Could not create backup metadata")
            sidecar = recordUri
            (resolver.openOutputStream(recordUri, "w") ?: error("Cannot write backup metadata")).use {
                it.write(record.toString().toByteArray(Charsets.UTF_8))
                it.flush()
            }
            val records = JSONArray(prefs.getString("records", "[]"))
            records.put(record)
            check(prefs.edit().putString("records", records.toString()).commit()) { "Could not save backup record" }
            complete = true
            return record
        } finally {
            if (!complete) {
                try { DocumentsContract.deleteDocument(resolver, target) } catch (_: Exception) { }
                sidecar?.let { try { DocumentsContract.deleteDocument(resolver, it) } catch (_: Exception) { } }
            }
        }
    }
}
