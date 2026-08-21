import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../viewmodels/chat_viewmodel.dart';

class AuthView extends StatefulWidget {
  const AuthView({super.key});

  @override
  State<AuthView> createState() => _AuthViewState();
}

class _AuthViewState extends State<AuthView> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _nomController = TextEditingController();
  final _phoneController = TextEditingController();

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _nomController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final viewModel = Provider.of<ChatViewModel>(context);
    final isDark = viewModel.isDarkTheme;
    final isLogin = viewModel.isLoginMode;
    final textColor = isDark ? Colors.white : Colors.black87;
    final textSecColor = isDark ? Colors.white60 : Colors.black54;

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 28.0, vertical: 40.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(
                Icons.account_circle,
                size: 90,
                color: Color(0xFFE2A000),
              ),
              const SizedBox(height: 16),
              Text(
                isLogin ? "Connexion ProsArtisan" : "Créer un Compte",
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                  color: textColor,
                ),
              ),
              const SizedBox(height: 32),

              if (!isLogin) ...[
                TextField(
                  controller: _nomController,
                  style: TextStyle(color: textColor),
                  decoration: _buildInputDecoration("Nom complet", isDark),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: _phoneController,
                  keyboardType: TextInputType.phone,
                  style: TextStyle(color: textColor),
                  decoration: _buildInputDecoration("Téléphone (ex: +225...)", isDark),
                ),
                const SizedBox(height: 14),
              ],

              TextField(
                controller: _emailController,
                keyboardType: TextInputType.emailAddress,
                style: TextStyle(color: textColor),
                decoration: _buildInputDecoration("Adresse email", isDark),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: _passwordController,
                obscureText: true,
                style: TextStyle(color: textColor),
                decoration: _buildInputDecoration("Mot de passe", isDark),
              ),
              
              if (viewModel.authError != null) ...[
                const SizedBox(height: 16),
                Text(
                  viewModel.authError!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.red, fontSize: 13, fontWeight: FontWeight.w500),
                ),
              ],

              const SizedBox(height: 32),

              if (viewModel.isAuthLoading)
                const CircularProgressIndicator(color: Color(0xFFE2A000))
              else ...[
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton(
                        onPressed: () {
                          if (isLogin) {
                            viewModel.login(_emailController.text, _passwordController.text);
                          } else {
                            viewModel.register(
                              _emailController.text,
                              _passwordController.text,
                              _nomController.text,
                              _phoneController.text,
                            );
                          }
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFFE2A000),
                          foregroundColor: Colors.black,
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                        child: Text(
                          isLogin ? "Se connecter" : "S'inscrire",
                          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                TextButton(
                  onPressed: () => viewModel.toggleAuthMode(),
                  child: Text(
                    isLogin 
                        ? "Pas de compte ? Inscrivez-vous" 
                        : "Déjà inscrit ? Connectez-vous",
                    style: TextStyle(color: textSecColor, fontSize: 14),
                  ),
                ),
                TextButton(
                  onPressed: () => viewModel.showConfigScreen(),
                  child: const Text(
                    "Modifier l'adresse serveur",
                    style: TextStyle(color: Color(0xFFE2A000), fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  InputDecoration _buildInputDecoration(String label, bool isDark) {
    return InputDecoration(
      labelText: label,
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
    );
  }
}
