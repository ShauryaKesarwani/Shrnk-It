import 'package:flutter/material.dart';
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
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -400));
    await tester.pumpAndSettle();
    expect(
      find.textContaining(
        'In-place replacement and restore are still being built',
      ),
      findsOneWidget,
    );
  });
}
