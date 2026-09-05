import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:prosartisan/services/local_storage_service.dart';
import 'package:prosartisan/viewmodels/chat_viewmodel.dart';
import 'package:prosartisan/network/network_client.dart';
import 'package:prosartisan/views/offline_sheets_view.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('LocalStorageService (Mode Hors-Ligne & Fiches)', () {
    test('Sauvegarde et récupération des conversations en cache', () async {
      final storage = LocalStorageService();
      final convs = [
        {'id': 'conv_1', 'title': 'Dosage béton C25'},
        {'id': 'conv_2', 'title': 'Câblage disjoncteur différentiel'},
      ];

      await storage.saveConversations(convs);
      final retrieved = await storage.getCachedConversations();

      expect(retrieved.length, 2);
      expect(retrieved[0]['title'], 'Dosage béton C25');
    });

    test('Sauvegarde et récupération des messages en cache', () async {
      final storage = LocalStorageService();
      final messages = [
        {'id': 'msg_1', 'role': 'user', 'content': 'Quel sable pour mortier ?'},
        {'id': 'msg_2', 'role': 'assistant', 'content': 'Utilisez du sable de rivière 0/4mm.'},
      ];

      await storage.saveMessages('conv_123', messages);
      final retrieved = await storage.getCachedMessages('conv_123');

      expect(retrieved.length, 2);
      expect(retrieved[1]['role'], 'assistant');
      expect(retrieved[1]['content'], contains('sable de rivière'));
    });

    test('Épinglage, vérification et suppression des Fiches Chantier', () async {
      final storage = LocalStorageService();
      final sheet = {
        'id': 'sheet_456',
        'title': 'Règle DTU 20.1 Maçonnerie',
        'content': 'Dosage 350 kg/m3 pour semelles filantes.',
        'metier_id': 1,
      };

      expect(await storage.isSheetStarred('sheet_456'), isFalse);

      await storage.saveStarredSheet(sheet);
      expect(await storage.isSheetStarred('sheet_456'), isTrue);

      final sheets = await storage.getStarredSheets();
      expect(sheets.length, 1);
      expect(sheets.first['title'], 'Règle DTU 20.1 Maçonnerie');

      await storage.removeStarredSheet('sheet_456');
      expect(await storage.isSheetStarred('sheet_456'), isFalse);
    });
  });

  group('ChatViewModel (Gestion Métier, Thème & Photo)', () {
    test('Sélection de métier et bascule de thème', () async {
      final client = NetworkClient();
      final vm = ChatViewModel(client, autoInitialize: false);

      expect(vm.isDarkTheme, isTrue);
      vm.toggleTheme();
      expect(vm.isDarkTheme, isFalse);

      vm.selectMetier(3); // Plomberie
      expect(vm.activeMetierId, 3);
    });

    test('Gestion des Fiches Chantier dans le ViewModel', () async {
      final client = NetworkClient();
      final vm = ChatViewModel(client, autoInitialize: false);

      final msg = {
        'id': 'msg_test_1',
        'role': 'assistant',
        'content': 'Calcul de pente d\'évacuation : minimum 1 cm par mètre.',
      };

      expect(vm.isSheetStarred('msg_test_1'), isFalse);
      await vm.toggleStarSheet(msg, customTitle: 'Pente évacuation');

      expect(vm.isSheetStarred('msg_test_1'), isTrue);
      expect(vm.starredSheets.length, 1);
      expect(vm.starredSheets.first['title'], 'Pente évacuation');

      await vm.removeStarredSheet('msg_test_1');
      expect(vm.isSheetStarred('msg_test_1'), isFalse);
    });
  });

  group('OfflineSheetsView (Widget Test)', () {
    testWidgets('Affiche le message vide puis la fiche épinglée', (tester) async {
      final client = NetworkClient();
      final vm = ChatViewModel(client, autoInitialize: false);

      await tester.pumpWidget(
        ChangeNotifierProvider<ChatViewModel>.value(
          value: vm,
          child: const MaterialApp(
            home: OfflineSheetsView(),
          ),
        ),
      );

      // Vérifier l'état vide initial
      expect(find.text('Aucune fiche épinglée'), findsOneWidget);

      // Ajouter une fiche
      await vm.toggleStarSheet({
        'id': 'fiche_btp_1',
        'role': 'assistant',
        'content': 'Norme NF C 15-100 : Disjoncteur 16A max pour 8 prises 1.5mm².',
      }, customTitle: 'Section câbles prises');

      await tester.pumpAndSettle();

      // Vérifier que la fiche est affichée
      expect(find.text('Section câbles prises'), findsOneWidget);
      expect(find.textContaining('Norme NF C 15-100'), findsOneWidget);
      expect(find.text('Écouter la fiche'), findsOneWidget);
    });
  });
}
