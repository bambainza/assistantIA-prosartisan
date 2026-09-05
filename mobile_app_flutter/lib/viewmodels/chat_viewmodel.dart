import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../network/network_client.dart';
import '../services/audio_service.dart';
import '../services/local_storage_service.dart';

enum AppScreen { auth, main }

class ChatViewModel extends ChangeNotifier {
  final NetworkClient client;
  final LocalStorageService localStorage = LocalStorageService();
  final AudioService audioService = AudioService();
  final ImagePicker _imagePicker = ImagePicker();

  // --- Écrans et Navigation ---
  AppScreen _currentScreen = AppScreen.auth;
  AppScreen get currentScreen => _currentScreen;

  // --- Thème ---
  bool _isDarkTheme = true;
  bool get isDarkTheme => _isDarkTheme;

  // --- État Hors-Ligne & Réseau ---
  bool _isOffline = false;
  bool get isOffline => _isOffline;

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

  int? _activeMetierId = 1; // 1: Maçonnerie, 2: Électricité, 3: Plomberie, 4: Menuiserie, 5: Carrelage, 6: Peinture
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

  // --- Fiches Chantier Épinglées (Favoris Hors-Ligne) ---
  List<Map<String, dynamic>> _starredSheets = [];
  List<Map<String, dynamic>> get starredSheets => _starredSheets;

  // --- Photo / Image Attachée ---
  Uint8List? _attachedImageBytes;
  Uint8List? get attachedImageBytes => _attachedImageBytes;
  String? _attachedImageName;
  String? get attachedImageName => _attachedImageName;

  // --- Audio Recording & TTS ---
  bool get isRecording => audioService.isRecording;
  bool _isTranscribing = false;
  bool get isTranscribing => _isTranscribing;

  ChatViewModel(this.client, {bool autoInitialize = true}) {
    if (autoInitialize) {
      _initialize();
    }
  }

  Future<void> _initialize() async {
    _isAuthLoading = true;
    notifyListeners();

    await loadStarredSheets();

    // Petit délai pour laisser SharedPreferences se charger dans client
    await Future.delayed(const Duration(milliseconds: 300));
    
    // Attendre la détection automatique du serveur
    await autoDetectServer();

    _isAuthLoading = false;
    if (client.token != null && client.userEmail != null) {
      _loadMainState(client.userEmail!);
    } else {
      _currentScreen = AppScreen.auth;
      notifyListeners();
    }
  }

  // --- Actions Réseau & Config ---
  Future<void> autoDetectServer() async {
    try {
      final url = await client.autoDetectBaseUrl();
      client.baseUrl = url;
      _isOffline = false;
    } catch (_) {
      _isOffline = true;
    }
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
      _isOffline = false;
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
      final loginResult = await client.login(email, password);
      _isAuthLoading = false;
      if (loginResult['success']) {
        _isOffline = false;
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
    _quotaRestant = 100; // Activation pass pro
    notifyListeners();
    refreshConversations();
    refreshQuota();
  }

  void createConversation() {
    _activeConversationId = null;
    _messages = [];
    _currentStreamText = '';
    _isSidebarOpen = false;
    clearAttachedImage();
    audioService.stopSpeaking();
    notifyListeners();
  }

  Future<void> selectConversation(String convId) async {
    _isSidebarOpen = false;
    _chatError = null;
    clearAttachedImage();
    audioService.stopSpeaking();
    notifyListeners();

    final detail = await client.getConversationDetail(convId);
    if (detail != null) {
      _isOffline = false;
      _activeConversationId = detail['id'];
      _messages = List<Map<String, dynamic>>.from(detail['messages']);
      await localStorage.saveMessages(convId, _messages);
      notifyListeners();
    } else {
      // Fallback hors-ligne : charger depuis le stockage local
      final cached = await localStorage.getCachedMessages(convId);
      if (cached.isNotEmpty) {
        _activeConversationId = convId;
        _messages = cached;
        _isOffline = true;
        notifyListeners();
      } else {
        _chatError = "Impossible de charger la discussion (mode hors-ligne)";
        notifyListeners();
      }
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
    if (list.isNotEmpty) {
      _isOffline = false;
      _conversations = list;
      await localStorage.saveConversations(list);
    } else {
      // Si le réseau est indisponible, charger les conversations en cache
      final cached = await localStorage.getCachedConversations();
      if (cached.isNotEmpty) {
        _conversations = cached;
        _isOffline = true;
      }
    }
    notifyListeners();
  }

  Future<void> refreshQuota() async {
    final q = await client.getQuota();
    _quotaRestant = q['quota_restant'];
    notifyListeners();
  }

  // --- Gestion des Photos & Vision (GPT-4o) ---

  Future<void> pickImageFromCamera() async {
    try {
      final XFile? photo = await _imagePicker.pickImage(
        source: ImageSource.camera,
        maxWidth: 1024,
        maxHeight: 1024,
        imageQuality: 85,
      );
      if (photo != null) {
        _attachedImageBytes = await photo.readAsBytes();
        _attachedImageName = photo.name;
        notifyListeners();
      }
    } catch (e) {
      _chatError = "Impossible d'accéder à la caméra : $e";
      notifyListeners();
    }
  }

  Future<void> pickImageFromGallery() async {
    try {
      final XFile? image = await _imagePicker.pickImage(
        source: ImageSource.gallery,
        maxWidth: 1024,
        maxHeight: 1024,
        imageQuality: 85,
      );
      if (image != null) {
        _attachedImageBytes = await image.readAsBytes();
        _attachedImageName = image.name;
        notifyListeners();
      }
    } catch (e) {
      _chatError = "Impossible d'accéder à la galerie : $e";
      notifyListeners();
    }
  }

  void clearAttachedImage() {
    _attachedImageBytes = null;
    _attachedImageName = null;
    notifyListeners();
  }

  // --- Enregistrement Audio Micro & Transcription (Whisper) ---

  Future<bool> startAudioRecording() async {
    _chatError = null;
    audioService.stopSpeaking();
    final started = await audioService.startRecording();
    notifyListeners();
    return started;
  }

  Future<String?> stopAudioRecordingAndTranscribe() async {
    _isTranscribing = true;
    notifyListeners();

    try {
      final audioBytes = await audioService.stopRecording();
      if (audioBytes != null && audioBytes.isNotEmpty) {
        final text = await client.transcribeAudio(audioBytes, 'chantier_note.m4a');
        _isTranscribing = false;
        notifyListeners();
        return text;
      }
    } catch (e) {
      _chatError = "Erreur audio : $e";
    }

    _isTranscribing = false;
    notifyListeners();
    return null;
  }

  Future<void> cancelAudioRecording() async {
    await audioService.cancelRecording();
    _isTranscribing = false;
    notifyListeners();
  }

  // --- Synthèse Vocale (Text-to-Speech) ---

  bool isSpeakingMessage(String messageId) {
    return audioService.currentlySpeakingId == messageId;
  }

  Future<void> toggleSpeak(String messageId, String text) async {
    await audioService.speak(messageId, text);
    notifyListeners();
  }

  // --- Fiches Chantier Épinglées (Favoris Hors-Ligne) ---

  Future<void> loadStarredSheets() async {
    _starredSheets = await localStorage.getStarredSheets();
    notifyListeners();
  }

  bool isSheetStarred(String messageId) {
    return _starredSheets.any((item) => item['id'] == messageId);
  }

  Future<void> toggleStarSheet(Map<String, dynamic> message, {String? customTitle}) async {
    final msgId = message['id']?.toString() ?? DateTime.now().millisecondsSinceEpoch.toString();
    if (isSheetStarred(msgId)) {
      await localStorage.removeStarredSheet(msgId);
    } else {
      await localStorage.saveStarredSheet({
        'id': msgId,
        'title': customTitle ?? 'Fiche Chantier Technique',
        'content': message['content'] ?? '',
        'metier_id': _activeMetierId,
      });
    }
    await loadStarredSheets();
  }

  Future<void> removeStarredSheet(String sheetId) async {
    await localStorage.removeStarredSheet(sheetId);
    await loadStarredSheets();
  }

  // --- Envoi de message et SSE Streaming ---

  Future<void> sendMessage(String question) async {
    if (_isStreaming || (question.trim().isEmpty && _attachedImageBytes == null)) return;

    audioService.stopSpeaking();

    // Préparer l'image en base64 pour la vision multimodale si présente
    String? imageUrl;
    Uint8List? imageThumbnailBytes;
    if (_attachedImageBytes != null) {
      imageThumbnailBytes = _attachedImageBytes;
      imageUrl = 'data:image/jpeg;base64,${base64Encode(_attachedImageBytes!)}';
    }

    // Réinitialiser la pièce jointe
    clearAttachedImage();

    // Ajouter le message de l'utilisateur
    final userMsg = <String, dynamic>{
      'id': DateTime.now().millisecondsSinceEpoch.toString(),
      'role': 'user',
      'content': question.trim(),
      'image_bytes': ?imageThumbnailBytes,
    };
    _messages = [..._messages, userMsg];
    _isStreaming = true;
    _currentStreamText = '...';
    notifyListeners();

    try {
      String? originalConvId = _activeConversationId;
      String fullResponseText = '';

      final stream = client.sendMessageStream(
        question,
        originalConvId,
        _activeMetierId,
        imageUrl: imageUrl,
      );
      
      await for (final data in stream) {
        try {
          final parsed = jsonDecode(data);
          
          if (parsed is Map) {
            if (parsed.containsKey('conversation_id')) {
              _activeConversationId = parsed['conversation_id'];
              notifyListeners();
            }
            
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
          if (fullResponseText == '...') {
            fullResponseText = data;
          } else {
            fullResponseText += data;
          }
          _currentStreamText = fullResponseText;
          notifyListeners();
        }
      }

      // Fin du flux : enregistrer la réponse de l'assistant
      final assistantMsg = {
        'id': DateTime.now().millisecondsSinceEpoch.toString(),
        'role': 'assistant',
        'content': _currentStreamText,
      };
      _messages = [..._messages, assistantMsg];
      _isStreaming = false;
      _currentStreamText = '';
      _isOffline = false;
      notifyListeners();
      
      // Sauvegarder dans le cache local
      if (_activeConversationId != null) {
        await localStorage.saveMessages(_activeConversationId!, _messages);
      }
      
      refreshConversations();
      refreshQuota();
    } catch (e) {
      _isStreaming = false;
      _currentStreamText = '';
      if (e.toString().contains('403') || e.toString().contains('quota')) {
        _showPaywall = true;
      } else {
        _isOffline = true;
        _chatError = "Réseau faible ou serveur injoignable : passage en mode hors-ligne";
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

  @override
  void dispose() {
    audioService.dispose();
    super.dispose();
  }
}



