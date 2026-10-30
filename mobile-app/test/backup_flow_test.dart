import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shrnk_it_mobile/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('shrnk_it/media');
  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });
  testWidgets('selects a folder before backing up selected media', (
    tester,
  ) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    final calls = <String>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call.method);
          switch (call.method) {
            case 'wallpaperAccent':
              return null;
            case 'codecSupport':
              return <String, dynamic>{'hevcEncoder': false};
            case 'pickMedia':
              return [
                <String, dynamic>{
                  'uri': 'content://media/1',
                  'name': 'photo.jpg',
                  'type': 'image/jpeg',
                  'size': 1024,
                },
              ];
            case 'hasBackupFolder':
              return false;
            case 'chooseBackupFolder':
              return true;
            case 'backupMedia':
              expect(call.arguments['uri'], 'content://media/1');
              return 1024;
          }
          return null;
        });
    await tester.pumpWidget(const ShrnkApp());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Choose photos & videos'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Back up selected files'),
      300,
      scrollable: find
          .descendant(
            of: find.byType(ListView).first,
            matching: find.byType(Scrollable),
          )
          .first,
    );
    await tester.tap(find.text('Back up selected files'));
    await tester.pumpAndSettle();
    expect(
      calls.where(
        (call) => [
          'hasBackupFolder',
          'chooseBackupFolder',
          'backupMedia',
        ].contains(call),
      ),
      ['hasBackupFolder', 'chooseBackupFolder', 'backupMedia'],
    );
    expect(find.textContaining('1 backup(s) verified'), findsOneWidget);
    debugDefaultTargetPlatformOverride = null;
  });
}
