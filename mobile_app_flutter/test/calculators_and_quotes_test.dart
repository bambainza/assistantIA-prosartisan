import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:prosartisan/network/network_client.dart';
import 'package:prosartisan/views/calculators_view.dart';
import 'package:prosartisan/views/quotes_view.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('QuoteItem & Devis Logic Tests', () {
    test('Calcul automatique des totaux de lignes et TVA', () {
      final item1 = QuoteItem(
        description: 'Disjoncteur 16A',
        quantite: 5,
        unite: 'u',
        prixUnitaire: 4500,
      );
      final item2 = QuoteItem(
        description: 'Rouleau câble 2.5mm²',
        quantite: 2,
        unite: 'rlx',
        prixUnitaire: 28000,
      );

      expect(item1.total, 22500);
      expect(item2.total, 56000);

      final totalHT = item1.total + item2.total;
      expect(totalHT, 78500);

      final tva = totalHT * 0.18;
      expect(tva, 14130);

      final ttc = totalHT + tva;
      expect(ttc, 92630);
    });

    test('Sérialisation JSON et désérialisation QuoteItem', () {
      final item = QuoteItem(
        description: 'Pose carrelage mural',
        quantite: 20,
        unite: 'm2',
        prixUnitaire: 4500,
      );

      final json = item.toJson();
      expect(json['description'], 'Pose carrelage mural');
      expect(json['quantite'], 20.0);
      expect(json['unite'], 'm2');
      expect(json['prix_unitaire'], 4500.0);

      final deserialized = QuoteItem.fromJson(json);
      expect(deserialized.description, item.description);
      expect(deserialized.total, 90000.0);
    });
  });

  group('Widgets UI Rendering Tests', () {
    testWidgets('CalculatorsView s\'affiche avec ses 5 onglets', (WidgetTester tester) async {
      final client = NetworkClient();

      await tester.pumpWidget(
        MaterialApp(
          home: CalculatorsView(networkClient: client),
        ),
      );

      await tester.pumpAndSettle();

      expect(find.text("🧮 Calculateurs Normés"), findsOneWidget);
      expect(find.text("Béton & Mortier"), findsOneWidget);
      expect(find.text("Câblage Élec"), findsOneWidget);
      expect(find.text("Pente Évacuation"), findsOneWidget);
      expect(find.text("Carrelage"), findsOneWidget);
      expect(find.text("Climatisation"), findsOneWidget);
    });

    testWidgets('QuotesView s\'affiche avec le bouton d\'extraction IA', (WidgetTester tester) async {
      final client = NetworkClient();

      await tester.pumpWidget(
        MaterialApp(
          home: QuotesView(networkClient: client),
        ),
      );

      await tester.pumpAndSettle();

      expect(find.text("📄 Devis & Factures Express"), findsOneWidget);
      expect(find.text("✨ Saisie rapide / Notes de chantier"), findsOneWidget);
      expect(find.text("Analyser & Chiffrer automatiquement"), findsOneWidget);
      expect(find.text("Total HT :"), findsOneWidget);
      expect(find.text("Total TTC :"), findsOneWidget);
      expect(find.text("WhatsApp"), findsOneWidget);
    });
  });
}
