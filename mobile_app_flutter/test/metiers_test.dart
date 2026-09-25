import 'package:flutter_test/flutter_test.dart';
import 'package:prosartisan/network/network_client.dart';
import 'package:prosartisan/viewmodels/chat_viewmodel.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Client simulé : `/api/metiers` renvoie la liste donnée (vide = hors-ligne).
class _ClientMetiers extends NetworkClient {
  _ClientMetiers(this.reponses);

  final List<List<Map<String, dynamic>>> reponses;

  @override
  Future<List<Map<String, dynamic>>> getMetiers() async =>
      reponses.isEmpty ? [] : reponses.removeAt(0);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('Par défaut : tous les métiers (aucun filtre codé en dur)', () {
    final vm = ChatViewModel(_ClientMetiers([]), autoInitialize: false);

    expect(vm.activeMetierId, isNull);
  });

  test('Les métiers viennent du serveur ; un métier désactivé est désélectionné', () async {
    final vm = ChatViewModel(
      _ClientMetiers([
        [
          {'id': 13, 'nom': 'Bâtiment & Construction', 'slug': 'batiment'},
          {'id': 2, 'nom': 'Électricité & Énergie', 'slug': 'electricite'},
        ],
        [
          {'id': 2, 'nom': 'Électricité & Énergie', 'slug': 'electricite'},
        ],
      ]),
      autoInitialize: false,
    );

    await vm.refreshMetiers();
    expect(vm.metiers.map((m) => m['id']), [13, 2]);

    vm.selectMetier(13);
    await vm.refreshMetiers(); // 13 désactivé côté serveur
    expect(vm.activeMetierId, isNull);
    expect(vm.metiers.map((m) => m['id']), [2]);

    await vm.refreshMetiers(); // hors-ligne : la dernière liste est conservée
    expect(vm.metiers.map((m) => m['id']), [2]);
  });
}
