import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shrnk_it_mobile/features/video_preview_page.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('shrnk_it/media');
  tearDown(
    () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null),
  );
  testWidgets('reports preview failures without changing the source', (
    tester,
  ) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          expect(call.method, 'previewVideo');
          expect(call.arguments['uri'], 'content://example/video');
          expect(call.arguments['hevc'], true);
          throw PlatformException(
            code: 'preview',
            message: 'Unsupported video',
          );
        });
    await tester.pumpWidget(
      const MaterialApp(
        home: VideoPreviewPage(
          uri: 'content://example/video',
          name: 'movie.mp4',
          hevcAvailable: true,
        ),
      ),
    );
    await tester.tap(find.text('Generate sample'));
    await tester.pumpAndSettle();
    expect(find.text('Unsupported video'), findsOneWidget);
    expect(find.textContaining('original stays untouched'), findsOneWidget);
  });
  testWidgets('shows both frames when sample creation succeeds', (
    tester,
  ) async {
    // A one-pixel PNG; the platform normally returns JPEG thumbnail bytes.
    final image = Uint8List.fromList([
      137,
      80,
      78,
      71,
      13,
      10,
      26,
      10,
      0,
      0,
      0,
      13,
      73,
      72,
      68,
      82,
      0,
      0,
      0,
      1,
      0,
      0,
      0,
      1,
      8,
      4,
      0,
      0,
      0,
      181,
      28,
      12,
      2,
      0,
      0,
      0,
      11,
      73,
      68,
      65,
      84,
      120,
      218,
      99,
      100,
      248,
      15,
      0,
      1,
      5,
      1,
      1,
      39,
      24,
      227,
      102,
      0,
      0,
      0,
      0,
      73,
      69,
      78,
      68,
      174,
      66,
      96,
      130,
    ]);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          channel,
          (call) async => {
            'originalFrame': image,
            'outputFrame': image,
            'sampleBytes': 1048576,
          },
        );
    await tester.pumpWidget(
      const MaterialApp(
        home: VideoPreviewPage(
          uri: 'content://example/video',
          name: 'movie.mp4',
          hevcAvailable: false,
        ),
      ),
    );
    await tester.tap(find.text('Generate sample'));
    await tester.pumpAndSettle();
    expect(find.text('Original'), findsOneWidget);
    expect(find.text('Sample'), findsOneWidget);
    expect(find.text('Sample size: 1.00 MB'), findsOneWidget);
  });
  testWidgets('prepares and saves a video copy', (tester) async {
    final image = Uint8List.fromList([
      137,
      80,
      78,
      71,
      13,
      10,
      26,
      10,
      0,
      0,
      0,
      13,
      73,
      72,
      68,
      82,
      0,
      0,
      0,
      1,
      0,
      0,
      0,
      1,
      8,
      4,
      0,
      0,
      0,
      181,
      28,
      12,
      2,
      0,
      0,
      0,
      11,
      73,
      68,
      65,
      84,
      120,
      218,
      99,
      100,
      248,
      15,
      0,
      1,
      5,
      1,
      1,
      39,
      24,
      227,
      102,
      0,
      0,
      0,
      0,
      73,
      69,
      78,
      68,
      174,
      66,
      96,
      130,
    ]);
    final calls = <String>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call.method);
          if (call.method == 'previewVideo') {
            return {
              'originalFrame': image,
              'outputFrame': image,
              'sampleBytes': 50,
            };
          }
          if (call.method == 'prepareVideoCopy') {
            expect(call.arguments['originalBytes'], 1000);
            expect(call.arguments['minimumSavings'], 20);
            expect(call.arguments['bitrate'], 3000000);
            return {'originalBytes': 1000, 'outputBytes': 500};
          }
          if (call.method == 'saveVideoCopy') return true;
          return null;
        });
    await tester.pumpWidget(
      const MaterialApp(
        home: VideoPreviewPage(
          uri: 'content://video/1',
          name: 'movie.mp4',
          hevcAvailable: true,
          originalBytes: 1000,
        ),
      ),
    );
    await tester.tap(find.text('Generate sample'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Prepare compressed copy'), 300);
    await tester.tap(find.text('Prepare compressed copy'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Save separate copy'), 300);
    await tester.tap(find.text('Save separate copy'));
    await tester.pumpAndSettle();
    expect(calls, ['previewVideo', 'prepareVideoCopy', 'saveVideoCopy']);
  });
}
