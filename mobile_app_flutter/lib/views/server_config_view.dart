import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../viewmodels/chat_viewmodel.dart';

class ServerConfigView extends StatefulWidget {
  const ServerConfigView({super.key});

  @override
  State<ServerConfigView> createState() => _ServerConfigViewState();
}

class _ServerConfigViewState extends State<ServerConfigView> {
  late TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    final viewModel = Provider.of<ChatViewModel>(context, listen: false);
    _controller = TextEditingController(text: viewModel.client.baseUrl);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final viewModel = Provider.of<ChatViewModel>(context);
    final isDark = viewModel.isDarkTheme;
    final textColor = isDark ? Colors.white : Colors.black87;
    final textSecColor = isDark ? Colors.white60 : Colors.black54;

    // Écouter le changement de baseUrl auto-détectée
    _controller.text = viewModel.client.baseUrl;

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(28.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(
                Icons.settings,
                size: 80,
                color: Color(0xFFE2A000),
              ),
              const SizedBox(height: 24),
              Text(
                "Configuration du Serveur",
                style: TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.bold,
                  color: textColor,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                "Entrez l'URL de l'API backend de ProsArtisan",
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 14,
                  color: textSecColor,
                ),
              ),
              const SizedBox(height: 36),
              TextField(
                controller: _controller,
                style: TextStyle(color: textColor),
                decoration: InputDecoration(
                  labelText: "URL de l'API",
                  labelStyle: const TextStyle(color: Colors.grey),
                  filled: true,
                  fillColor: isDark ? const Color(0xFF222232) : Colors.white,
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: Color(0xFFE2A000), width: 2),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: Colors.grey),
                  ),
                ),
              ),
              const SizedBox(height: 20),
              
              // Affichage du message d'erreur ou d'état de détection
              if (viewModel.chatError != null) ...[
                Text(
                  viewModel.chatError!,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: viewModel.chatError!.contains("détecté") 
                        ? Colors.green 
                        : (viewModel.chatError!.contains("cours") ? Colors.blue : Colors.red),
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 16),
              ],

              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => viewModel.autoDetectServer(),
                      icon: const Icon(Icons.wifi_find, color: Color(0xFFE2A000)),
                      label: const Text("Détecter le Serveur", style: TextStyle(color: Color(0xFFE2A000))),
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        side: const BorderSide(color: Color(0xFFE2A000)),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: ElevatedButton(
                      onPressed: () => viewModel.saveBaseUrl(_controller.text),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFFE2A000),
                        foregroundColor: Colors.black,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                      child: const Text(
                        "Enregistrer et Continuer",
                        style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
