import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import '../network/network_client.dart';

/// Notifications push (Firebase Cloud Messaging).
///
/// IMPORTANT : nécessite un vrai projet Firebase configuré nativement
/// (`android/app/google-services.json` + plugin Gradle `com.google.gms.google-services`,
/// `ios/Runner/GoogleService-Info.plist`) pour fonctionner réellement — voir
/// docs/PLAN_AMELIORATION.md (item 4.2). Sans cette configuration, `initialize()`
/// échoue silencieusement (capturé) et l'application continue de fonctionner
/// normalement sans notifications push : jamais de crash au démarrage.
class PushNotificationService {
  final NetworkClient _networkClient;

  PushNotificationService(this._networkClient);

  Future<void> initialize() async {
    try {
      await Firebase.initializeApp();

      final messaging = FirebaseMessaging.instance;
      final settings = await messaging.requestPermission(
        alert: true,
        badge: true,
        sound: true,
      );

      if (settings.authorizationStatus == AuthorizationStatus.denied) {
        debugPrint('Notifications push refusées par l\'utilisateur.');
        return;
      }

      final token = await messaging.getToken();
      if (token != null) {
        await _networkClient.registerDevice(token);
      }

      // Réenregistre le token auprès du backend s'il est renouvelé par FCM.
      FirebaseMessaging.instance.onTokenRefresh.listen((newToken) {
        _networkClient.registerDevice(newToken);
      });
    } catch (e) {
      // Aucun projet Firebase configuré (dev local, build sans config native) :
      // dégradation silencieuse, l'app reste pleinement fonctionnelle.
      debugPrint('Notifications push non disponibles (Firebase non configuré) : $e');
    }
  }
}
