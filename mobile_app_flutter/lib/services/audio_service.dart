import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:record/record.dart';

class AudioService {
  AudioRecorder? _audioRecorder;
  AudioRecorder get _recorder => _audioRecorder ??= AudioRecorder();

  FlutterTts? _flutterTts;
  FlutterTts get _tts => _flutterTts ??= FlutterTts();

  bool _isRecording = false;
  bool get isRecording => _isRecording;

  String? _currentlySpeakingId;
  String? get currentlySpeakingId => _currentlySpeakingId;
  bool _ttsInitialized = false;

  AudioService();

  Future<void> _ensureTtsInit() async {
    if (_ttsInitialized) return;
    try {
      await _tts.setLanguage("fr-FR");
      await _tts.setSpeechRate(0.5);
      await _tts.setVolume(1.0);
      await _tts.setPitch(1.0);

      _tts.setCompletionHandler(() {
        _currentlySpeakingId = null;
      });

      _tts.setCancelHandler(() {
        _currentlySpeakingId = null;
      });

      _tts.setErrorHandler((_) {
        _currentlySpeakingId = null;
      });
      _ttsInitialized = true;
    } catch (_) {}
  }

  // --- Enregistrement Micro (Speech-to-Text) ---

  Future<bool> startRecording() async {
    try {
      if (await _recorder.hasPermission()) {
        const encoder = AudioEncoder.aacLc;
        
        final config = const RecordConfig(
          encoder: encoder,
          bitRate: 128000,
          sampleRate: 44100,
        );

        if (kIsWeb) {
          await _recorder.start(config, path: '');
        } else {
          final tempDir = Directory.systemTemp;
          final path = '${tempDir.path}/chantier_voice_${DateTime.now().millisecondsSinceEpoch}.m4a';
          await _recorder.start(config, path: path);
        }

        _isRecording = true;
        return true;
      }
      return false;
    } catch (_) {
      _isRecording = false;
      return false;
    }
  }

  Future<Uint8List?> stopRecording() async {
    try {
      if (!_isRecording) return null;
      final path = await _recorder.stop();
      _isRecording = false;

      if (path != null && path.isNotEmpty) {
        final file = File(path);
        if (await file.exists()) {
          final bytes = await file.readAsBytes();
          try {
            await file.delete();
          } catch (_) {}
          return bytes;
        }
      }
      return null;
    } catch (_) {
      _isRecording = false;
      return null;
    }
  }

  Future<void> cancelRecording() async {
    try {
      if (_isRecording) {
        await _recorder.cancel();
        _isRecording = false;
      }
    } catch (_) {
      _isRecording = false;
    }
  }

  // --- Synthèse Vocale (Text-to-Speech) ---

  Future<void> speak(String messageId, String text) async {
    try {
      if (_currentlySpeakingId == messageId) {
        await stopSpeaking();
        return;
      }

      await stopSpeaking();
      await _ensureTtsInit();
      _currentlySpeakingId = messageId;
      
      // Nettoyer les balises Markdown basiques pour une lecture vocale fluide
      final cleanedText = text
          .replaceAll(RegExp(r'\*\*|\*|#|`|_'), '')
          .replaceAll(RegExp(r'\[(.*?)\]\(.*?\)'), r'$1');

      await _tts.speak(cleanedText);
    } catch (_) {
      _currentlySpeakingId = null;
    }
  }

  Future<void> stopSpeaking() async {
    try {
      if (_flutterTts != null) {
        await _tts.stop();
      }
      _currentlySpeakingId = null;
    } catch (_) {
      _currentlySpeakingId = null;
    }
  }

  void dispose() {
    _audioRecorder?.dispose();
    _flutterTts?.stop();
  }
}
