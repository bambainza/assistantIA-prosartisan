import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import '../network/network_client.dart';

enum AppScreen { config, auth, main }

class ChatViewModel extends ChangeNotifier {
  final NetworkClient client;

  // --- Écrans et Navigation ---
  AppScreen _currentScreen = AppScreen.config;
  AppScreen get currentScreen => _currentScreen;

  // --- Thème ---
  bool _isDarkTheme = true;
  bool get isDarkTheme => _isDarkTheme;

  // --- État Auth ---
  bool _isLoginMode = true;
  bool get isLoginMode => _isLoginMode;
  bool _isAuthLoading = false;
  bool get isAuthLoading => _isAuthLoading;
  String? _authError;
  String? get authError => _authError;

  // --- État Main Chat ---
  List<dynamic> _conversations = [];
  List<dynamic> get conversations => _conversations;

  String? _activeConversationId;
  String? get activeConversationId => _activeConversationId;

  List<Map<String, dynamic>> _messages = [];
  List<Map<String, dynamic>> get messages => _messages;

  int? _activeMetierId = 1; // 1: Maçonnerie, 2: Électricité, 3: Plomberie, 4: Menuiserie
  int? get activeMetierId => _activeMetierId;

  bool _isStreaming = false;
  bool get isStreaming => _isStreaming;

  String _currentStreamText = '';
  String get currentStreamText => _currentStreamText;

  int? _quotaRestant;
  int? get quotaRestant => _quotaRestant;

  bool _showPaywall = false;
  bool get showPaywall => _showPaywall;

  String? _chatError;
  String? get chatError => _chatError;

  bool _isSidebarOpen = false;
  bool get isSidebarOpen => _isSidebarOpen;

  ChatViewModel(this.client) {
    _initialize();
  }

  Future<void> _initialize() async {
    // Petit délai pour laisser SharedPreferences se charger dans client
    await Future.delayed(const Duration(milliseconds: 300));
    
    // Détection auto au démarrage si aucune URL configurée
    if (client.baseUrl == 'http://localhost:8000') {
      await autoDetectServer();
    }

    if (client.token != null && client.userEmail != null) {
      _loadMainState(client.userEmail!);
    } else {
      _currentScreen = AppScreen.auth;
      notifyListeners();
    }
  }

  // --- Actions Réseau & Config ---
  Future<void> autoDetectServer() async {
    _chatError = "Détection du serveur en cours...";
    notifyListeners();
    final url = await client.autoDetectBaseUrl();
    _chatError = "Serveur détecté : $url";
    notifyListeners();
  }

  void saveBaseUrl(String url) {
    if (url.trim().isEmpty) {
      _chatError = "L'adresse URL ne peut pas être vide";
      notifyListeners();
      return;
    }
    client.baseUrl = url.trim();
    _currentScreen = AppScreen.auth;
    _chatError = null;
    notifyListeners();
  }

  void showConfigScreen() {
    _currentScreen = AppScreen.config;
    _chatError = null;
    notifyListeners();
  }

  // --- Actions Authentification ---
  void toggleAuthMode() {
    _isLoginMode = !_isLoginMode;
    _authError = null;
    _isAuthLoading = false;
    notifyListeners();
  }

  Future<void> login(String email, String password) async {
    _isAuthLoading = true;
    _authError = null;
    notifyListeners();

    final result = await client.login(email, password);
    _isAuthLoading = false;

    if (result['success']) {
      _loadMainState(email);
    } else {
      _authError = result['error'];
      notifyListeners();
    }
  }

  Future<void> register(String email, String password, String name, String phone) async {
    _isAuthLoading = true;
    _authError = null;
    notifyListeners();

    final result = await client.register(email, password, name, phone);
    if (result['success']) {
      // Connexion automatique après inscription
      final loginResult = await client.login(email, password);
      _isAuthLoading = false;
      if (loginResult['success']) {
        _loadMainState(email);
      } else {
        _authError = "Inscription réussie, mais connexion automatique échouée.";
        notifyListeners();
      }
    } else {
      _isAuthLoading = false;
      _authError = result['error'];
      notifyListeners();
    }
  }

  Future<void> logout() async {
    await client.clearSession();
    _activeConversationId = null;
    _messages = [];
    _conversations = [];
    _currentScreen = AppScreen.auth;
    notifyListeners();
  }

  // --- Actions Chat & Métiers ---
  void selectMetier(int? id) {
    _activeMetierId = id;
    notifyListeners();
  }

  void setSidebarOpen(bool open) {
    _isSidebarOpen = open;
    notifyListeners();
  }

  void toggleTheme() {
    _isDarkTheme = !_isDarkTheme;
    notifyListeners();
  }

  void dismissError() {
    _chatError = null;
    _authError = null;
    notifyListeners();
  }

  void dismissPaywall() {
    _showPaywall = false;
    notifyListeners();
  }

  void triggerFakePaymentSuccess() {
    _showPaywall = false;
    _quotaRestant = 100; // Simulation d'activation d'abonnement
    notifyListeners();
    refreshConversations();
  }

  void createConversation() {
    _activeConversationId = null;
    _messages = [];
    _currentStreamText = '';
    _isSidebarOpen = false;
    notifyListeners();
  }

  Future<void> selectConversation(String convId) async {
    _isSidebarOpen = false;
    _chatError = null;
    notifyListeners();

    final detail = await client.getConversationDetail(convId);
    if (detail != null) {
      _activeConversationId = detail['id'];
      _messages = List<Map<String, dynamic>>.from(detail['messages']);
      notifyListeners();
    } else {
      _chatError = "Impossible de charger la conversation";
      notifyListeners();
    }
  }

  Future<void> deleteConversation(String convId) async {
    final success = await client.deleteConversation(convId);
    if (success) {
      if (_activeConversationId == convId) {
        createConversation();
      }
      refreshConversations();
    } else {
      _chatError = "Échec de la suppression";
      notifyListeners();
    }
  }

  Future<void> refreshConversations() async {
    final list = await client.getConversations();
    _conversations = list;
    notifyListeners();
  }

  Future<void> refreshQuota() async {
    final q = await client.getQuota();
    _quotaRestant = q['quota_restant'];
    notifyListeners();
  }

  // --- Envoi de message et SSE Streaming ---
  Future<void> sendMessage(String question) async {
    if (_isStreaming || question.trim().isEmpty) return;

    // Ajouter le message de l'utilisateur
    final userMsg = {
      'id': DateTime.now().millisecondsSinceEpoch.toString(),
      'role': 'user',
      'content': question.trim(),
    };
    _messages = [..._messages, userMsg];
    _isStreaming = true;
    _currentStreamText = '...';
    notifyListeners();

    try {
      String? originalConvId = _activeConversationId;
      String fullResponseText = '';

      final stream = client.sendMessageStream(question, originalConvId, _activeMetierId);
      
      await for (final data in stream) {
        // En SSE, on reçoit du JSON contenant le chunk ou d'autres infos
        try {
          final parsed = jsonDecode(data);
          
          if (parsed is Map) {
            // Si c'est un message d'information (metadata de la conversation)
            if (parsed.containsKey('conversation_id')) {
              _activeConversationId = parsed['conversation_id'];
              notifyListeners();
            }
            
            // Si c'est un chunk de texte
            if (parsed.containsKey('chunk')) {
              final chunk = parsed['chunk'] as String;
              if (fullResponseText == '...') {
                fullResponseText = chunk;
              } else {
                fullResponseText += chunk;
              }
              _currentStreamText = fullResponseText;
              notifyListeners();
            }
          }
        } catch (_) {
          // Si le format reçu est du texte brut (fallback)
          if (fullResponseText == '...') {
            fullResponseText = data;
          } else {
            fullResponseText += data;
          }
          _currentStreamText = fullResponseText;
          notifyListeners();
        }
      }

      // Fin du flux : enregistrer le message de l'assistant
      final assistantMsg = {
        'id': DateTime.now().millisecondsSinceEpoch.toString(),
        'role': 'assistant',
        'content': _currentStreamText,
      };
      _messages = [..._messages, assistantMsg];
      _isStreaming = false;
      _currentStreamText = '';
      notifyListeners();
      
      // Rafraîchir la liste et les quotas
      refreshConversations();
      refreshQuota();
    } catch (e) {
      _isStreaming = false;
      _currentStreamText = '';
      if (e.toString().contains('403') || e.toString().contains('quota')) {
        _showPaywall = true;
      } else {
        _chatError = "Erreur de transmission : $e";
      }
      notifyListeners();
    }
  }

  void _loadMainState(String email) {
    _currentScreen = AppScreen.main;
    _chatError = null;
    notifyListeners();
    refreshConversations();
    refreshQuota();
  }
}


