import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../viewmodels/chat_viewmodel.dart';
import 'offline_sheets_view.dart';
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

    if (viewModel.isStreaming || viewModel.messages.isNotEmpty) {
      _scrollToBottom();
    }

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
        viewModel.dismissPaywall();
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
            Row(
              children: [
                Text(
                  "ProsArtisan IA",
                  style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: textColor),
                ),
                if (viewModel.isOffline) ...[
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: Colors.orange.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.cloud_off, size: 12, color: Colors.orange),
                        SizedBox(width: 4),
                        Text(
                          "Hors-ligne",
                          style: TextStyle(fontSize: 10, color: Colors.orange, fontWeight: FontWeight.bold),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
            Text(
              "Abonnement: ${viewModel.quotaRestant != null && viewModel.quotaRestant! > 10 ? "Pro Illimité" : "Gratuit (5/jour)"}",
              style: TextStyle(fontSize: 11, color: textSecColor),
            ),
          ],
        ),
        iconTheme: IconThemeData(color: textColor),
        actions: [
          IconButton(
            icon: const Icon(Icons.bookmark_border, color: Color(0xFFE2A000)),
            tooltip: "Fiches Chantier Hors-Ligne",
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const OfflineSheetsView()),
              );
            },
          ),
          IconButton(
            icon: Icon(
              isDark ? Icons.brightness_7 : Icons.brightness_4,
              color: const Color(0xFFE2A000),
            ),
            onPressed: () => viewModel.toggleTheme(),
          ),
          IconButton(
            icon: const Icon(Icons.add, color: Color(0xFFE2A000)),
            tooltip: "Nouvelle discussion",
            onPressed: () => viewModel.createConversation(),
          ),
          IconButton(
            icon: Icon(Icons.logout, color: textSecColor),
            tooltip: "Déconnexion",
            onPressed: () => viewModel.logout(),
          ),
        ],
      ),
      drawer: _buildDrawer(viewModel, isDark, textColor, textSecColor, barColor),
      body: Column(
        children: [
          _buildMetierSelectorRow(viewModel, isDark, textColor),

          // Liste des messages
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              itemCount: viewModel.messages.length + (viewModel.isStreaming ? 1 : 0),
              itemBuilder: (context, index) {
                if (index < viewModel.messages.length) {
                  final msg = viewModel.messages[index];
                  return _buildMessageBubble(msg, viewModel, isDark, textColor);
                } else {
                  return _buildStreamingBubble(viewModel.currentStreamText, isDark, textSecColor);
                }
              },
            ),
          ),

          // Prévisualisation de la photo sélectionnée
          if (viewModel.attachedImageBytes != null)
            _buildImageAttachmentPreview(viewModel, isDark, textColor),

          // Barre d'enregistrement vocal en cours
          if (viewModel.isRecording || viewModel.isTranscribing)
            _buildAudioRecordingBar(viewModel, isDark, textColor),

          // Zone de saisie principale
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
                const Icon(Icons.engineering, size: 42, color: Color(0xFFE2A000)),
                const SizedBox(height: 8),
                Text(
                  "ProsArtisan Discussions",
                  style: TextStyle(color: textColor, fontSize: 16, fontWeight: FontWeight.bold),
                ),
                Text(
                  viewModel.client.userEmail ?? "",
                  style: TextStyle(color: textSecColor, fontSize: 12),
                ),
              ],
            ),
          ),
          ListTile(
            leading: const Icon(Icons.bookmark, color: Color(0xFFE2A000)),
            title: Text(
              "Fiches Chantier (${viewModel.starredSheets.length})",
              style: TextStyle(color: textColor, fontWeight: FontWeight.bold, fontSize: 14),
            ),
            subtitle: Text(
              "Consultable sans connexion",
              style: TextStyle(color: textSecColor, fontSize: 11),
            ),
            onTap: () {
              Navigator.pop(context);
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const OfflineSheetsView()),
              );
            },
          ),
          const Divider(),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
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
                        fontSize: 13,
                        fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
                      ),
                    ),
                    onTap: () {
                      Navigator.pop(context);
                      viewModel.selectConversation(conv['id']);
                    },
                    trailing: IconButton(
                      icon: Icon(Icons.delete, color: isActive ? Colors.black54 : Colors.redAccent, size: 16),
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
      {'id': 5, 'label': '📐 Carrelage'},
      {'id': 6, 'label': '🎨 Peinture'},
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
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
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

  Widget _buildMessageBubble(
    Map<String, dynamic> msg,
    ChatViewModel viewModel,
    bool isDark,
    Color textColor,
  ) {
    final isUser = msg['role'] == 'user';
    final msgId = msg['id']?.toString() ?? '';
    final content = msg['content'] ?? '';
    final isSpeaking = viewModel.isSpeakingMessage(msgId);
    final isStarred = viewModel.isSheetStarred(msgId);

    final bubbleColor = isUser 
        ? const Color(0xFF0F5A47) 
        : (isDark ? const Color(0xFF2C2C3C) : const Color(0xFFE5E5EA));
    final bubbleTextColor = isUser ? Colors.white : (isDark ? Colors.white : Colors.black87);

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 6),
        padding: const EdgeInsets.all(12),
        constraints: const BoxConstraints(maxWidth: 300),
        decoration: BoxDecoration(
          color: bubbleColor,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(isUser ? 16 : 2),
            bottomRight: Radius.circular(isUser ? 2 : 16),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Vignette image jointe si envoyée par l'utilisateur
            if (msg.containsKey('image_bytes') && msg['image_bytes'] != null) ...[
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.memory(
                  msg['image_bytes'],
                  height: 160,
                  width: double.infinity,
                  fit: BoxFit.cover,
                ),
              ),
              const SizedBox(height: 8),
            ],

            Text(
              content,
              style: TextStyle(color: bubbleTextColor, fontSize: 14, height: 1.35),
            ),

            // Barre d'actions pour l'assistant : TTS + Épingler Fiche Chantier
            if (!isUser && content.isNotEmpty) ...[
              const SizedBox(height: 8),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  InkWell(
                    onTap: () => viewModel.toggleSpeak(msgId, content),
                    borderRadius: BorderRadius.circular(4),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            isSpeaking ? Icons.stop_circle : Icons.volume_up,
                            size: 16,
                            color: const Color(0xFFE2A000),
                          ),
                          const SizedBox(width: 4),
                          Text(
                            isSpeaking ? "Arrêter" : "Écouter",
                            style: const TextStyle(
                              color: Color(0xFFE2A000),
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  InkWell(
                    onTap: () => viewModel.toggleStarSheet(msg),
                    borderRadius: BorderRadius.circular(4),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            isStarred ? Icons.star : Icons.star_border,
                            size: 16,
                            color: const Color(0xFFE2A000),
                          ),
                          const SizedBox(width: 4),
                          Text(
                            isStarred ? "Fiche épinglée" : "Épingler fiche",
                            style: TextStyle(
                              color: isStarred ? const Color(0xFFE2A000) : (isDark ? Colors.white60 : Colors.black54),
                              fontSize: 11,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ],
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
        constraints: const BoxConstraints(maxWidth: 300),
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
          style: TextStyle(color: textSecColor, fontSize: 14),
        ),
      ),
    );
  }

  Widget _buildImageAttachmentPreview(ChatViewModel viewModel, bool isDark, Color textColor) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      color: isDark ? const Color(0xFF1E1E2C) : const Color(0xFFE0E0E0),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: Image.memory(
              viewModel.attachedImageBytes!,
              width: 48,
              height: 48,
              fit: BoxFit.cover,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              viewModel.attachedImageName ?? "Photo de chantier jointe",
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 12, color: textColor, fontWeight: FontWeight.bold),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.close, color: Colors.redAccent, size: 20),
            onPressed: () => viewModel.clearAttachedImage(),
            tooltip: "Supprimer la photo",
          ),
        ],
      ),
    );
  }

  Widget _buildAudioRecordingBar(ChatViewModel viewModel, bool isDark, Color textColor) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: Colors.redAccent.withValues(alpha: 0.15),
      child: Row(
        children: [
          const Icon(Icons.mic, color: Colors.redAccent, size: 22),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              viewModel.isTranscribing
                  ? "Transcription de votre note vocale en cours..."
                  : "Enregistrement en cours... Parlez maintenant",
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Colors.redAccent),
            ),
          ),
          if (viewModel.isRecording) ...[
            TextButton(
              onPressed: () => viewModel.cancelAudioRecording(),
              child: const Text("Annuler", style: TextStyle(color: Colors.grey, fontSize: 12)),
            ),
            ElevatedButton.icon(
              icon: const Icon(Icons.check, size: 16, color: Colors.white),
              label: const Text("Valider", style: TextStyle(color: Colors.white, fontSize: 12)),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.redAccent,
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              ),
              onPressed: () async {
                final text = await viewModel.stopAudioRecordingAndTranscribe();
                if (text != null && text.isNotEmpty) {
                  _textController.text = text;
                  setState(() {});
                }
              },
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildChatInputArea(ChatViewModel viewModel, bool isDark, Color textColor, Color barColor) {
    final hasText = _textController.text.trim().isNotEmpty || viewModel.attachedImageBytes != null;
    return Container(
      color: barColor,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      alignment: Alignment.center,
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            // Bouton Caméra Photo
            IconButton(
              icon: const Icon(Icons.camera_alt, color: Color(0xFFE2A000), size: 22),
              tooltip: "Prendre une photo du chantier",
              onPressed: () => viewModel.pickImageFromCamera(),
            ),

            // Bouton Galerie
            IconButton(
              icon: const Icon(Icons.image, color: Color(0xFFE2A000), size: 22),
              tooltip: "Choisir depuis la galerie",
              onPressed: () => viewModel.pickImageFromGallery(),
            ),

            // Bouton Micro (StT)
            IconButton(
              icon: Icon(
                viewModel.isRecording ? Icons.stop : Icons.mic,
                color: viewModel.isRecording ? Colors.redAccent : const Color(0xFFE2A000),
                size: 22,
              ),
              tooltip: "Dictée vocale chantier",
              onPressed: () async {
                if (viewModel.isRecording) {
                  final text = await viewModel.stopAudioRecordingAndTranscribe();
                  if (text != null && text.isNotEmpty) {
                    _textController.text = text;
                    setState(() {});
                  }
                } else {
                  await viewModel.startAudioRecording();
                }
              },
            ),

            // Champ de saisie
            Expanded(
              child: SizedBox(
                height: 46,
                child: TextField(
                  controller: _textController,
                  style: TextStyle(color: textColor, fontSize: 14),
                  onChanged: (_) => setState(() {}),
                  decoration: InputDecoration(
                    hintText: "Question chantier ou photo...",
                    hintStyle: const TextStyle(color: Colors.grey, fontSize: 13),
                    filled: true,
                    fillColor: isDark ? const Color(0xFF222232) : Colors.white,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(24),
                      borderSide: BorderSide.none,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 8),

            // Bouton Envoyer
            IconButton(
              icon: viewModel.isStreaming
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(color: Colors.black, strokeWidth: 2),
                    )
                  : const Icon(Icons.send, color: Colors.black, size: 20),
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
                padding: const EdgeInsets.all(10),
                shape: const CircleBorder(),
                minimumSize: const Size(42, 42),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
