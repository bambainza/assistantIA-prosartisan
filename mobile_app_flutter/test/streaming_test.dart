import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:prosartisan/network/network_client.dart';
import 'package:prosartisan/viewmodels/chat_viewmodel.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Flux SSE tel que l'envoie `/api/chat/stream` (lignes `event:` / `data:`).
Stream<String> _lignes(List<String> lignes) => Stream.fromIterable(lignes);

/// Client simulé : rejoue les `data:` d'un flux serveur via `lireFluxSse`.
class _ClientFlux extends NetworkClient {
  _ClientFlux(this.lignes);

  final List<String> lignes;

  @override
  Stream<String> sendMessageStream(
    String message,
    String? conversationId,
    int? metierId, {
    String? imageUrl,
  }) =>
      lireFluxSse(_lignes(lignes));

  @override
  Future<List<dynamic>> getConversations() async => [];
}

List<String> _fluxReponse(List<String> morceaux) => [
      'event: info',
      'data: ${jsonEncode({'conversation_id': null, 'sources': []})}',
      '',
      for (final m in morceaux) ...['event: chunk', 'data: ${jsonEncode(m)}', ''],
      'event: end',
      'data: [DONE]',
      '',
    ];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('lireFluxSse renvoie les data jusqu\'à [DONE]', () async {
    final data = await lireFluxSse(_lignes(_fluxReponse(['Bon', 'jour']))).toList();

    expect(data.length, 3); // info + 2 morceaux
    expect(jsonDecode(data[1]), 'Bon');
    expect(jsonDecode(data[2]), 'jour');
  });

  test('lireFluxSse lève AssistantIndisponibleException sur event: error', () async {
    final flux = lireFluxSse(_lignes([
      'event: error',
      'data: ${jsonEncode("Assistant indisponible.")}',
      '',
      'event: end',
      'data: [DONE]',
    ]));

    await expectLater(
      flux.toList(),
      throwsA(isA<AssistantIndisponibleException>()
          .having((e) => e.message, 'message', 'Assistant indisponible.')),
    );
  });

  test('La réponse streamée (chaînes JSON) s\'affiche en entier', () async {
    final viewModel = ChatViewModel(
      _ClientFlux(_fluxReponse(['Dosez ', '350 kg', ' de ciment.'])),
      autoInitialize: false,
    );

    await viewModel.sendMessage('Dosage béton pour une dalle ?');

    final reponse = viewModel.messages.last;
    expect(reponse['role'], 'assistant');
    expect(reponse['content'], 'Dosez 350 kg de ciment.');
    expect(viewModel.chatError, isNull);
  });

  test('Panne de l\'IA : message clair, pas de mise en file hors-ligne', () async {
    final viewModel = ChatViewModel(
      _ClientFlux([
        'event: error',
        'data: ${jsonEncode("L'assistant est momentanément indisponible.")}',
        'data: [DONE]',
      ]),
      autoInitialize: false,
    );

    await viewModel.sendMessage('Dosage béton pour une dalle ?');

    expect(viewModel.chatError, "L'assistant est momentanément indisponible.");
    expect(viewModel.isOffline, isFalse);
    expect(viewModel.pendingOfflineCount, 0);
    expect(viewModel.messages.where((m) => m['role'] == 'assistant'), isEmpty);
  });
}
