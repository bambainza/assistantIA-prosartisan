import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../viewmodels/chat_viewmodel.dart';
import 'paywall_dialog.dart';

class ChatView extends StatefulWidget {
  const ChatView({super.key});

  @override
  State<ChatView> createState() => _ChatViewState();
}

class _ChatViewState extends State<ChatView> {
  final _textController = TextEditingController();
  final _scrollController = ScrollController();

  @override
  void dispose() {
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    if (_scrollController.hasClients) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final viewModel = Provider.of<ChatViewModel>(context);
    final isDark = viewModel.isDarkTheme;
    final textColor = isDark ? Colors.white : Colors.black87;
    final textSecColor = isDark ? Colors.white60 : Colors.black54;
    final barColor = isDark ? const Color(0xFF171721) : const Color(0xFFE5E5EA);

    // Défiler vers le bas si de nouveaux messages arrivent
    if (viewModel.isStreaming || viewModel.messages.isNotEmpty) {
      _scrollToBottom();
    }

    // Affichage des messages temporaires d'erreur éphémères (Snackbar)
    if (viewModel.chatError != null && viewModel.chatError!.startsWith("Erreur")) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(viewModel.chatError!),
            action: SnackBarAction(
              label: "OK",
              textColor: const Color(0xFFE2A000),
              onPressed: () => viewModel.dismissError(),
            ),
          ),
        );
        viewModel.dismissError();
      });
    }

    // Dialogue de paywall si déclenché
    if (viewModel.showPaywall) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        showDialog(
          context: context,
          barrierDismissible: false,
          builder: (context) => PaywallDialog(
            onDismiss: () => viewModel.dismissPaywall(),
            onPaymentSuccess: () => viewModel.triggerFakePaymentSuccess(),
          ),
        );
        viewModel.dismissPaywall(); // Reset trigger dans le viewmodel
      });
    }

    return Scaffold(
      backgroundColor: Colors.transparent,
      appBar: AppBar(
        backgroundColor: barColor,
        elevation: 0,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              "ProsArtisan IA",
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: textColor),
            ),
            Text(
              "Abonnement: ${viewModel.quotaRestant != null && viewModel.quotaRestant! > 10 ? "Pro Illimité" : "Gratuit"}",
              style: TextStyle(fontSize: 12, color: textSecColor),
            ),
          ],
        ),
        iconTheme: IconThemeData(color: textColor),
        actions: [
          IconButton(
            icon: Icon(
              isDark ? Icons.brightness_7 : Icons.brightness_4,
              color: const Color(0xFFE2A000),
            ),
            onPressed: () => viewModel.toggleTheme(),
          ),
          IconButton(
            icon: const Icon(Icons.add, color: Color(0xFFE2A000)),
            onPressed: () => viewModel.createConversation(),
          ),
          IconButton(
            icon: Icon(Icons.logout, color: textSecColor),
            onPressed: () => viewModel.logout(),
          ),
        ],
      ),
      drawer: _buildDrawer(viewModel, isDark, textColor, textSecColor, barColor),
      body: Column(
        children: [
          // Barre de Sélection de Métier
          _buildMetierSelectorRow(viewModel, isDark, textColor),

          // Messages
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              itemCount: viewModel.messages.length + (viewModel.isStreaming ? 1 : 0),
              itemBuilder: (context, index) {
                if (index < viewModel.messages.length) {
                  final msg = viewModel.messages[index];
                  return _buildMessageBubble(msg, isDark);
                } else {
                  return _buildStreamingBubble(viewModel.currentStreamText, isDark, textSecColor);
                }
              },
            ),
          ),

          // Zone de saisie
          _buildChatInputArea(viewModel, isDark, textColor, barColor),
        ],
      ),
    );
  }

  // --- Widgets Internes ---

  Widget _buildDrawer(ChatViewModel viewModel, bool isDark, Color textColor, Color textSecColor, Color barColor) {
    return Drawer(
      backgroundColor: isDark ? const Color(0xFF171721) : Colors.white,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          DrawerHeader(
            decoration: BoxDecoration(color: barColor),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                const Icon(Icons.engineering, size: 48, color: Color(0xFFE2A000)),
                const SizedBox(height: 12),
                Text(
                  "ProsArtisan discussions",
                  style: TextStyle(color: textColor, fontSize: 18, fontWeight: FontWeight.bold),
                ),
                Text(
                  viewModel.client.userEmail ?? "",
                  style: TextStyle(color: textSecColor, fontSize: 13),
                ),
              ],
            ),
          ),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              itemCount: viewModel.conversations.length,
              itemBuilder: (context, index) {
                final conv = viewModel.conversations[index];
                final isActive = conv['id'] == viewModel.activeConversationId;
                return Card(
                  color: isActive 
                      ? const Color(0xFFE2A000) 
                      : (isDark ? const Color(0xFF232333) : const Color(0xFFE5E5EA)),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  child: ListTile(
                    title: Text(
                      conv['title'] ?? 'Discussion',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: isActive ? Colors.black : textColor,
                        fontSize: 14,
                        fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
                      ),
                    ),
                    onTap: () {
                      Navigator.pop(context);
                      viewModel.selectConversation(conv['id']);
                    },
                    trailing: IconButton(
                      icon: Icon(Icons.delete, color: isActive ? Colors.black54 : Colors.redAccent, size: 18),
                      onPressed: () => viewModel.deleteConversation(conv['id']),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMetierSelectorRow(ChatViewModel viewModel, bool isDark, Color textColor) {
    final metiers = [
      {'id': 1, 'label': '🧱 Maçonnerie'},
      {'id': 2, 'label': '⚡ Électricité'},
      {'id': 3, 'label': '🚰 Plomberie'},
      {'id': 4, 'label': '🪵 Menuiserie'},
    ];

    final barColor = isDark ? const Color(0xFF171721) : const Color(0xFFE5E5EA);
    final chipUnselectedColor = isDark ? const Color(0xFF232333) : const Color(0xFFD1D1D6);

    return Container(
      width: double.infinity,
      color: barColor,
      height: 48,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        itemCount: metiers.length,
        itemBuilder: (context, index) {
          final m = metiers[index];
          final isSelected = viewModel.activeMetierId == m['id'];
          return Padding(
            padding: const EdgeInsets.only(right: 8.0),
            child: InkWell(
              onTap: () => viewModel.selectMetier(m['id'] as int),
              borderRadius: BorderRadius.circular(16),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                decoration: BoxDecoration(
                  color: isSelected ? const Color(0xFFE2A000) : chipUnselectedColor,
                  borderRadius: BorderRadius.circular(16),
                ),
                alignment: Alignment.center,
                child: Text(
                  m['label'] as String,
                  style: TextStyle(
                    color: isSelected ? Colors.black : (isDark ? Colors.white : Colors.black87),
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildMessageBubble(Map<String, dynamic> msg, bool isDark) {
    final isUser = msg['role'] == 'user';
    final bubbleColor = isUser 
        ? const Color(0xFF0F5A47) 
        : (isDark ? const Color(0xFF2C2C3C) : const Color(0xFFE5E5EA));
    final bubbleTextColor = isUser ? Colors.white : (isDark ? Colors.white : Colors.black87);

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 6),
        padding: const EdgeInsets.all(12),
        constraints: const BoxConstraints(maxWidth: 280),
        decoration: BoxDecoration(
          color: bubbleColor,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(isUser ? 16 : 2),
            bottomRight: Radius.circular(isUser ? 2 : 16),
          ),
        ),
        child: Text(
          msg['content'] ?? '',
          style: TextStyle(color: bubbleTextColor, fontSize: 15),
        ),
      ),
    );
  }

  Widget _buildStreamingBubble(String text, bool isDark, Color textSecColor) {
    final bubbleColor = isDark ? const Color(0xFF232333) : const Color(0xFFE5E5EA);
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 6),
        padding: const EdgeInsets.all(12),
        constraints: const BoxConstraints(maxWidth: 280),
        decoration: BoxDecoration(
          color: bubbleColor,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(16),
            topRight: Radius.circular(16),
            bottomLeft: Radius.circular(2),
            bottomRight: Radius.circular(16),
          ),
        ),
        child: Text(
          text,
          style: TextStyle(color: textSecColor, fontSize: 15),
        ),
      ),
    );
  }

  Widget _buildChatInputArea(ChatViewModel viewModel, bool isDark, Color textColor, Color barColor) {
    final hasText = _textController.text.trim().isNotEmpty;
    return Container(
      color: barColor,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      alignment: Alignment.center,
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            Expanded(
              child: SizedBox(
                height: 50,
                child: TextField(
                  controller: _textController,
                  style: TextStyle(color: textColor, fontSize: 15),
                  onChanged: (text) => setState(() {}), // Rafraîchir pour activer/désactiver le bouton
                  decoration: InputDecoration(
                    hintText: "Posez votre question chantier...",
                    hintStyle: const TextStyle(color: Colors.grey, fontSize: 14),
                    filled: true,
                    fillColor: isDark ? const Color(0xFF222232) : Colors.white,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(24),
                      borderSide: BorderSide.none,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            IconButton(
              icon: viewModel.isStreaming
                  ? const SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(color: Colors.black, strokeWidth: 2),
                    )
                  : const Icon(Icons.send, color: Colors.black),
              onPressed: (!viewModel.isStreaming && hasText)
                  ? () {
                      final text = _textController.text;
                      _textController.clear();
                      setState(() {});
                      viewModel.sendMessage(text);
                    }
                  : null,
              style: IconButton.styleFrom(
                backgroundColor: hasText && !viewModel.isStreaming 
                    ? const Color(0xFFE2A000) 
                    : Colors.grey,
                padding: const EdgeInsets.all(12),
                shape: const CircleBorder(),
                minimumSize: const Size(48, 48),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
