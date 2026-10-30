import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'features/video_preview_page.dart';
import 'features/backups_page.dart';
import 'features/jpeg_preview_page.dart';
import 'features/media_browser_page.dart';

void main() => runApp(const ShrnkApp());

class ShrnkApp extends StatefulWidget {
  const ShrnkApp({super.key});

  @override
  State<ShrnkApp> createState() => _ShrnkAppState();
}

class _ShrnkAppState extends State<ShrnkApp> {
  Color seed = const Color(0xff6459b8);

  @override
  void initState() {
    super.initState();
    _loadWallpaperAccent();
  }

  Future<void> _loadWallpaperAccent() async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) return;
    try {
      final accent = await const MethodChannel('shrnk_it/media')
          .invokeMethod<int>('wallpaperAccent');
      if (mounted && accent != null) setState(() => seed = Color(accent));
    } on PlatformException {
      // Use the default palette if Android cannot supply a wallpaper accent.
    } on MissingPluginException {
      // Android platform integration is not available in widget tests.
    }
  }

  @override
  Widget build(BuildContext context) {
    final light = ColorScheme.fromSeed(seedColor: seed);
    final dark = ColorScheme.fromSeed(
      seedColor: seed,
      brightness: Brightness.dark,
    );
    return MaterialApp(
      title: 'Shrnk It',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(useMaterial3: true, colorScheme: light),
      darkTheme: ThemeData(useMaterial3: true, colorScheme: dark),
      home: const HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  static const channel = MethodChannel('shrnk_it/media');
  final List<Map<String, dynamic>> files = [];
  String query = '';
  bool largestFirst = true;
  bool loading = false;
  String? message;
  Map<String, dynamic>? codecs;

  @override
  void initState() {
    super.initState();
    loadCodecs();
  }

  Future<void> loadCodecs() async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) return;
    try {
      final result = await channel.invokeMapMethod<String, dynamic>(
        'codecSupport',
      );
      if (mounted) setState(() => codecs = result);
    } on PlatformException {
      // Codec detection is informational; media selection remains available.
    } on MissingPluginException {
      // The Android bridge is unavailable in non-Android test environments.
    }
  }

  Future<void> pickFiles() async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) {
      setState(
        () => message = 'File selection is available in the Android app.',
      );
      return;
    }
    setState(() {
      loading = true;
      message = null;
    });
    try {
      final result = await channel.invokeListMethod<dynamic>('pickMedia');
      if (!mounted) return;
      setState(() {
        for (final entry in result ?? []) {
          final file = Map<String, dynamic>.from(entry as Map);
          if (!files.any((existing) => existing['uri'] == file['uri'])) {
            files.add(file);
          }
        }
      });
    } on PlatformException catch (error) {
      if (mounted) {
        setState(
          () => message = error.message ?? 'Could not open the media picker.',
        );
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> browseMedia() async {
    final chosen = await Navigator.of(context).push<List<Map<String, dynamic>>>(
      MaterialPageRoute(builder: (_) => const MediaBrowserPage()),
    );
    if (!mounted || chosen == null) return;
    setState(() {
      for (final item in chosen) {
        if (!files.any((existing) => existing['uri'] == item['uri'])) {
          files.add(item);
        }
      }
    });
  }

  Future<void> backupSelected() async {
    if (files.isEmpty || loading) return;
    setState(() {
      loading = true;
      message = null;
    });
    try {
      var hasFolder =
          await channel.invokeMethod<bool>('hasBackupFolder') ?? false;
      if (!hasFolder) {
        hasFolder =
            await channel.invokeMethod<bool>('chooseBackupFolder') ?? false;
      }
      if (!hasFolder) return;
      var completed = 0;
      final errors = <String>[];
      for (final file in files) {
        try {
          await channel.invokeMethod<int>('backupMedia', {
            'uri': file['uri'],
            'name': file['name'],
          });
          completed++;
        } on PlatformException catch (error) {
          errors.add('${file['name']}: ${error.message ?? 'backup failed'}');
        }
      }
      if (mounted) {
        setState(
          () => message =
              '$completed backup(s) verified.${errors.isEmpty ? '' : ' Failed: ${errors.join('; ')}'}',
        );
      }
    } on PlatformException catch (error) {
      if (mounted) {
        setState(
          () => message = error.message ?? 'Could not access backup folder.',
        );
      }
    } on MissingPluginException {
      if (mounted) {
        setState(() => message = 'Backups are available on Android only.');
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final visible =
        files
            .where(
              (file) => (file['name'] as String).toLowerCase().contains(
                query.toLowerCase(),
              ),
            )
            .toList()
          ..sort(
            (a, b) => largestFirst
                ? (b['size'] as int).compareTo(a['size'] as int)
                : (a['name'] as String).compareTo(b['name'] as String),
          );
    return Scaffold(
      appBar: AppBar(
        title: const Text('Shrnk It'),
        actions: [
          IconButton(
            tooltip: 'Backups',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const BackupsPage()),
            ),
            icon: const Icon(Icons.backup_outlined),
          ),
          IconButton(
            onPressed: () => setState(() => largestFirst = !largestFirst),
            tooltip: largestFirst ? 'Sort by name' : 'Sort by size',
            icon: const Icon(Icons.sort_rounded),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 680),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
            children: [
              Text(
                'Your media',
                style: Theme.of(context).textTheme.headlineMedium
                    ?.copyWith(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 6),
              Text(
                'Choose photos and videos to make more space.',
                style: Theme.of(context).textTheme.bodyLarge
                    ?.copyWith(color: colors.onSurfaceVariant),
              ),
              const SizedBox(height: 24),
              SearchBar(
                leading: const Icon(Icons.search),
                hintText: 'Search selected files',
                elevation: const WidgetStatePropertyAll(0),
                backgroundColor: WidgetStatePropertyAll(
                  colors.surfaceContainerHighest,
                ),
                onChanged: (value) => setState(() => query = value),
              ),
              const SizedBox(height: 20),
              if (codecs != null)
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.high_quality_outlined),
                    title: const Text('Video compatibility'),
                    subtitle: Text(
                      codecs!['hevcEncoder'] == true
                          ? 'H.265 encoding is available on this device.'
                          : codecs!['avcEncoder'] == true
                          ? 'H.265 encoding is unavailable; H.264 is available.'
                          : 'No H.265 or H.264 encoder was detected.',
                    ),
                  ),
                ),
              FilledButton.tonalIcon(
                onPressed: loading ? null : browseMedia,
                icon: const Icon(Icons.photo_library_outlined),
                label: const Text('Browse local media'),
              ),
              const SizedBox(height: 8),
              FilledButton.icon(
                onPressed: loading ? null : pickFiles,
                icon: const Icon(Icons.add_photo_alternate_outlined),
                label: Text(
                  loading ? 'Opening picker…' : 'Choose photos & videos',
                ),
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.all(18),
                ),
              ),
              if (message != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(message!, style: TextStyle(color: colors.error)),
                ),
              const SizedBox(height: 28),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Selected',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  ),
                  Text(
                    '${files.length} files',
                    style: TextStyle(color: colors.onSurfaceVariant),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              if (visible.isEmpty)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 24,
                    vertical: 32,
                  ),
                  decoration: BoxDecoration(
                    color: colors.surfaceContainerLow,
                    borderRadius: BorderRadius.circular(28),
                  ),
                  child: Column(
                    children: [
                      Icon(
                        Icons.collections_outlined,
                        size: 40,
                        color: colors.primary,
                      ),
                      const SizedBox(height: 12),
                      Text(
                        files.isEmpty
                            ? 'Nothing selected yet'
                            : 'No matching files',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 6),
                      Text(
                        files.isEmpty
                            ? 'Your selected media will appear here.'
                            : 'Try a different search.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: colors.onSurfaceVariant),
                      ),
                    ],
                  ),
                )
              else
                ...visible.map(
                  (file) => Card(
                    child: ListTile(
                      leading: Icon(
                        (file['type'] as String).startsWith('video/')
                            ? Icons.movie_outlined
                            : Icons.image_outlined,
                      ),
                      title: Text(
                        file['name'] as String,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      subtitle: Text(
                        '${((file['size'] as int) / 1048576).toStringAsFixed(1)} MB',
                      ),
                      onTap: (file['type'] as String).startsWith('video/')
                          ? () => Navigator.of(context).push(
                              MaterialPageRoute<void>(
                                builder: (_) => VideoPreviewPage(
                                  uri: file['uri'] as String,
                                  name: file['name'] as String,
                                  originalBytes: file['size'] as int,
                                  hevcAvailable: codecs?['hevcEncoder'] == true,
                                ),
                              ),
                            )
                          : (file['type'] as String) == 'image/jpeg'
                          ? () => Navigator.of(context).push(
                              MaterialPageRoute<void>(
                                builder: (_) => JpegPreviewPage(
                                  uri: file['uri'] as String,
                                  name: file['name'] as String,
                                ),
                              ),
                            )
                          : null,
                      trailing: IconButton(
                        icon: const Icon(Icons.close),
                        tooltip: 'Remove',
                        onPressed: () => setState(() => files.remove(file)),
                      ),
                    ),
                  ),
                ),
              const SizedBox(height: 20),
              OutlinedButton.icon(
                onPressed: files.isEmpty || loading ? null : backupSelected,
                icon: const Icon(Icons.backup_outlined),
                label: const Text('Back up selected files'),
              ),
              const SizedBox(height: 12),
              Card.filled(
                color: colors.secondaryContainer,
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        Icons.info_outline,
                        color: colors.onSecondaryContainer,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          'Previews, backups, and separate copies are experimental. In-place replacement and restore are still being built. Your originals will not be changed.',
                          style: TextStyle(color: colors.onSecondaryContainer),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
