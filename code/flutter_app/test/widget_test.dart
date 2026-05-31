import 'package:flutter_test/flutter_test.dart';
import 'package:smart_home_flutter_app/main.dart';

void main() {
  testWidgets('Smart Home app starts', (tester) async {
    await tester.pumpWidget(const SmartHomeApp());
    await tester.pump();
    expect(find.text('Smart Home'), findsWidgets);
  });
}
