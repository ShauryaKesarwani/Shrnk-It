import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shrnk_it_mobile/features/backups_page.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('shrnk_it/media');
  tearDown(
    () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null),
  );
  testWidgets('lists recorded backups and exposes their identity', (
    tester,
  ) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'restoreBackupCopy') {
            expect(call.arguments['uri'], 'content://backup/1');
            expect(call.arguments['sha256'], 'abc');
            return true;
          }
          return [
            {
              'name': 'photo.jpg',
              'backup': 'content://backup/1',
              'bytes': 1048576,
              'created': 0,
              'sha256': 'abc',
            },
          ];
        });
    await tester.pumpWidget(const MaterialApp(home: BackupsPage()));
    await tester.pumpAndSettle();
    expect(find.text('photo.jpg'), findsOneWidget);
    await tester.tap(find.text('photo.jpg'));
    await tester.pumpAndSettle();
    expect(find.textContaining('content://backup/1'), findsOneWidget);
    expect(find.textContaining('abc'), findsOneWidget);
    await tester.tap(find.text('Restore a copy'));
    await tester.pumpAndSettle();
    expect(find.text('Restored copy verified.'), findsOneWidget);
  });
}
