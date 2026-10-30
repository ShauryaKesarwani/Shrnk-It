import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class JpegPreviewPage extends StatefulWidget {
  const JpegPreviewPage({super.key, required this.uri, required this.name});
  final String uri;
  final String name;
  @override
  State<JpegPreviewPage> createState() => _JpegPreviewPageState();
}

class _JpegPreviewPageState extends State<JpegPreviewPage> {
  double quality = 85;
  bool busy = false;
  double minimumSavings = 20;
  String? error;
  Map<String, dynamic>? preview;
  Map<String, dynamic>? prepared;
  String? status;

  Future<void> discardPreparedCopy() async {
    try {
      await const MethodChannel('shrnk_it/media')
          .invokeMethod<void>('discardJpegCopy');
    } on PlatformException {
      /* Cache cleanup is best effort. */
    } on MissingPluginException {
      /* No Android bridge on web. */
    }
  }

  @override
  void dispose() {
    if (!busy) discardPreparedCopy();
    super.dispose();
  }

  Future<void> prepareCopy() async {
    setState(() {
      busy = true;
      error = null;
      prepared = null;
      status = null;
    });
    try {
      final data = await const MethodChannel('shrnk_it/media')
          .invokeMapMethod<String, dynamic>('prepareJpegCopy', {
            'uri': widget.uri,
            'quality': quality.round(),
            'minimumSavings': minimumSavings.round(),
          });
      if (mounted) {
        setState(() => prepared = data);
      } else {
        await discardPreparedCopy();
      }
    } on PlatformException catch (e) {
      if (mounted) {
        setState(() => error = e.message ?? 'Could not compress photo.');
      }
    } on MissingPluginException {
      if (mounted) {
        setState(() => error = 'Compression is available on Android only.');
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> saveCopy() async {
    setState(() {
      busy = true;
      error = null;
      status = null;
    });
    try {
      final saved = await const MethodChannel('shrnk_it/media')
          .invokeMethod<bool>('saveJpegCopy', {'name': widget.name});
      if (mounted) {
        setState(() {
          prepared = null;
          status = saved == true
              ? 'Compressed copy saved and verified.'
              : 'Save cancelled.';
        });
      }
    } on PlatformException catch (e) {
      if (mounted) {
        setState(() {
          prepared = null;
          error = e.message ?? 'Could not save compressed copy.';
        });
      }
    } on MissingPluginException {
      if (mounted) {
        setState(() => error = 'Saving is available on Android only.');
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> generate() async {
    setState(() {
      busy = true;
      error = null;
      preview = null;
    });
    try {
      final result = await const MethodChannel('shrnk_it/media')
          .invokeMapMethod<String, dynamic>('previewJpeg', {
            'uri': widget.uri,
            'quality': quality.round(),
          });
      if (mounted) setState(() => preview = result);
    } on PlatformException catch (e) {
      if (mounted) {
        setState(() => error = e.message ?? 'Could not preview photo.');
      }
    } on MissingPluginException {
      if (mounted) {
        setState(() => error = 'Photo preview is available on Android only.');
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Compare photo quality')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text(widget.name, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        const Text(
          'JPEG compression loses detail. This preview does not change your original.',
        ),
        const SizedBox(height: 20),
        Text('JPEG quality: ${quality.round()}'),
        Slider(
          value: quality,
          min: 30,
          max: 100,
          divisions: 70,
          label: '${quality.round()}',
          onChanged: busy
              ? null
              : (value) => setState(() {
                  quality = value;
                  preview = null;
                  prepared = null;
                }),
        ),
        FilledButton.icon(
          onPressed: busy ? null : generate,
          icon: const Icon(Icons.compare),
          label: Text(busy ? 'Generating sample…' : 'Generate sample'),
        ),
        if (error != null)
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Text(
              error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        if (status != null)
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Text(status!),
          ),
        if (preview != null) ...[
          const SizedBox(height: 24),
          Text(
            'Original preview',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Image.memory(preview!['originalFrame'] as Uint8List),
          const SizedBox(height: 16),
          Text(
            'Compressed preview',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Image.memory(preview!['outputFrame'] as Uint8List),
          const SizedBox(height: 12),
          const Text(
            'The images are previews; large photos are downsampled. The original preview is encoded for display. Sample size is not the final file size.',
          ),
          const SizedBox(height: 16),
          const Text(
            'A compressed copy preserves orientation and basic camera/date tags; other metadata may be lost. Photos over 16 megapixels are not supported yet.',
          ),
          const SizedBox(height: 12),
          Text('Minimum saving: ${minimumSavings.round()}%'),
          Slider(
            value: minimumSavings,
            min: 0,
            max: 50,
            divisions: 50,
            onChanged: busy
                ? null
                : (value) => setState(() {
                    minimumSavings = value;
                    prepared = null;
                  }),
          ),
          OutlinedButton(
            onPressed: busy ? null : prepareCopy,
            child: Text(busy ? 'Working…' : 'Prepare compressed copy'),
          ),
          if (prepared != null) ...[
            Text(
              'Original: ${((prepared!['originalBytes'] as int) / 1048576).toStringAsFixed(2)} MB · Copy: ${((prepared!['outputBytes'] as int) / 1048576).toStringAsFixed(2)} MB',
            ),
            FilledButton(
              onPressed: busy ? null : saveCopy,
              child: const Text('Save separate copy'),
            ),
          ],
        ],
      ],
    ),
  );
}
