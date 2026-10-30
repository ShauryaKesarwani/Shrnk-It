import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shrnk_it_mobile/features/media_browser_page.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('shrnk_it/media');
  tearDown(
    () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null),
  );
  testWidgets('searches indexed media and filters by folder', (tester) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          channel,
          (call) async => [
            {
              'uri': 'a',
              'name': 'photo.jpg',
              'size': 100,
              'type': 'image/jpeg',
              'folder': 'DCIM/Camera/',
            },
            {
              'uri': 'b',
              'name': 'movie.mp4',
              'size': 1000,
              'type': 'video/mp4',
              'folder': 'Movies/',
            },
          ],
        );
    await tester.pumpWidget(const MaterialApp(home: MediaBrowserPage()));
    await tester.pumpAndSettle();
    expect(find.text('photo.jpg'), findsOneWidget);
    expect(find.text('movie.mp4'), findsOneWidget);
    await tester.tap(find.text('DCIM/Camera'));
    await tester.pumpAndSettle();
    expect(find.text('photo.jpg'), findsOneWidget);
    expect(find.text('movie.mp4'), findsNothing);
    await tester.enterText(find.byType(SearchBar), 'missing');
    await tester.pumpAndSettle();
    expect(find.text('No matching media available.'), findsOneWidget);
  });
}
