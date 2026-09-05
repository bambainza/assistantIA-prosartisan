import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../viewmodels/chat_viewmodel.dart';

class OfflineSheetsView extends StatelessWidget {
  const OfflineSheetsView({super.key});

  @override
  Widget build(BuildContext context) {
    final viewModel = Provider.of<ChatViewModel>(context);
    final isDark = viewModel.isDarkTheme;
    final textColor = isDark ? Colors.white : Colors.black87;
    final textSecColor = isDark ? Colors.white60 : Colors.black54;
    final barColor = isDark ? const Color(0xFF171721) : const Color(0xFFE5E5EA);
    final cardBg = isDark ? const Color(0xFF232333) : Colors.white;

    final sheets = viewModel.starredSheets;

    return Scaffold(
      backgroundColor: isDark ? const Color(0xFF13131A) : const Color(0xFFF5F5F7),
      appBar: AppBar(
        backgroundColor: barColor,
        elevation: 0,
        title: Text(
          "📁 Mes Fiches Chantier (Hors-Ligne)",
          style: TextStyle(color: textColor, fontSize: 17, fontWeight: FontWeight.bold),
        ),
        iconTheme: IconThemeData(color: textColor),
      ),
      body: sheets.isEmpty
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.bookmark_border, size: 64, color: Color(0xFFE2A000)),
                    const SizedBox(height: 16),
                    Text(
                      "Aucune fiche épinglée",
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: textColor),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      "Sur vos chantiers, appuyez sur l'icône ⭐ sous les réponses de l'IA pour les conserver ici et les consulter sans connexion internet.",
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 14, color: textSecColor),
                    ),
                  ],
                ),
              ),
            )
          : ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: sheets.length,
              itemBuilder: (context, index) {
                final sheet = sheets[index];
                final sheetId = sheet['id']?.toString() ?? '';
                final content = sheet['content']?.toString() ?? '';
                final title = sheet['title']?.toString() ?? 'Fiche Technique';
                final date = sheet['savedAt'] != null 
                    ? sheet['savedAt'].toString().split('T').first 
                    : 'Récemment';

                final isSpeaking = viewModel.isSpeakingMessage(sheetId);

                return Card(
                  color: cardBg,
                  margin: const EdgeInsets.symmetric(vertical: 8),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                    side: BorderSide(color: const Color(0xFFE2A000).withValues(alpha: 0.3)),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(14.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                              decoration: BoxDecoration(
                                color: const Color(0xFFE2A000).withValues(alpha: 0.2),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                "📌 Fiche Sauvegardée • $date",
                                style: const TextStyle(
                                  color: Color(0xFFE2A000),
                                  fontSize: 11,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                            IconButton(
                              icon: const Icon(Icons.delete_outline, color: Colors.redAccent, size: 20),
                              onPressed: () => viewModel.removeStarredSheet(sheetId),
                              tooltip: "Supprimer la fiche",
                            ),
                          ],
                        ),
                        if (title.isNotEmpty && title != 'Fiche Technique') ...[
                          const SizedBox(height: 6),
                          Text(
                            title,
                            style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: textColor),
                          ),
                        ],
                        const SizedBox(height: 8),
                        Text(
                          content,
                          style: TextStyle(fontSize: 14, color: textColor, height: 1.4),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            ElevatedButton.icon(
                              icon: Icon(
                                isSpeaking ? Icons.stop : Icons.volume_up,
                                size: 16,
                                color: Colors.black,
                              ),
                              label: Text(
                                isSpeaking ? "Arrêter" : "Écouter la fiche",
                                style: const TextStyle(color: Colors.black, fontSize: 12, fontWeight: FontWeight.bold),
                              ),
                              style: ElevatedButton.styleFrom(
                                backgroundColor: const Color(0xFFE2A000),
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                              ),
                              onPressed: () => viewModel.toggleSpeak(sheetId, content),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }
}
