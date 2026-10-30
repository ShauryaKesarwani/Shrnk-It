import 'media.dart';

/// Platform operations must verify the backup independently before returning true.
abstract interface class BatchOperations {
  Future<String> createBackup(MediaItem item);
  Future<bool> verifyBackup(MediaItem item, String backupId);
  Future<EncodedMedia> encode(MediaItem item);
  Future<bool> sourceUnchanged(MediaItem item);
  Future<void> replace(MediaItem item, EncodedMedia output);
  Future<bool> verifyReplacement(MediaItem item, EncodedMedia output);
  Future<void> discard(EncodedMedia output);
}

class EncodedMedia {
  const EncodedMedia({required this.id, required this.sizeBytes});
  final String id;
  final int sizeBytes;
}

enum BatchStatus { replaced, skipped, failed }

class BatchResult {
  const BatchResult(this.item, this.status, {this.backupId, this.reason});
  final MediaItem item;
  final BatchStatus status;
  final String? backupId;
  final String? reason;
}

/// Caller must obtain user approval and platform write consent before invoking.
/// Each item is independent; verified backups survive failures and are never deleted.
Future<List<BatchResult>> processBatch(
  Iterable<MediaItem> items,
  BatchOperations operations, {
  int minimumSavingsPercent = 20,
}) async {
  if (minimumSavingsPercent < 0 || minimumSavingsPercent > 100) {
    throw ArgumentError.value(minimumSavingsPercent, 'minimumSavingsPercent');
  }
  final results = <BatchResult>[];
  for (final item in items) {
    String? backup;
    EncodedMedia? output;
    try {
      backup = await operations.createBackup(item);
      if (!await operations.verifyBackup(item, backup)) {
        results.add(
          BatchResult(
            item,
            BatchStatus.failed,
            backupId: backup,
            reason: 'Backup verification failed',
          ),
        );
        continue;
      }
      output = await operations.encode(item);
      if (!meetsSavingsThreshold(
        originalBytes: item.sizeBytes,
        outputBytes: output.sizeBytes,
        minimumPercent: minimumSavingsPercent,
      )) {
        results.add(
          BatchResult(
            item,
            BatchStatus.skipped,
            backupId: backup,
            reason: 'Output did not meet the savings threshold',
          ),
        );
        continue;
      }
      if (!await operations.sourceUnchanged(item)) {
        results.add(
          BatchResult(
            item,
            BatchStatus.failed,
            backupId: backup,
            reason: 'Source changed after backup',
          ),
        );
        continue;
      }
      await operations.replace(item, output);
      if (!await operations.verifyReplacement(item, output)) {
        results.add(
          BatchResult(
            item,
            BatchStatus.failed,
            backupId: backup,
            reason: 'Replacement verification failed; restore the original from backup',
          ),
        );
        continue;
      }
      results.add(BatchResult(item, BatchStatus.replaced, backupId: backup));
    } catch (error) {
      results.add(
        BatchResult(
          item,
          BatchStatus.failed,
          backupId: backup,
          reason: error.toString(),
        ),
      );
    } finally {
      if (output != null) {
        try {
          await operations.discard(output);
        } catch (_) {
          /* Do not mask the operation outcome. */
        }
      }
    }
  }
  return results;
}
