import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:prosartisan/network/network_client.dart';
import 'package:prosartisan/viewmodels/chat_viewmodel.dart';
import 'package:prosartisan/views/paywall_dialog.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Client simulé : le serveur répond 402 (quota épuisé) à toute question.
class _ClientQuotaEpuise extends NetworkClient {
  @override
  Stream<String> sendMessageStream(
    String message,
    String? conversationId,
    int? metierId, {
    String? imageUrl,
  }) async* {
    throw const QuotaEpuiseException();
  }

  @override
  Future<List<dynamic>> getConversations() async => [];
}

Future<void> _ouvrirPaywall(
  WidgetTester tester, {
  required Future<Map<String, dynamic>> Function(String, String) startPayment,
  required Future<String?> Function(String) checkPayment,
  required Future<bool> Function(Uri) openUrl,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: PaywallDialog(
          onDismiss: () {},
          startPayment: startPayment,
          checkPayment: checkPayment,
          openUrl: openUrl,
          pollInterval: const Duration(milliseconds: 10),
        ),
      ),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('Paywall : paiement Wave ouvert puis confirmé par le suivi', (tester) async {
    final demandes = <List<String>>[];
    final urlsOuvertes = <Uri>[];
    var appels = 0;

    await _ouvrirPaywall(
      tester,
      startPayment: (typePass, operateur) async {
        demandes.add([typePass, operateur]);
        return {
          'payment_url': 'http://localhost:8000/api/payment/demo/checkout/cos-1',
          'transaction_id': 'txn-1',
        };
      },
      checkPayment: (id) async => ++appels < 2 ? 'PENDING' : 'ACCEPTED',
      openUrl: (url) async {
        urlsOuvertes.add(url);
        return true;
      },
    );

    await tester.tap(find.byKey(const Key('offre-pass_mois')));
    await tester.pump();
    await tester.tap(find.text('Payer avec Wave'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump(const Duration(milliseconds: 50));

    expect(demandes, [
      ['pass_mois', 'WAVE'],
    ]);
    expect(urlsOuvertes.single.path, '/api/payment/demo/checkout/cos-1');
    expect(find.textContaining('Paiement confirmé'), findsOneWidget);
    expect(find.text('Continuer'), findsOneWidget);
  });

  testWidgets('Paywall : erreur serveur affichée, aucune page ouverte', (tester) async {
    final urlsOuvertes = <Uri>[];
    await _ouvrirPaywall(
      tester,
      startPayment: (_, __) async => {'error': 'Paiement Mobile Money bientôt disponible.'},
      checkPayment: (_) async => null,
      openUrl: (url) async {
        urlsOuvertes.add(url);
        return true;
      },
    );

    await tester.tap(find.text('Payer avec Orange Money'));
    await tester.pump();

    expect(find.text('Paiement Mobile Money bientôt disponible.'), findsOneWidget);
    expect(urlsOuvertes, isEmpty);
  });

  testWidgets('Paywall : paiement refusé chez l\'opérateur', (tester) async {
    await _ouvrirPaywall(
      tester,
      startPayment: (_, __) async => {
        'payment_url': 'https://pay.example/1',
        'transaction_id': 'txn-2',
      },
      checkPayment: (_) async => 'FAILED',
      openUrl: (_) async => true,
    );

    await tester.tap(find.text('Payer avec Orange Money'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.textContaining('refusé ou expiré'), findsOneWidget);
  });

  test('Quota épuisé (402) : paywall affiché, question non mise en file hors-ligne', () async {
    final viewModel = ChatViewModel(_ClientQuotaEpuise(), autoInitialize: false);

    await viewModel.sendMessage('Dosage béton pour une dalle ?');

    expect(viewModel.showPaywall, isTrue);
    expect(viewModel.isOffline, isFalse);
    expect(viewModel.pendingOfflineCount, 0);
  });
}
