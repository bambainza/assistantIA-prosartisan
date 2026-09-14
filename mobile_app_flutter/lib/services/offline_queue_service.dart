import 'package:hive_flutter/hive_flutter.dart';

/// File d'attente locale des questions posées sans réseau (Hive).
///
/// Une question qui échoue faute de réseau est mise en file ici plutôt que
/// simplement perdue ; elle est rejouée automatiquement dès que la
/// connectivité revient (voir `ChatViewModel.flushOfflineQueue`). Limite
/// connue : seul le texte de la question est conservé, pas une éventuelle
/// photo jointe (les pièces jointes ne sont pas mises en file dans cette
/// première version — voir docs/PLAN_AMELIORATION.md, item 4.3).
class OfflineQueueService {
  static const String _boxName = 'offline_message_queue';
  Box? _box;

  Future<void> init() async {
    try {
      await Hive.initFlutter();
      _box = Hive.isBoxOpen(_boxName)
          ? Hive.box(_boxName)
          : await Hive.openBox(_boxName);
    } catch (_) {
      // Stockage local indisponible (plateforme non supportée, permissions...) :
      // la file d'attente est simplement désactivée, jamais un crash.
      _box = null;
    }
  }

  Future<void> enqueue(String question, int? metierId, String? conversationId) async {
    if (_box == null || question.trim().isEmpty) return;
    final id = DateTime.now().millisecondsSinceEpoch.toString();
    await _box!.put(id, {
      'id': id,
      'question': question,
      'metierId': metierId,
      'conversationId': conversationId,
      'queuedAt': DateTime.now().toIso8601String(),
    });
  }

  List<Map<String, dynamic>> getAll() {
    if (_box == null) return [];
    final entries = _box!.values
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    entries.sort(
      (a, b) => (a['queuedAt'] as String).compareTo(b['queuedAt'] as String),
    );
    return entries;
  }

  int get pendingCount => _box?.length ?? 0;

  Future<void> removeById(String id) async {
    await _box?.delete(id);
  }
}
