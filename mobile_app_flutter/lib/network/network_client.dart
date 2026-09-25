import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:dio/dio.dart';

/// Quota de questions épuisé (HTTP 402) : l'interface doit proposer un Pass,
/// et surtout ne pas traiter l'erreur comme une coupure réseau (sinon la
/// question serait remise en file hors-ligne et rejouée indéfiniment).
class QuotaEpuiseException implements Exception {
  const QuotaEpuiseException();

  @override
  String toString() => 'Quota de questions épuisé (402).';
}

class NetworkClient {
  // Le token JWT et l'email de session sont sensibles : ils sont stockés dans
  // le Keychain (iOS) / Keystore (Android) via flutter_secure_storage, jamais
  // dans SharedPreferences (fichier en clair, lisible sur un device
  // rooté/jailbreaké). Seule l'URL du serveur (non sensible) reste dans
  // SharedPreferences.
  static const FlutterSecureStorage _secureStorage = FlutterSecureStorage();
  static const String _kTokenKey = 'token';
  static const String _kUserEmailKey = 'userEmail';

  String _baseUrl = 'https://assistantia-prosartisan.onrender.com';
  String? _token;
  String? _userEmail;
  final Dio _dio = Dio();

  String get baseUrl => _baseUrl;
  set baseUrl(String url) {
    _baseUrl = url;
    _saveBaseUrl();
  }

  String? get token => _token;
  String? get userEmail => _userEmail;

  NetworkClient() {
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString('baseUrl') ?? 'https://assistantia-prosartisan.onrender.com';
    // Le stockage sécurisé n'est pas disponible partout (plateforme non
    // supportée, tests sans plugin natif) : on dégrade en mode déconnecté
    // plutôt que de faire planter le démarrage de l'app.
    try {
      _token = await _secureStorage.read(key: _kTokenKey);
      _userEmail = await _secureStorage.read(key: _kUserEmailKey);
    } catch (_) {
      _token = null;
      _userEmail = null;
    }
  }

  Future<void> _saveBaseUrl() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('baseUrl', _baseUrl);
  }

  Future<void> saveSession(String token, String email) async {
    _token = token;
    _userEmail = email;
    try {
      await _secureStorage.write(key: _kTokenKey, value: token);
      await _secureStorage.write(key: _kUserEmailKey, value: email);
    } catch (_) {
      // Session conservée en mémoire pour la durée du process même si la
      // persistance sécurisée échoue (voir _loadSettings).
    }
  }

  Future<void> clearSession() async {
    _token = null;
    _userEmail = null;
    try {
      await _secureStorage.delete(key: _kTokenKey);
      await _secureStorage.delete(key: _kUserEmailKey);
    } catch (_) {}
  }

  // URL du serveur de production par défaut
  static const String productionUrl = 'https://assistantia-prosartisan.onrender.com';

  // --- Auto-détection de l'IP Serveur ---
  Future<String> autoDetectBaseUrl() async {
    if (kIsWeb) {
      final host = Uri.base.host;
      final detectedUrl = (host == 'localhost' || host == '127.0.0.1')
          ? 'http://localhost:8000'
          : productionUrl;
      baseUrl = detectedUrl;
      return detectedUrl;
    }

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
    try {
      final response = await _dio.post(
        '$_baseUrl/api/auth/login',
        data: {
          'email': email,
          'password': password,
        },
      );

      final data = response.data;
      if (response.statusCode == 200) {
        final token = data['access_token'];
        await saveSession(token, email);
        return {'success': true, 'data': data};
      } else {
        return {'success': false, 'error': data['detail'] ?? 'Identifiants invalides'};
      }
    } on DioException catch (e) {
      if (e.response != null) {
        final data = e.response!.data;
        if (data is Map && data.containsKey('detail')) {
          return {'success': false, 'error': data['detail']};
        }
        return {
          'success': false,
          'error': 'Le serveur a renvoyé une réponse invalide (HTTP ${e.response!.statusCode} Not Found).\n[Serveur ciblé : $_baseUrl]'
        };
      }
      return {'success': false, 'error': 'Impossible de se connecter au serveur : ${e.message}\n[Serveur ciblé : $_baseUrl]'};
    } catch (e) {
      return {'success': false, 'error': 'Impossible de se connecter au serveur : $e\n[Serveur ciblé : $_baseUrl]'};
    }
  }

  Future<Map<String, dynamic>> register(String email, String password, String name, String phone) async {
    try {
      final response = await _dio.post(
        '$_baseUrl/api/auth/register',
        data: {
          'email': email,
          'password': password,
          'nom': name,
          'telephone': phone.isEmpty ? null : phone,
        },
      );

      final data = response.data;
      if (response.statusCode == 200 || response.statusCode == 201) {
        return {'success': true, 'data': data};
      } else {
        return {'success': false, 'error': data['detail'] ?? 'Échec de l\'inscription'};
      }
    } on DioException catch (e) {
      if (e.response != null) {
        final data = e.response!.data;
        if (data is Map && data.containsKey('detail')) {
          return {'success': false, 'error': data['detail']};
        }
        return {
          'success': false,
          'error': 'Le serveur a renvoyé une réponse invalide (HTTP ${e.response!.statusCode} Not Found).\n[Serveur ciblé : $_baseUrl]'
        };
      }
      return {'success': false, 'error': 'Impossible de joindre le serveur : ${e.message}\n[Serveur ciblé : $_baseUrl]'};
    } catch (e) {
      return {'success': false, 'error': 'Impossible de joindre le serveur : $e\n[Serveur ciblé : $_baseUrl]'};
    }
  }

  // --- Conversations ---
  Future<List<dynamic>> getConversations() async {
    try {
      final response = await _dio.get(
        '$_baseUrl/api/conversations',
        options: Options(
          headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
        ),
      );
      if (response.statusCode == 200) {
        return response.data as List;
      }
      return [];
    } catch (_) {
      return [];
    }
  }

  Future<Map<String, dynamic>?> getConversationDetail(String convId) async {
    try {
      final response = await _dio.get(
        '$_baseUrl/api/conversations/$convId',
        options: Options(
          headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
        ),
      );
      if (response.statusCode == 200) {
        return response.data as Map<String, dynamic>;
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  Future<bool> deleteConversation(String convId) async {
    try {
      final response = await _dio.delete(
        '$_baseUrl/api/conversations/$convId',
        options: Options(
          headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
        ),
      );
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, dynamic>> getQuota() async {
    try {
      final response = await _dio.get(
        '$_baseUrl/api/quota',
        options: Options(
          headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
        ),
      );
      if (response.statusCode == 200) {
        return response.data as Map<String, dynamic>;
      }
      return {'quota_restant': 0};
    } catch (_) {
      return {'quota_restant': 0};
    }
  }

  // --- SSE Chat Streaming ---
  Stream<String> sendMessageStream(
    String message,
    String? conversationId,
    int? metierId, {
    String? imageUrl,
  }) async* {
    final payload = {
      // Le serveur attend `question` (ExtendedChatRequest) : avec l'ancienne
      // clé `message`, chaque envoi était refusé en 422.
      'question': message,
      'conversation_id': conversationId,
      'metier_id': metierId,
      if (imageUrl != null && imageUrl.isNotEmpty) 'image_url': imageUrl,
    };

    if (kIsWeb) {
      try {
        final response = await _dio.post(
          '$_baseUrl/api/chat/stream',
          data: payload,
          options: Options(
            responseType: ResponseType.stream,
            headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
          ),
        );
        
        final Stream<List<int>> stream = (response.data as ResponseBody).stream;
        await for (final chunk in stream
            .transform(utf8.decoder)
            .transform(const LineSplitter())) {
          final trimmed = chunk.trim();
          if (trimmed.startsWith('data: ')) {
            final data = trimmed.substring(6).trim();
            if (data == '[DONE]') {
              break;
            }
            yield data;
          }
        }
      } on DioException catch (e) {
        if (e.response?.statusCode == 402) {
          throw const QuotaEpuiseException();
        }
        throw Exception('Erreur de transmission : $e');
      } catch (e) {
        throw Exception('Erreur de transmission : $e');
      }
    } else {
      final client = HttpClient();
      client.connectionTimeout = const Duration(seconds: 10);
      try {
        final uri = Uri.parse('$_baseUrl/api/chat/stream');
        final request = await client.postUrl(uri);
        
        request.headers.set('content-type', 'application/json');
        if (_token != null) {
          request.headers.set('authorization', 'Bearer $_token');
        }
        
        request.write(jsonEncode(payload));
        final response = await request.close();
        
        if (response.statusCode == 402) {
          throw const QuotaEpuiseException();
        }
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

  // --- Paiement Mobile Money (Wave / Orange Money) ---

  /// Crée le paiement chez l'opérateur ; renvoie `payment_url` et
  /// `transaction_id`, ou `{'error': ...}` si le paiement est impossible.
  Future<Map<String, dynamic>> initPayment(String typePass, String operateur) async {
    try {
      final response = await _dio.post(
        '$_baseUrl/api/payment/init',
        data: {'type_pass': typePass, 'operateur': operateur},
        options: Options(
          headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
        ),
      );
      return Map<String, dynamic>.from(response.data as Map);
    } on DioException catch (e) {
      final data = e.response?.data;
      final detail = data is Map ? data['detail'] : null;
      return {
        'error': detail is String ? detail : 'Paiement momentanément indisponible.',
      };
    } catch (_) {
      return {'error': 'Erreur de connexion : paiement non initialisé.'};
    }
  }

  /// Statut d'une transaction ("PENDING", "ACCEPTED", "FAILED", "EXPIRED"),
  /// ou null si le serveur est injoignable.
  Future<String?> getTransactionStatus(String transactionId) async {
    try {
      final response = await _dio.get(
        '$_baseUrl/api/payment/transactions/$transactionId',
        options: Options(
          headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
        ),
      );
      return (response.data as Map)['statut'] as String?;
    } catch (_) {
      return null;
    }
  }

  // --- Notifications Push (enregistrement du device token FCM) ---
  Future<bool> registerDevice(String fcmToken) async {
    try {
      final response = await _dio.post(
        '$_baseUrl/api/notifications/register-device',
        data: {'fcm_token': fcmToken},
        options: Options(
          headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
        ),
      );
      return response.statusCode == 204;
    } catch (_) {
      return false;
    }
  }

  // --- Transcription Audio (Whisper) ---
  Future<String?> transcribeAudio(List<int> bytes, String filename) async {
    try {
      final formData = FormData.fromMap({
        'file': MultipartFile.fromBytes(bytes, filename: filename),
      });

      final response = await _dio.post(
        '$_baseUrl/api/chat/transcribe',
        data: formData,
        options: Options(
          headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
        ),
      );

      if (response.statusCode == 200 && response.data is Map) {
        return response.data['text'] as String?;
      }
      return null;
    } catch (e) {
      return null;
    }
  }

  // --- Calculateurs Métier Normés ---
  Future<Map<String, dynamic>> calculate(
    String toolName,
    Map<String, dynamic> parameters,
  ) async {
    try {
      final response = await _dio.post(
        '$_baseUrl/api/chat/calculate',
        data: {
          'tool_name': toolName,
          'parameters': parameters,
        },
        options: Options(
          headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
        ),
      );
      if (response.statusCode == 200 && response.data is Map) {
        return Map<String, dynamic>.from(response.data as Map);
      }
      return {
        'tool_name': toolName,
        'result_text': 'Erreur: réponse invalide du serveur.',
        'data': {},
      };
    } catch (e) {
      return {
        'tool_name': toolName,
        'result_text': 'Erreur lors du calcul ($e).',
        'data': {},
      };
    }
  }

  // --- Devis & Factures Pro-Forma ---
  Future<Map<String, dynamic>> extractQuote(String prompt) async {
    try {
      final response = await _dio.post(
        '$_baseUrl/api/quotes/extract',
        data: {'prompt': prompt},
        options: Options(
          headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
        ),
      );
      if (response.statusCode == 200 && response.data is Map) {
        return Map<String, dynamic>.from(response.data as Map);
      }
      return {};
    } catch (e) {
      throw Exception('Erreur lors de l\'analyse du devis : $e');
    }
  }

  Future<Map<String, dynamic>> createQuote(Map<String, dynamic> quoteData) async {
    try {
      final response = await _dio.post(
        '$_baseUrl/api/quotes',
        data: quoteData,
        options: Options(
          headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
        ),
      );
      if ((response.statusCode == 200 || response.statusCode == 201) && response.data is Map) {
        return Map<String, dynamic>.from(response.data as Map);
      }
      return {};
    } catch (e) {
      throw Exception('Erreur lors de la sauvegarde du devis : $e');
    }
  }

  Future<List<dynamic>> listQuotes() async {
    try {
      final response = await _dio.get(
        '$_baseUrl/api/quotes',
        options: Options(
          headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
        ),
      );
      if (response.statusCode == 200 && response.data is List) {
        return response.data as List<dynamic>;
      }
      return [];
    } catch (_) {
      return [];
    }
  }

  Future<Map<String, dynamic>> getQuote(String quoteId) async {
    try {
      final response = await _dio.get(
        '$_baseUrl/api/quotes/$quoteId',
        options: Options(
          headers: _token != null ? {'authorization': 'Bearer $_token'} : null,
        ),
      );
      if (response.statusCode == 200 && response.data is Map) {
        return Map<String, dynamic>.from(response.data as Map);
      }
      return {};
    } catch (e) {
      throw Exception('Erreur lors de la récupération du devis : $e');
    }
  }
}
