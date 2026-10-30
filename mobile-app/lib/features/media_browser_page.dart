import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class MediaBrowserPage extends StatefulWidget {
  const MediaBrowserPage({super.key});
  @override
  State<MediaBrowserPage> createState() => _MediaBrowserPageState();
}

class _MediaBrowserPageState extends State<MediaBrowserPage> {
  List<Map<String, dynamic>> media = [];
  final selected = <String>{};
  bool loading = true;
  String query = '';
  String? folder;
  String? error;
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    try {
      final data = await const MethodChannel('shrnk_it/media')
          .invokeListMethod<dynamic>('listMedia');
      if (mounted) {
        setState(
          () => media = (data ?? [])
              .map((entry) => Map<String, dynamic>.from(entry as Map))
              .toList(),
        );
      }
    } on PlatformException catch (e) {
      if (mounted) setState(() => error = e.message ?? 'Cannot load media');
    } on MissingPluginException {
      if (mounted) {
        setState(() => error = 'Media browsing is available on Android only.');
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final folders =
        media
            .map((e) => e['folder'] as String? ?? '')
            .where((s) => s.isNotEmpty)
            .toSet()
            .toList()
          ..sort();
    final needle = query.trim().toLowerCase();
    final visible =
        media
            .where(
              (e) =>
                  (folder == null || e['folder'] == folder) &&
                  '${e['name']} ${e['folder'] ?? ''}'.toLowerCase().contains(
                    needle,
                  ),
            )
            .toList()
          ..sort((a, b) => (b['size'] as int).compareTo(a['size'] as int));
    return Scaffold(
      appBar: AppBar(title: const Text('Browse media')),
      bottomNavigationBar: selected.isEmpty
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: FilledButton(
                  onPressed: () => Navigator.pop(
                    context,
                    media.where((e) => selected.contains(e['uri'])).toList(),
                  ),
                  child: Text('Add ${selected.length} selected'),
                ),
              ),
            ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : error != null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(error!),
              ),
            )
          : Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                  child: SearchBar(
                    leading: const Icon(Icons.search),
                    hintText: 'Search media or folder',
                    onChanged: (value) => setState(() => query = value),
                  ),
                ),
                SizedBox(
                  height: 52,
                  child: ListView(
                    scrollDirection: Axis.horizontal,
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: FilterChip(
                          label: const Text('All'),
                          selected: folder == null,
                          onSelected: (_) => setState(() => folder = null),
                        ),
                      ),
                      ...folders.map(
                        (name) => Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: FilterChip(
                            label: Text(name.replaceAll(RegExp(r'/$'), '')),
                            selected: folder == name,
                            onSelected: (_) => setState(
                              () => folder = folder == name ? null : name,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                if (visible.isEmpty)
                  const Expanded(
                    child: Center(child: Text('No matching media available.')),
                  )
                else
                  Expanded(
                    child: ListView.builder(
                      itemCount: visible.length,
                      itemBuilder: (context, index) {
                        final item = visible[index];
                        final uri = item['uri'] as String;
                        return CheckboxListTile(
                          value: selected.contains(uri),
                          onChanged: (checked) => setState(() {
                            if (checked == true) {
                              selected.add(uri);
                            } else {
                              selected.remove(uri);
                            }
                          }),
                          secondary: Icon(
                            (item['type'] as String).startsWith('video/')
                                ? Icons.movie_outlined
                                : Icons.image_outlined,
                          ),
                          title: Text(
                            item['name'] as String,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          subtitle: Text(
                            '${((item['size'] as int) / 1048576).toStringAsFixed(1)} MB · ${item['folder'] ?? ''}',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        );
                      },
                    ),
                  ),
              ],
            ),
    );
  }
}
