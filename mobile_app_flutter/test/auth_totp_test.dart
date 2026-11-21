import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:prosartisan/network/network_client.dart';
import 'package:prosartisan/viewmodels/chat_viewmodel.dart';
import 'package:prosartisan/views/auth_view.dart';

class _TotpClient extends NetworkClient {
  String? receivedCode;

  @override
  Future<Map<String, dynamic>> login(String email, String password,
      {String? totpCode}) async {
    receivedCode = totpCode;
    return {'success': false, 'error': 'Code invalide'};
  }
}

void main() {
  testWidgets('Le formulaire transmet le second facteur sans connecter sur erreur',
      (tester) async {
    final client = _TotpClient();
    final model = ChatViewModel(client, autoInitialize: false);
    await tester.pumpWidget(ChangeNotifierProvider.value(
      value: model,
      child: const MaterialApp(home: AuthView()),
    ));
    final fields = find.byType(TextField);
    await tester.enterText(fields.at(0), 'admin@example.com');
    await tester.enterText(fields.at(1), 'password');
    await tester.enterText(fields.at(2), '123456');
    await tester.ensureVisible(find.widgetWithText(ElevatedButton, 'Se connecter'));
    await tester.tap(find.widgetWithText(ElevatedButton, 'Se connecter'));
    await tester.pumpAndSettle();
    expect(client.receivedCode, '123456');
    expect(find.text('Code invalide'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    model.dispose();
  });
}
