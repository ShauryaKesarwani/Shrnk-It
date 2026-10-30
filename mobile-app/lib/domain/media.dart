/// Metadata returned by the platform media library.
class MediaItem {
  const MediaItem({
    required this.id,
    required this.name,
    required this.folder,
    required this.sizeBytes,
    required this.isVideo,
  });
  final String id;
  final String name;
  final String folder;
  final int sizeBytes;
  final bool isVideo;
}

/// Filters without mutating the platform's original list and sorts largest first.
List<MediaItem> searchMedia(
  Iterable<MediaItem> items, {
  String query = '',
  String? folder,
}) {
  final needle = query.trim().toLowerCase();
  final result = items
      .where(
        (item) =>
            (folder == null || item.folder == folder) &&
            (needle.isEmpty ||
                '${item.name} ${item.folder}'.toLowerCase().contains(needle)),
      )
      .toList();
  result.sort((a, b) {
    final bySize = b.sizeBytes.compareTo(a.sizeBytes);
    return bySize != 0
        ? bySize
        : a.name.toLowerCase().compareTo(b.name.toLowerCase());
  });
  return result;
}

/// A replacement is worthwhile only if the output is valid and saves enough space.
bool meetsSavingsThreshold({
  required int originalBytes,
  required int outputBytes,
  required int minimumPercent,
}) {
  if (originalBytes <= 0 ||
      outputBytes <= 0 ||
      minimumPercent < 0 ||
      minimumPercent > 100) {
    return false;
  }
  return outputBytes < originalBytes &&
      (originalBytes - outputBytes) * 100 >= originalBytes * minimumPercent;
}
