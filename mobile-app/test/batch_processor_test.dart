import 'package:flutter_test/flutter_test.dart';
import 'package:shrnk_it_mobile/domain/batch_processor.dart';
import 'package:shrnk_it_mobile/domain/media.dart';

class FakeOperations implements BatchOperations {
  final calls = <String>[];
  bool verified = true;
  bool unchanged = true;
  bool replacementVerified = true;
  String? failBackupFor;
  int outputSize = 50;
  @override
  Future<String> createBackup(MediaItem item) async {
    calls.add('backup:${item.id}');
    if (item.id == failBackupFor) throw StateError('backup failed');
    return 'backup-${item.id}';
  }

  @override
  Future<bool> verifyBackup(MediaItem item, String backupId) async {
    calls.add('verify:${item.id}');
    return verified;
  }

  @override
  Future<EncodedMedia> encode(MediaItem item) async {
    calls.add('encode:${item.id}');
    return EncodedMedia(id: item.id, sizeBytes: outputSize);
  }

  @override
  Future<bool> sourceUnchanged(MediaItem item) async {
    calls.add('check:${item.id}');
    return unchanged;
  }

  @override
  Future<void> replace(MediaItem item, EncodedMedia output) async {
    calls.add('replace:${item.id}');
  }

  @override
  Future<bool> verifyReplacement(MediaItem item, EncodedMedia output) async {
    calls.add('verify-replacement:${item.id}');
    return replacementVerified;
  }

  @override
  Future<void> discard(EncodedMedia output) async {
    calls.add('discard:${output.id}');
  }
}

void main() {
  const item = MediaItem(
    id: 'one',
    name: 'a.mp4',
    folder: 'Camera',
    sizeBytes: 100,
    isVideo: true,
  );
  test('verifies backup and unchanged source before replacing', () async {
    final ops = FakeOperations();
    final result = await processBatch([item], ops);
    expect(result.single.status, BatchStatus.replaced);
    expect(ops.calls, [
      'backup:one',
      'verify:one',
      'encode:one',
      'check:one',
      'replace:one',
      'verify-replacement:one',
      'discard:one',
    ]);
  });
  test('never encodes or replaces after failed backup verification', () async {
    final ops = FakeOperations()..verified = false;
    final result = await processBatch([item], ops);
    expect(result.single.status, BatchStatus.failed);
    expect(result.single.backupId, 'backup-one');
    expect(ops.calls, ['backup:one', 'verify:one']);
  });
  test('continues after an item fails and retains its result', () async {
    const second = MediaItem(
      id: 'two',
      name: 'b.mp4',
      folder: 'Camera',
      sizeBytes: 100,
      isVideo: true,
    );
    final ops = FakeOperations()..failBackupFor = 'one';
    final results = await processBatch([item, second], ops);
    expect(results.map((result) => result.status), [
      BatchStatus.failed,
      BatchStatus.replaced,
    ]);
    expect(ops.calls, isNot(contains('replace:one')));
    expect(ops.calls, contains('replace:two'));
  });
  test(
    'reports failed replacement verification and keeps the backup reference',
    () async {
      final ops = FakeOperations()..replacementVerified = false;
      final result = (await processBatch([item], ops)).single;
      expect(result.status, BatchStatus.failed);
      expect(result.backupId, 'backup-one');
      expect(result.reason, contains('restore'));
    },
  );
  test('discards output without replacing when source changed or savings are too small', () async {
    final changed = FakeOperations()..unchanged = false;
    expect(
      (await processBatch([item], changed)).single.status,
      BatchStatus.failed,
    );
    expect(changed.calls, isNot(contains('replace:one')));
    expect(changed.calls.last, 'discard:one');
    final large = FakeOperations()..outputSize = 90;
    expect(
      (await processBatch([item], large)).single.status,
      BatchStatus.skipped,
    );
    expect(large.calls, isNot(contains('replace:one')));
    expect(large.calls.last, 'discard:one');
  });
}
