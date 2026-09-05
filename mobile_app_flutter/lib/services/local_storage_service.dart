import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

class LocalStorageService {
  static const String _kCachedConversations = 'cached_conversations';
  static const String _kCachedMessagesPrefix = 'cached_messages_';
  static const String _kStarredSheets = 'starred_technical_sheets';

  // --- Sauvegarde des conversations & messages (Mode Hors-Ligne) ---

  Future<void> saveConversations(List<dynamic> conversations) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = jsonEncode(conversations);
      await prefs.setString(_kCachedConversations, jsonString);
    } catch (_) {}
  }

  Future<List<dynamic>> getCachedConversations() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = prefs.getString(_kCachedConversations);
      if (jsonString != null && jsonString.isNotEmpty) {
        return jsonDecode(jsonString) as List<dynamic>;
      }
    } catch (_) {}
    return [];
  }

  Future<void> saveMessages(String conversationId, List<Map<String, dynamic>> messages) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = jsonEncode(messages);
      await prefs.setString('$_kCachedMessagesPrefix$conversationId', jsonString);
    } catch (_) {}
  }

  Future<List<Map<String, dynamic>>> getCachedMessages(String conversationId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = prefs.getString('$_kCachedMessagesPrefix$conversationId');
      if (jsonString != null && jsonString.isNotEmpty) {
        final decoded = jsonDecode(jsonString) as List<dynamic>;
        return decoded.map((e) => Map<String, dynamic>.from(e as Map)).toList();
      }
    } catch (_) {}
    return [];
  }

  // --- Fiches Chantier Sauvegardées / Favoris Hors-Ligne ---

  Future<List<Map<String, dynamic>>> getStarredSheets() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = prefs.getString(_kStarredSheets);
      if (jsonString != null && jsonString.isNotEmpty) {
        final decoded = jsonDecode(jsonString) as List<dynamic>;
        return decoded.map((e) => Map<String, dynamic>.from(e as Map)).toList();
      }
    } catch (_) {}
    return [];
  }

  Future<void> saveStarredSheet(Map<String, dynamic> sheet) async {
    try {
      final sheets = await getStarredSheets();
      final id = sheet['id'] ?? DateTime.now().millisecondsSinceEpoch.toString();
      
      // Éviter les doublons
      sheets.removeWhere((item) => item['id'] == id);
      sheets.insert(0, {
        ...sheet,
        'id': id,
        'savedAt': DateTime.now().toIso8601String(),
      });

      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kStarredSheets, jsonEncode(sheets));
    } catch (_) {}
  }

  Future<void> removeStarredSheet(String sheetId) async {
    try {
      final sheets = await getStarredSheets();
      sheets.removeWhere((item) => item['id'] == sheetId);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kStarredSheets, jsonEncode(sheets));
    } catch (_) {}
  }

  Future<bool> isSheetStarred(String sheetId) async {
    final sheets = await getStarredSheets();
    return sheets.any((item) => item['id'] == sheetId);
  }
}
