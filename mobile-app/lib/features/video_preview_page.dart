import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Shows a temporary sample. It never changes the selected file.
class VideoPreviewPage extends StatefulWidget {
  const VideoPreviewPage({
    super.key,
    required this.uri,
    required this.name,
    required this.hevcAvailable,
    this.originalBytes = 0,
  });
  final String uri;
  final String name;
  final bool hevcAvailable;
  final int originalBytes;
  @override
  State<VideoPreviewPage> createState() => _VideoPreviewPageState();
}

class _VideoPreviewPageState extends State<VideoPreviewPage> {
  bool busy = false;
  double minimumSavings = 20;
  double bitrateMbps = 3;
  bool hevc = false;
  String? error;
  Map<String, dynamic>? preview;
  Map<String, dynamic>? prepared;
  String? status;

  Future<void> discardPreparedCopy() async {
    try {
      await const MethodChannel('shrnk_it/media')
          .invokeMethod<void>('discardVideoCopy');
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
      final result = await const MethodChannel('shrnk_it/media')
          .invokeMapMethod<String, dynamic>('prepareVideoCopy', {
            'uri': widget.uri,
            'hevc': hevc,
            'bitrate': (bitrateMbps * 1000000).round(),
            'originalBytes': widget.originalBytes,
            'minimumSavings': minimumSavings.round(),
          });
      if (mounted) {
        setState(() => prepared = result);
      } else {
        await discardPreparedCopy();
      }
    } on PlatformException catch (e) {
      if (mounted) {
        setState(() => error = e.message ?? 'Could not compress video.');
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
          .invokeMethod<bool>('saveVideoCopy');
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

  @override
  void initState() {
    super.initState();
    hevc = widget.hevcAvailable;
  }

  Future<void> generate() async {
    setState(() {
      busy = true;
      error = null;
      preview = null;
    });
    try {
      final result = await const MethodChannel('shrnk_it/media')
          .invokeMapMethod<String, dynamic>('previewVideo', {
            'uri': widget.uri,
            'hevc': hevc,
            'bitrate': (bitrateMbps * 1000000).round(),
          });
      if (mounted) setState(() => preview = result);
    } on PlatformException catch (e) {
      if (mounted) {
        setState(() => error = e.message ?? 'Could not generate a preview.');
      }
    } on MissingPluginException {
      if (mounted) {
        setState(() => error = 'Preview is available on Android only.');
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Compare quality')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text(widget.name, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        const Text(
          'Generate a five-second sample. Your original stays untouched.',
        ),
        const SizedBox(height: 8),
        const Text(
          'This experimental preview may copy video without re-encoding when its format already matches the selected codec. The device may not use the requested bitrate.',
        ),
        const SizedBox(height: 20),
        SegmentedButton<bool>(
          segments: [
            ButtonSegment(value: false, label: const Text('H.264')),
            ButtonSegment(
              value: true,
              label: const Text('H.265'),
              enabled: widget.hevcAvailable,
            ),
          ],
          selected: {hevc},
          onSelectionChanged: busy
              ? null
              : (value) => setState(() {
                  hevc = value.first;
                  preview = null;
                  prepared = null;
                }),
        ),
        const SizedBox(height: 12),
        Text('Target video bitrate: ${bitrateMbps.toStringAsFixed(1)} Mbps'),
        Slider(
          value: bitrateMbps,
          min: 0.5,
          max: 10,
          divisions: 19,
          onChanged: busy
              ? null
              : (value) => setState(() {
                  bitrateMbps = value;
                  preview = null;
                  prepared = null;
                }),
        ),
        const SizedBox(height: 20),
        FilledButton.icon(
          onPressed: busy ? null : generate,
          icon: busy
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.compare),
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
          Text('Original', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Image.memory(
            preview!['originalFrame'] as Uint8List,
            fit: BoxFit.contain,
          ),
          const SizedBox(height: 16),
          Text('Sample', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Image.memory(
            preview!['outputFrame'] as Uint8List,
            fit: BoxFit.contain,
          ),
          const SizedBox(height: 12),
          Text(
            'Sample size: ${((preview!['sampleBytes'] as int) / 1048576).toStringAsFixed(2)} MB',
          ),
          const SizedBox(height: 8),
          const Text(
            'A sample does not predict the final file size or guarantee playback on other devices.',
          ),
          const SizedBox(height: 16),
          const Text(
            'The complete video is processed on this device. The separate copy must meet the minimum saving; some metadata may be lost.',
          ),
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
