import 'package:flutter_test/flutter_test.dart';
import 'package:shrnk_it_mobile/main.dart';

void main() {
  testWidgets('shows selection and accurately describes unavailable features', (
    tester,
  ) async {
    await tester.pumpWidget(const ShrnkApp());
    expect(find.text('Your media'), findsOneWidget);
    expect(find.text('Choose photos & videos'), findsOneWidget);
    expect(find.text('Nothing selected yet'), findsOneWidget);
    expect(
      find.textContaining('Compression and backups are still being built'),
      findsOneWidget,
    );
  });
}
