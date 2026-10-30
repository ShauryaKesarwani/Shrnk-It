import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class BackupsPage extends StatefulWidget {
  const BackupsPage({super.key});
  @override
  State<BackupsPage> createState() => _BackupsPageState();
}

class _BackupsPageState extends State<BackupsPage> {
  late final Future<List<dynamic>> records = load();
  Future<List<dynamic>> load() async =>
      await const MethodChannel('shrnk_it/media')
          .invokeListMethod<dynamic>('listBackups') ??
      [];

  Future<void> restoreCopy(Map<String, dynamic> backup) async {
    try {
      final restored = await const MethodChannel('shrnk_it/media')
          .invokeMethod<bool>('restoreBackupCopy', {
            'uri': backup['backup'],
            'name': backup['name'],
            'sha256': backup['sha256'],
          });
      if (mounted && restored == true) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Restored copy verified.')),
        );
      }
    } on PlatformException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.message ?? 'Restore failed.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Backups')),
    body: FutureBuilder<List<dynamic>>(
      future: records,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return const Center(
            child: Text('Could not load backups on this device.'),
          );
        }
        final backups = snapshot.data ?? [];
        if (backups.isEmpty) {
          return const Center(child: Text('No backups yet.'));
        }
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Padding(
              padding: EdgeInsets.all(8),
              child: Text(
                'Choose a backup to inspect it or restore a separate copy. Existing files are not replaced.',
              ),
            ),
            ...backups.map((raw) {
              final backup = Map<String, dynamic>.from(raw as Map);
              final date = DateTime.fromMillisecondsSinceEpoch(
                backup['created'] as int,
              ).toLocal();
              return Card(
                child: ListTile(
                  leading: const Icon(Icons.restore_page_outlined),
                  title: Text(backup['name'] as String),
                  subtitle: Text(
                    '${(backup['bytes'] / 1048576).toStringAsFixed(2)} MB · ${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}',
                  ),
                  onTap: () => showDialog<void>(
                    context: context,
                    builder: (context) => AlertDialog(
                      title: Text(backup['name'] as String),
                      content: SelectableText(
                        'SHA-256\n${backup['sha256']}\n\nBackup URI\n${backup['backup']}',
                      ),
                      actions: [
                        FilledButton.tonal(
                          onPressed: () {
                            Navigator.pop(context);
                            restoreCopy(backup);
                          },
                          child: const Text('Restore a copy'),
                        ),
                        TextButton(
                          onPressed: () => Navigator.pop(context),
                          child: const Text('Close'),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            }),
          ],
        );
      },
    ),
  );
}
