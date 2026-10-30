/// A verified backup version; [originalId] identifies the same original across runs.
class BackupVersion {
  const BackupVersion({
    required this.id,
    required this.originalId,
    required this.createdAt,
    this.inUse = false,
  });
  final String id;
  final String originalId;
  final DateTime createdAt;
  final bool inUse;
}

/// Candidates are suggestions only. Deletion requires an explicit user action.
List<BackupVersion> cleanupCandidates(
  Iterable<BackupVersion> backups, {
  required DateTime now,
  int keepVersions = 3,
  Duration maxAge = const Duration(days: 30),
}) {
  if (keepVersions < 1 || maxAge.isNegative) {
    throw ArgumentError('Invalid retention policy');
  }
  final byOriginal = <String, List<BackupVersion>>{};
  for (final backup in backups) {
    byOriginal.putIfAbsent(backup.originalId, () => []).add(backup);
  }
  final candidates = <BackupVersion>[];
  for (final versions in byOriginal.values) {
    versions.sort((a, b) {
      final byDate = b.createdAt.compareTo(a.createdAt);
      return byDate != 0 ? byDate : a.id.compareTo(b.id);
    });
    for (var i = 0; i < versions.length; i++) {
      final backup = versions[i];
      if (!backup.inUse &&
          (i >= keepVersions ||
              backup.createdAt.isBefore(now.subtract(maxAge)))) {
        candidates.add(backup);
      }
    }
  }
  return candidates;
}
