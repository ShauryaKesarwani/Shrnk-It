import 'package:flutter_test/flutter_test.dart';
import 'package:shrnk_it_mobile/domain/backup_retention.dart';

void main() {
  final now = DateTime.utc(2026, 10, 30);
  BackupVersion version(
    String id,
    String original,
    int days, {
    bool inUse = false,
  }) => BackupVersion(
    id: id,
    originalId: original,
    createdAt: now.subtract(Duration(days: days)),
    inUse: inUse,
  );
  test('proposes old and excess versions independently per original', () {
    final backups = [
      version('a1', 'a', 1),
      version('a2', 'a', 2),
      version('a3', 'a', 3),
      version('a4', 'a', 4),
      version('b1', 'b', 31),
      version('b2', 'b', 30),
    ];
    expect(
      cleanupCandidates(backups, now: now).map((e) => e.id),
      unorderedEquals(['a4', 'b1']),
    );
    expect(backups.map((e) => e.id), ['a1', 'a2', 'a3', 'a4', 'b1', 'b2']);
  });
  test('never proposes an active backup, even when old or excess', () {
    expect(
      cleanupCandidates([version('a', 'x', 60, inUse: true)], now: now),
      isEmpty,
    );
  });
  test('rejects invalid retention settings', () {
    expect(
      () => cleanupCandidates([], now: now, keepVersions: 0),
      throwsArgumentError,
    );
    expect(
      () => cleanupCandidates([], now: now, maxAge: const Duration(days: -1)),
      throwsArgumentError,
    );
  });
}
