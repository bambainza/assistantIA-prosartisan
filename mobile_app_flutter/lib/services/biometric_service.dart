import 'package:local_auth/local_auth.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Verrouillage optionnel de l'app par biométrie (Face ID / empreinte).
///
/// La préférence d'activation n'est pas sensible (juste un booléen) et reste
/// dans `shared_preferences` ; c'est la biométrie native (Keychain/Keystore
/// sous-jacents) qui protège réellement l'accès, pas ce stockage.
class BiometricService {
  static const String _kEnabledPref = 'biometric_lock_enabled';

  final LocalAuthentication _auth = LocalAuthentication();

  Future<bool> isDeviceSupported() async {
    try {
      final supported = await _auth.isDeviceSupported();
      final canCheck = await _auth.canCheckBiometrics;
      return supported && canCheck;
    } catch (_) {
      return false;
    }
  }

  Future<bool> authenticate({
    String reason = 'Déverrouillez ProsArtisan IA',
  }) async {
    try {
      return await _auth.authenticate(
        localizedReason: reason,
        options: const AuthenticationOptions(
          biometricOnly: false,
          stickyAuth: true,
        ),
      );
    } catch (_) {
      return false;
    }
  }

  Future<bool> isLockEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_kEnabledPref) ?? false;
  }

  Future<void> setLockEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_kEnabledPref, enabled);
  }
}
