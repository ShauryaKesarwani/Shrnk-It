import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shrnk_it_mobile/features/jpeg_preview_page.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('shrnk_it/media');
  tearDown(
    () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null),
  );
  testWidgets(
    'passes selected quality and displays errors without changing the file',
    (tester) async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            expect(call.method, 'previewJpeg');
            expect(call.arguments['uri'], 'content://photo/1');
            expect(call.arguments['quality'], 85);
            throw PlatformException(
              code: 'preview',
              message: 'Cannot decode photo',
            );
          });
      await tester.pumpWidget(
        const MaterialApp(
          home: JpegPreviewPage(uri: 'content://photo/1', name: 'photo.jpg'),
        ),
      );
      await tester.tap(find.text('Generate sample'));
      await tester.pumpAndSettle();
      expect(find.text('Cannot decode photo'), findsOneWidget);
      expect(
        find.textContaining('does not change your original'),
        findsOneWidget,
      );
    },
  );
  testWidgets('prepares and saves a separate JPEG copy after preview', (
    tester,
  ) async {
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
          if (call.method == 'previewJpeg') {
            return {'originalFrame': image, 'outputFrame': image};
          }
          if (call.method == 'prepareJpegCopy') {
            expect(call.arguments['minimumSavings'], 20);
            return {'originalBytes': 1000, 'outputBytes': 500};
          }
          if (call.method == 'saveJpegCopy') return true;
          return null;
        });
    await tester.pumpWidget(
      const MaterialApp(
        home: JpegPreviewPage(uri: 'content://photo/1', name: 'photo.jpg'),
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
    expect(calls, ['previewJpeg', 'prepareJpegCopy', 'saveJpegCopy']);
  });
}
