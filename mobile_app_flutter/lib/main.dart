import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'network/network_client.dart';
import 'viewmodels/chat_viewmodel.dart';
import 'views/auth_view.dart';
import 'views/chat_view.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final networkClient = NetworkClient();

  runApp(
    ChangeNotifierProvider(
      create: (_) => ChatViewModel(networkClient),
      child: const ProsArtisanApp(),
    ),
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
