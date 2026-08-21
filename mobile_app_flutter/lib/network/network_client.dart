import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:shared_preferences/shared_preferences.dart';

class NetworkClient {
  String _baseUrl = 'https://assistantia-prosartisan.onrender.com';
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
    _baseUrl = prefs.getString('baseUrl') ?? 'https://assistantia-prosartisan.onrender.com';
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
  // URL du serveur de production par défaut
  static const String productionUrl = 'https://assistantia-prosartisan.onrender.com';

  // --- Auto-détection de l'IP Serveur ---
  Future<String> autoDetectBaseUrl() async {
    // 1. Tester la production en priorité avec un timeout très court si on a une connexion
    try {
      final client = HttpClient();
      client.connectionTimeout = const Duration(milliseconds: 1500);
      final uri = Uri.parse('$productionUrl/health');
      final request = await client.getUrl(uri);
      final response = await request.close();
      if (response.statusCode == 200) {
        baseUrl = productionUrl;
        return productionUrl;
      }
    } catch (_) {
      // Échec de la production ou pas d'internet, on cherche le serveur local
    }

    // 2. Chercher l'IP locale pour déduire le sous-réseau
    String? localIp;
    try {
      for (var interface in await NetworkInterface.list()) {
        for (var addr in interface.addresses) {
          if (addr.type == InternetAddressType.IPv4 && !addr.isLoopback) {
            localIp = addr.address;
            break;
          }
        }
        if (localIp != null) break;
      }
    } catch (_) {}

    final List<String> candidates = [
      'http://10.0.2.2:8000', // Émulateur Android
      'http://localhost:8000',
      'http://127.0.0.1:8000',
    ];

    // Si on a trouvé une IP locale privée, on scanne tout son sous-réseau /24
    if (localIp != null) {
      final parts = localIp.split('.');
      if (parts.length == 4) {
        final firstOctet = int.tryParse(parts[0]);
        final secondOctet = int.tryParse(parts[1]);
        
        bool isPrivate = false;
        if (firstOctet == 10) {
          isPrivate = true;
        } else if (firstOctet == 172 && secondOctet != null && secondOctet >= 16 && secondOctet <= 31) {
          isPrivate = true;
        } else if (firstOctet == 192 && secondOctet == 168) {
          isPrivate = true;
        }

        if (isPrivate) {
          final subnet = '${parts[0]}.${parts[1]}.${parts[2]}';
          // Ajouter d'abord les IP les plus probables (.1, .2, .3, .4, .5, .100, .101, .102, .103, et l'IP courante)
          final List<int> preferredIps = [1, 2, 3, 4, 5, 100, 101, 102, 103, int.parse(parts[3])];
          for (final ip in preferredIps) {
            candidates.add('http://$subnet.$ip:8000');
          }
          // Ajouter toutes les autres IP du sous-réseau en repli
          for (int i = 1; i <= 254; i++) {
            final ipStr = 'http://$subnet.$i:8000';
            if (!candidates.contains(ipStr)) {
              candidates.add(ipStr);
            }
          }
        }
      }
    } else {
      // Hôtes locaux par défaut au cas où
      candidates.addAll([
        'http://192.168.1.100:8000',
        'http://192.168.1.2:8000',
        'http://192.168.1.3:8000',
        'http://192.168.100.2:8000',
        'http://192.168.0.100:8000',
      ]);
    }

    final completer = Completer<String>();
    int completedCount = 0;
    bool successFound = false;

    void checkUrl(String url) async {
      try {
        final client = HttpClient();
        // Timeout très agressif pour scanner en parallèle sans lenteur
        client.connectionTimeout = const Duration(milliseconds: 900);
        final uri = Uri.parse('$url/health');
        final request = await client.getUrl(uri);
        final response = await request.close();
        
        if (response.statusCode == 200 && !successFound) {
          successFound = true;
          baseUrl = url;
          if (!completer.isCompleted) {
            completer.complete(url);
          }
        }
      } catch (_) {
        // Injoignable
      } finally {
        completedCount++;
        if (completedCount == candidates.length && !successFound && !completer.isCompleted) {
          // Si rien n'est trouvé, on tente de se connecter à la production par défaut (ou la dernière connue)
          completer.complete(productionUrl);
        }
      }
    }

    for (final url in candidates) {
      checkUrl(url);
    }

    // Sécurité : timeout global pour ne pas bloquer l'appli indéfiniment si le scan est lent
    Future.delayed(const Duration(seconds: 4), () {
      if (!completer.isCompleted) {
        completer.complete(successFound ? _baseUrl : productionUrl);
      }
    });

    return completer.future;
  }
  Future<Map<String, dynamic>> login(String email, String password) async {
    final client = HttpClient();
    try {
      final uri = Uri.parse('$_baseUrl/api/auth/login');
      final request = await client.postUrl(uri);
      request.headers.set('content-type', 'application/json');

      final body = jsonEncode({
        'email': email,
        'password': password,
      });
      request.write(body);

      final response = await request.close();
      final responseBody = await response.transform(utf8.decoder).join();
      
      dynamic data;
      try {
        data = json.decode(responseBody);
      } catch (_) {
        return {
          'success': false,
          'error': 'Le serveur a renvoyé une réponse invalide (HTTP ${response.statusCode} Not Found).\n[Serveur ciblé : $_baseUrl]'
        };
      }

      if (response.statusCode == 200) {
        final token = data['access_token'];
        await saveSession(token, email);
        return {'success': true, 'data': data};
      } else {
        return {'success': false, 'error': data['detail'] ?? 'Identifiants invalides'};
      }
    } catch (e) {
      return {'success': false, 'error': 'Impossible de se connecter au serveur : $e\n[Serveur ciblé : $_baseUrl]'};
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
      
      dynamic data;
      try {
        data = json.decode(responseBody);
      } catch (_) {
        return {
          'success': false,
          'error': 'Le serveur a renvoyé une réponse invalide (HTTP ${response.statusCode} Not Found).\n[Serveur ciblé : $_baseUrl]'
        };
      }

      if (response.statusCode == 200 || response.statusCode == 201) {
        return {'success': true, 'data': data};
      } else {
        return {'success': false, 'error': data['detail'] ?? 'Échec de l\'inscription'};
      }
    } catch (e) {
      return {'success': false, 'error': 'Impossible de joindre le serveur : $e\n[Serveur ciblé : $_baseUrl]'};
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
