import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../network/network_client.dart';

class QuoteItem {
  String description;
  double quantite;
  String unite;
  double prixUnitaire;

  QuoteItem({
    required this.description,
    this.quantite = 1.0,
    this.unite = 'u',
    this.prixUnitaire = 0.0,
  });

  double get total => quantite * prixUnitaire;

  Map<String, dynamic> toJson() => {
        'description': description,
        'quantite': quantite,
        'unite': unite,
        'prix_unitaire': prixUnitaire,
      };

  factory QuoteItem.fromJson(Map<String, dynamic> json) => QuoteItem(
        description: json['description'] as String? ?? '',
        quantite: (json['quantite'] as num?)?.toDouble() ?? 1.0,
        unite: json['unite'] as String? ?? 'u',
        prixUnitaire: (json['prix_unitaire'] as num?)?.toDouble() ?? 0.0,
      );
}

class QuotesView extends StatefulWidget {
  final NetworkClient networkClient;

  const QuotesView({super.key, required this.networkClient});

  @override
  State<QuotesView> createState() => _QuotesViewState();
}

class _QuotesViewState extends State<QuotesView> {
  final _promptController = TextEditingController();
  final _clientNomController = TextEditingController();
  final _clientPhoneController = TextEditingController();
  final _clientAddressController = TextEditingController();

  String _docType = 'devis';
  bool _isExtracting = false;
  bool _isSaving = false;
  String? _savedQuoteNum;

  final List<QuoteItem> _items = [
    QuoteItem(description: 'Prestation principale', quantite: 1, unite: 'u', prixUnitaire: 25000),
  ];

  @override
  void dispose() {
    _promptController.dispose();
    _clientNomController.dispose();
    _clientPhoneController.dispose();
    _clientAddressController.dispose();
    super.dispose();
  }

  double get _totalHT => _items.fold(0.0, (sum, it) => sum + it.total);
  double get _totalTVA => _totalHT * 0.18;
  double get _totalTTC => _totalHT + _totalTVA;

  Future<void> _extractFromPrompt() async {
    final text = _promptController.text.trim();
    if (text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Veuillez saisir ou dicter vos notes de chantier.")),
      );
      return;
    }

    FocusScope.of(context).unfocus();
    setState(() => _isExtracting = true);

    try {
      final res = await widget.networkClient.extractQuote(text);
      if (mounted) {
        setState(() {
          _clientNomController.text = res['client_nom'] as String? ?? '';
          _clientPhoneController.text = res['client_telephone'] as String? ?? '';
          _clientAddressController.text = res['client_adresse'] as String? ?? '';

          final rawItems = res['items'] as List<dynamic>? ?? [];
          _items.clear();
          if (rawItems.isNotEmpty) {
            for (final item in rawItems) {
              if (item is Map) {
                _items.add(QuoteItem.fromJson(Map<String, dynamic>.from(item)));
              }
            }
          } else {
            _items.add(QuoteItem(description: 'Travaux généraux', quantite: 1, unite: 'forfait', prixUnitaire: 50000));
          }
        });

        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Devis structuré avec succès par l'IA !")),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Erreur d'analyse : $e")),
        );
      }
    } finally {
      if (mounted) setState(() => _isExtracting = false);
    }
  }

  Future<void> _saveQuote() async {
    if (_items.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Ajoutez au moins une ligne de prestation.")),
      );
      return;
    }

    setState(() => _isSaving = true);
    try {
      final payload = {
        'titre': 'Devis travaux',
        'type_document': _docType,
        'client_nom': _clientNomController.text.trim().isEmpty ? 'Client' : _clientNomController.text.trim(),
        'client_telephone': _clientPhoneController.text.trim(),
        'client_adresse': _clientAddressController.text.trim(),
        'taux_tva': 18.0,
        'items': _items.map((e) => e.toJson()).toList(),
      };

      final res = await widget.networkClient.createQuote(payload);
      if (mounted) {
        setState(() {
          _savedQuoteNum = res['numero_devis'] as String?;
        });

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text("Devis ${_savedQuoteNum ?? ''} enregistré avec succès !"),
            backgroundColor: Colors.green[700],
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Erreur de sauvegarde : $e")),
        );
      }
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  void _shareWhatsApp() {
    if (_items.isEmpty) return;

    final clientName = _clientNomController.text.trim().isEmpty ? 'Client' : _clientNomController.text.trim();
    final clientPhone = _clientPhoneController.text.trim();
    final address = _clientAddressController.text.trim();

    final buffer = StringBuffer();
    buffer.writeln("🛠️ *${_docType.toUpperCase()} PROSARTISAN*");
    buffer.writeln("👤 *Client :* $clientName ${clientPhone.isNotEmpty ? '($clientPhone)' : ''}");
    if (address.isNotEmpty) buffer.writeln("📍 *Lieu :* $address");
    buffer.writeln();
    buffer.writeln("*DÉTAILS DES PRESTATIONS :*");

    for (int i = 0; i < _items.length; i++) {
      final it = _items[i];
      buffer.writeln("${i + 1}. ${it.description} - ${it.quantite} ${it.unite} × ${it.prixUnitaire.toStringAsFixed(0)} = *${it.total.toStringAsFixed(0)} FCFA*");
    }

    buffer.writeln();
    buffer.writeln("💰 *Total HT :* ${_totalHT.toStringAsFixed(0)} FCFA");
    buffer.writeln("💵 *Total TTC (TVA 18%) :* *${_totalTTC.toStringAsFixed(0)} FCFA*");
    buffer.writeln();
    buffer.writeln("_Devis généré avec l'Assistant ProsArtisan IA Expert_");

    Clipboard.setData(ClipboardData(text: buffer.toString()));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text("Texte du devis copié ! Prêt à coller dans WhatsApp."),
        duration: Duration(seconds: 3),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    const primaryColor = Color(0xFFE2A000);
    const bgColor = Color(0xFF101018);
    const cardColor = Color(0xFF1A1A26);

    return Scaffold(
      backgroundColor: bgColor,
      appBar: AppBar(
        backgroundColor: const Color(0xFF171721),
        elevation: 0,
        title: const Text(
          "📄 Devis & Factures Express",
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Zone d'extraction IA
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: cardColor,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: primaryColor.withValues(alpha: 0.3)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    "✨ Saisie rapide / Notes de chantier",
                    style: TextStyle(color: primaryColor, fontWeight: FontWeight.bold, fontSize: 14),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _promptController,
                    maxLines: 3,
                    style: const TextStyle(color: Colors.white, fontSize: 13),
                    decoration: const InputDecoration(
                      hintText: "ex: Devis M. Kouadio à Yopougon : pose tableau élec 8 modules 35000 F, 3 prises étanches 15000 F, raccordement général 20000 F.",
                      hintStyle: TextStyle(color: Colors.white38, fontSize: 12),
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 10),
                  ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: primaryColor,
                      foregroundColor: Colors.black,
                    ),
                    icon: _isExtracting
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black),
                          )
                        : const Icon(Icons.auto_awesome),
                    label: Text(
                      _isExtracting ? "Analyse en cours..." : "Analyser & Chiffrer automatiquement",
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    onPressed: _isExtracting ? null : _extractFromPrompt,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // En-tête Client
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: cardColor,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _clientNomController,
                          style: const TextStyle(color: Colors.white),
                          decoration: const InputDecoration(
                            labelText: "Client",
                            labelStyle: TextStyle(color: Colors.white70),
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: TextField(
                          controller: _clientPhoneController,
                          keyboardType: TextInputType.phone,
                          style: const TextStyle(color: Colors.white),
                          decoration: const InputDecoration(
                            labelText: "Téléphone",
                            labelStyle: TextStyle(color: Colors.white70),
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _clientAddressController,
                          style: const TextStyle(color: Colors.white),
                          decoration: const InputDecoration(
                            labelText: "Localisation",
                            labelStyle: TextStyle(color: Colors.white70),
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          initialValue: _docType,
                          dropdownColor: cardColor,
                          style: const TextStyle(color: Colors.white, fontSize: 13),
                          decoration: const InputDecoration(
                            labelText: "Type",
                            labelStyle: TextStyle(color: Colors.white70),
                            border: OutlineInputBorder(),
                          ),
                          items: const [
                            DropdownMenuItem(value: 'devis', child: Text("Devis")),
                            DropdownMenuItem(value: 'facture_proforma', child: Text("Pro-Forma")),
                            DropdownMenuItem(value: 'facture', child: Text("Facture")),
                          ],
                          onChanged: (val) => setState(() => _docType = val!),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // Lignes du devis
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: cardColor,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        "Lignes de prestations",
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14),
                      ),
                      TextButton.icon(
                        icon: const Icon(Icons.add, size: 18, color: primaryColor),
                        label: const Text("Ajouter", style: TextStyle(color: primaryColor)),
                        onPressed: () {
                          setState(() {
                            _items.add(QuoteItem(description: '', quantite: 1, unite: 'u', prixUnitaire: 0));
                          });
                        },
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  ListView.separated(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: _items.length,
                    separatorBuilder: (_, __) => const Divider(color: Colors.white12),
                    itemBuilder: (context, index) {
                      final item = _items[index];
                      return Row(
                        children: [
                          Expanded(
                            flex: 3,
                            child: TextFormField(
                              initialValue: item.description,
                              style: const TextStyle(color: Colors.white, fontSize: 13),
                              decoration: const InputDecoration(
                                hintText: "Désignation",
                                hintStyle: TextStyle(color: Colors.white30),
                                isDense: true,
                              ),
                              onChanged: (val) => item.description = val,
                            ),
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            flex: 1,
                            child: TextFormField(
                              initialValue: item.quantite.toString(),
                              keyboardType: TextInputType.number,
                              style: const TextStyle(color: Colors.white, fontSize: 13),
                              decoration: const InputDecoration(hintText: "Qté", isDense: true),
                              onChanged: (val) {
                                setState(() {
                                  item.quantite = double.tryParse(val) ?? 1.0;
                                });
                              },
                            ),
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            flex: 2,
                            child: TextFormField(
                              initialValue: item.prixUnitaire.toStringAsFixed(0),
                              keyboardType: TextInputType.number,
                              style: const TextStyle(color: Colors.white, fontSize: 13),
                              decoration: const InputDecoration(hintText: "Prix U.", isDense: true),
                              onChanged: (val) {
                                setState(() {
                                  item.prixUnitaire = double.tryParse(val) ?? 0.0;
                                });
                              },
                            ),
                          ),
                          IconButton(
                            icon: const Icon(Icons.delete_outline, color: Colors.redAccent, size: 20),
                            onPressed: () {
                              setState(() {
                                _items.removeAt(index);
                              });
                            },
                          ),
                        ],
                      );
                    },
                  ),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // Carte des Totaux
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: cardColor,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.white12),
              ),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text("Total HT :", style: TextStyle(color: Colors.white70)),
                      Text("${_totalHT.toStringAsFixed(0)} FCFA", style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text("TVA (18%) :", style: TextStyle(color: Colors.white70)),
                      Text("${_totalTVA.toStringAsFixed(0)} FCFA", style: const TextStyle(color: Colors.white70)),
                    ],
                  ),
                  const Divider(color: Colors.white24, height: 16),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text("Total TTC :", style: TextStyle(color: primaryColor, fontWeight: FontWeight.bold, fontSize: 16)),
                      Text("${_totalTTC.toStringAsFixed(0)} FCFA", style: const TextStyle(color: primaryColor, fontWeight: FontWeight.bold, fontSize: 16)),
                    ],
                  ),
                ],
              ),
            ),

            const SizedBox(height: 20),

            // Actions d'export & Sauvegarde
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white,
                      side: const BorderSide(color: Colors.white30),
                      padding: const EdgeInsets.symmetric(vertical: 12),
                    ),
                    icon: _isSaving
                        ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.save),
                    label: const Text("Enregistrer"),
                    onPressed: _isSaving ? null : _saveQuote,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF25D366),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                    ),
                    icon: const Icon(Icons.chat),
                    label: const Text("WhatsApp", style: TextStyle(fontWeight: FontWeight.bold)),
                    onPressed: _shareWhatsApp,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
