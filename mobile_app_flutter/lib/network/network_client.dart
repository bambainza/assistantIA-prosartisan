import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:shared_preferences/shared_preferences.dart';

class NetworkClient {
  String _baseUrl = 'http://localhost:8000';
  String? _token;
  String? _userEmail;

  String get baseUrl => _baseUrl;
  set baseUrl(String url) {
    _baseUrl = url;
    _saveSettings();
  }

  String? get token => _token;
  String? get userEmail => _userEmail;

  NetworkClient() {
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString('baseUrl') ?? 'http://localhost:8000';
    _token = prefs.getString('token');
    _userEmail = prefs.getString('userEmail');
  }

  Future<void> _saveSettings() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('baseUrl', _baseUrl);
    if (_token != null) {
      await prefs.setString('token', _token!);
    } else {
      await prefs.remove('token');
    }
    if (_userEmail != null) {
      await prefs.setString('userEmail', _userEmail!);
    } else {
      await prefs.remove('userEmail');
    }
  }

  Future<void> saveSession(String token, String email) async {
    _token = token;
    _userEmail = email;
    await _saveSettings();
  }

  Future<void> clearSession() async {
    _token = null;
    _userEmail = null;
    await _saveSettings();
  }

  // --- Auto-détection de l'IP Serveur ---
  Future<String> autoDetectBaseUrl() async {
    final List<String> candidates = [
      'http://10.0.2.2:8000', // Émulateur Android
      'http://localhost:8000',
      'http://127.0.0.1:8000',
      'http://192.168.100.2:8000', // IP locale du PC de dev
      'http://192.168.1.100:8000',
    ];

    final completer = Completer<String>();
    int completedCount = 0;
    bool successFound = false;

    void checkUrl(String url) async {
      try {
        final client = HttpClient();
        client.connectionTimeout = const Duration(milliseconds: 1200);
        final uri = Uri.parse('$url/api/health');
        final request = await client.getUrl(uri);
        final response = await request.close();
        
        if (response.statusCode == 200 && !successFound) {
          successFound = true;
          baseUrl = url;
          completer.complete(url);
        }
      } catch (_) {
        // Ignorer l'erreur, l'URL est juste injoignable
      } finally {
        completedCount++;
        if (completedCount == candidates.length && !successFound && !completer.isCompleted) {
          completer.complete(_baseUrl); // Retourne la dernière connue par défaut
        }
      }
    }

    for (final url in candidates) {
      checkUrl(url);
    }

    return completer.future;
  }

  // --- Authentification ---
  Future<Map<String, dynamic>> login(String email, String password) async {
    final client = HttpClient();
    try {
      final uri = Uri.parse('$_baseUrl/api/auth/token');
      final request = await client.postUrl(uri);
      request.headers.set('content-type', 'application/x-www-form-urlencoded');

      final body = 'username=${Uri.encodeComponent(email)}&password=${Uri.encodeComponent(password)}';
      request.write(body);

      final response = await request.close();
      final responseBody = await response.transform(utf8.decoder).join();
      final data = jsonDecode(responseBody);

      if (response.statusCode == 200) {
        final token = data['access_token'];
        await saveSession(token, email);
        return {'success': true, 'data': data};
      } else {
        return {'success': false, 'error': data['detail'] ?? 'Identifiants invalides'};
      }
    } catch (e) {
      return {'success': false, 'error': 'Impossible de se connecter au serveur : $e'};
    } finally {
      client.close();
    }
  }

  Future<Map<String, dynamic>> register(String email, String password, String name, String phone) async {
    final client = HttpClient();
    try {
      final uri = Uri.parse('$_baseUrl/api/auth/register');
      final request = await client.postUrl(uri);
      request.headers.set('content-type', 'application/json');

      final body = jsonEncode({
        'email': email,
        'password': password,
        'nom': name,
        'telephone': phone.isEmpty ? null : phone,
      });
      request.write(body);

      final response = await request.close();
      final responseBody = await response.transform(utf8.decoder).join();
      final data = jsonDecode(responseBody);

      if (response.statusCode == 200 || response.statusCode == 201) {
        return {'success': true, 'data': data};
      } else {
        return {'success': false, 'error': data['detail'] ?? 'Échec de l\'inscription'};
      }
    } catch (e) {
      return {'success': false, 'error': 'Impossible de joindre le serveur : $e'};
    } finally {
      client.close();
    }
  }

  // --- Conversations ---
  Future<List<dynamic>> getConversations() async {
    final client = HttpClient();
    try {
      final uri = Uri.parse('$_baseUrl/api/conversations');
      final request = await client.getUrl(uri);
      if (_token != null) {
        request.headers.set('authorization', 'Bearer $_token');
      }

      final response = await request.close();
      final responseBody = await response.transform(utf8.decoder).join();
      if (response.statusCode == 200) {
        return jsonDecode(responseBody) as List;
      }
      return [];
    } catch (_) {
      return [];
    } finally {
      client.close();
    }
  }

  Future<Map<String, dynamic>?> getConversationDetail(String convId) async {
    final client = HttpClient();
    try {
      final uri = Uri.parse('$_baseUrl/api/conversations/$convId');
      final request = await client.getUrl(uri);
      if (_token != null) {
        request.headers.set('authorization', 'Bearer $_token');
      }

      final response = await request.close();
      final responseBody = await response.transform(utf8.decoder).join();
      if (response.statusCode == 200) {
        return jsonDecode(responseBody) as Map<String, dynamic>;
      }
      return null;
    } catch (_) {
      return null;
    } finally {
      client.close();
    }
  }

  Future<bool> deleteConversation(String convId) async {
    final client = HttpClient();
    try {
      final uri = Uri.parse('$_baseUrl/api/conversations/$convId');
      final request = await client.deleteUrl(uri);
      if (_token != null) {
        request.headers.set('authorization', 'Bearer $_token');
      }

      final response = await request.close();
      return response.statusCode == 200;
    } catch (_) {
      return false;
    } finally {
      client.close();
    }
  }

  Future<Map<String, dynamic>> getQuota() async {
    final client = HttpClient();
    try {
      final uri = Uri.parse('$_baseUrl/api/quota');
      final request = await client.getUrl(uri);
      if (_token != null) {
        request.headers.set('authorization', 'Bearer $_token');
      }

      final response = await request.close();
      final responseBody = await response.transform(utf8.decoder).join();
      if (response.statusCode == 200) {
        return jsonDecode(responseBody) as Map<String, dynamic>;
      }
      return {'quota_restant': 0};
    } catch (_) {
      return {'quota_restant': 0};
    } finally {
      client.close();
    }
  }

  // --- SSE Chat Streaming ---
  Stream<String> sendMessageStream(String message, String? conversationId, int? metierId) async* {
    final client = HttpClient();
    client.connectionTimeout = const Duration(seconds: 10);
    try {
      final uri = Uri.parse('$_baseUrl/api/chat/stream');
      final request = await client.postUrl(uri);
      
      request.headers.set('content-type', 'application/json');
      if (_token != null) {
        request.headers.set('authorization', 'Bearer $_token');
      }
      
      final body = {
        'message': message,
        'conversation_id': conversationId,
        'metier_id': metierId,
      };
      
      request.write(jsonEncode(body));
      final response = await request.close();
      
      if (response.statusCode != 200) {
        throw Exception('Serveur indisponible (code ${response.statusCode})');
      }
      
      // Lire ligne par ligne (SSE)
      await for (final line in response
          .transform(utf8.decoder)
          .transform(const LineSplitter())) {
        
        final trimmed = line.trim();
        if (trimmed.startsWith('data: ')) {
          final data = trimmed.substring(6).trim();
          if (data == '[DONE]') {
            break;
          }
          yield data;
        }
      }
    } finally {
      client.close();
    }
  }
}
