import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

void main() => runApp(const ShrnkApp());

class ShrnkApp extends StatelessWidget {
  const ShrnkApp({super.key});
  @override
  Widget build(BuildContext context) {
    final light = ColorScheme.fromSeed(seedColor: const Color(0xff6459b8));
    final dark = ColorScheme.fromSeed(
      seedColor: const Color(0xffa99ff7),
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
                      trailing: IconButton(
                        icon: const Icon(Icons.close),
                        tooltip: 'Remove',
                        onPressed: () => setState(() => files.remove(file)),
                      ),
                    ),
                  ),
                ),
              const SizedBox(height: 20),
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
                          'Compression and backups are still being built. Your originals will not be changed.',
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
