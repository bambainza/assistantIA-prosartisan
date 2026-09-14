import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'network/network_client.dart';
import 'services/push_notification_service.dart';
import 'viewmodels/chat_viewmodel.dart';
import 'views/auth_view.dart';
import 'views/chat_view.dart';

// Supervision d'erreurs (Sentry) : inactive tant qu'aucun DSN n'est fourni au
// build (`flutter run --dart-define=SENTRY_DSN=https://...`). Sans cela,
// SentryFlutter.init est simplement ignoré — voir docs/PLAN_AMELIORATION.md (4.5).
const String _sentryDsn = String.fromEnvironment('SENTRY_DSN', defaultValue: '');

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final networkClient = NetworkClient();

  Future<void> bootstrap() async {
    // Notifications push : no-op silencieux si Firebase n'est pas configuré
    // nativement (voir services/push_notification_service.dart).
    unawaited(PushNotificationService(networkClient).initialize());

    runApp(
      ChangeNotifierProvider(
        create: (_) => ChatViewModel(networkClient),
        child: const ProsArtisanApp(),
      ),
    );
  }

  if (_sentryDsn.isEmpty) {
    await bootstrap();
    return;
  }

  await SentryFlutter.init(
    (options) {
      options.dsn = _sentryDsn;
      options.tracesSampleRate = 0.2;
    },
    appRunner: bootstrap,
  );
}

class ProsArtisanApp extends StatelessWidget {
  const ProsArtisanApp({super.key});

  @override
  Widget build(BuildContext context) {
    final viewModel = Provider.of<ChatViewModel>(context);
    final isDark = viewModel.isDarkTheme;

    return MaterialApp(
      title: 'ProsArtisan IA',
      debugShowCheckedModeBanner: false,
      themeMode: isDark ? ThemeMode.dark : ThemeMode.light,
      darkTheme: ThemeData(
        brightness: Brightness.dark,
        primaryColor: const Color(0xFFE2A000),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFE2A000),
          secondary: Color(0xFFE2A000),
          surface: Colors.transparent,
        ),
        useMaterial3: true,
      ),
      theme: ThemeData(
        brightness: Brightness.light,
        primaryColor: const Color(0xFFE2A000),
        colorScheme: const ColorScheme.light(
          primary: Color(0xFFE2A000),
          secondary: Color(0xFFE2A000),
          surface: Colors.transparent,
        ),
        useMaterial3: true,
      ),
      home: const MainLayoutWrapper(),
    );
  }
}

class MainLayoutWrapper extends StatelessWidget {
  const MainLayoutWrapper({super.key});

  @override
  Widget build(BuildContext context) {
    final viewModel = Provider.of<ChatViewModel>(context);
    final isDark = viewModel.isDarkTheme;

    // Choix du dégradé selon le thème
    final backgroundColors = isDark
        ? [const Color(0xFF1E1E2C), const Color(0xFF0F0F17)]
        : [const Color(0xFFF5F5F7), const Color(0xFFE5E5EA)];

    Widget activeScreen;
    switch (viewModel.currentScreen) {
      case AppScreen.auth:
        activeScreen = const AuthView();
        break;
      case AppScreen.main:
        activeScreen = const ChatView();
        break;
      case AppScreen.locked:
        activeScreen = _BiometricLockScreen(isDark: isDark);
        break;
    }

    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: backgroundColors,
        ),
      ),
      child: GestureDetector(
        // Clic en dehors des textfields pour fermer le clavier automatiquement
        onTap: () => FocusScope.of(context).unfocus(),
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 300),
          child: KeyedSubtree(
            key: ValueKey(viewModel.currentScreen),
            child: activeScreen,
          ),
        ),
      ),
    );
  }
}

/// Écran de verrouillage biométrique affiché au démarrage quand l'option est
/// activée (voir `ChatViewModel.toggleBiometricLock`).
class _BiometricLockScreen extends StatelessWidget {
  final bool isDark;

  const _BiometricLockScreen({required this.isDark});

  @override
  Widget build(BuildContext context) {
    final viewModel = Provider.of<ChatViewModel>(context, listen: false);
    final textColor = isDark ? Colors.white : const Color(0xFF1A1A1A);

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.fingerprint, size: 72, color: const Color(0xFFE2A000)),
            const SizedBox(height: 16),
            Text(
              'ProsArtisan IA est verrouillé',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: textColor),
            ),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: () => viewModel.unlockWithBiometrics(),
              icon: const Icon(Icons.lock_open),
              label: const Text('Déverrouiller'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFE2A000),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
