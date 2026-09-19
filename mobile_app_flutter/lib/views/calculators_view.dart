import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../network/network_client.dart';

class CalculatorsView extends StatefulWidget {
  final NetworkClient networkClient;

  const CalculatorsView({super.key, required this.networkClient});

  @override
  State<CalculatorsView> createState() => _CalculatorsViewState();
}

class _CalculatorsViewState extends State<CalculatorsView>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  bool _isLoading = false;
  String? _resultText;

  // Controllers Béton
  String _betonType = 'beton_arme_fondation';
  final _betonVolController = TextEditingController(text: '1.0');

  // Controllers Électricité
  final _cablePowerController = TextEditingController(text: '3500');
  int _cableVoltage = 230;
  final _cableLengthController = TextEditingController(text: '25');

  // Controllers Plomberie
  String _plombType = 'wc';
  final _plombLengthController = TextEditingController(text: '4.0');

  // Controllers Carrelage
  final _carrSurfController = TextEditingController(text: '25');
  String _carrFormat = '60x60';
  int _carrWaste = 10;

  // Controllers Climatisation
  final _climSurfController = TextEditingController(text: '20');
  final _climHeightController = TextEditingController(text: '2.8');
  String _climSun = 'normale';
  final _climPersController = TextEditingController(text: '2');

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 5, vsync: this);
    _tabController.addListener(() {
      if (_tabController.indexIsChanging) {
        setState(() {
          _resultText = null;
        });
      }
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    _betonVolController.dispose();
    _cablePowerController.dispose();
    _cableLengthController.dispose();
    _plombLengthController.dispose();
    _carrSurfController.dispose();
    _climSurfController.dispose();
    _climHeightController.dispose();
    _climPersController.dispose();
    super.dispose();
  }

  Future<void> _runCalculation(String toolName, Map<String, dynamic> params) async {
    FocusScope.of(context).unfocus();
    setState(() {
      _isLoading = true;
      _resultText = null;
    });

    try {
      final res = await widget.networkClient.calculate(toolName, params);
      setState(() {
        _resultText = res['result_text'] as String? ?? 'Calcul effectué.';
      });
    } catch (e) {
      setState(() {
        _resultText = 'Erreur lors du calcul : $e';
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
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
        title: const Row(
          children: [
            Text(
              "🧮 Calculateurs Normés",
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white),
            ),
          ],
        ),
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          indicatorColor: primaryColor,
          labelColor: primaryColor,
          unselectedLabelColor: Colors.white60,
          tabs: const [
            Tab(icon: Icon(Icons.foundation, size: 20), text: "Béton & Mortier"),
            Tab(icon: Icon(Icons.bolt, size: 20), text: "Câblage Élec"),
            Tab(icon: Icon(Icons.water_drop, size: 20), text: "Pente Évacuation"),
            Tab(icon: Icon(Icons.grid_view, size: 20), text: "Carrelage"),
            Tab(icon: Icon(Icons.ac_unit, size: 20), text: "Climatisation"),
          ],
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Contenu de l'onglet actif
            SizedBox(
              height: 280,
              child: TabBarView(
                controller: _tabController,
                children: [
                  _buildBetonForm(cardColor, primaryColor),
                  _buildCableForm(cardColor, primaryColor),
                  _buildPlomberieForm(cardColor, primaryColor),
                  _buildCarrelageForm(cardColor, primaryColor),
                  _buildClimForm(cardColor, primaryColor),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // Indicateur de chargement
            if (_isLoading)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(16.0),
                  child: CircularProgressIndicator(color: primaryColor),
                ),
              ),

            // Carte de résultat
            if (_resultText != null)
              Container(
                margin: const EdgeInsets.only(top: 8),
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: cardColor,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: primaryColor.withValues(alpha: 0.6)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Row(
                          children: [
                            Icon(Icons.verified, color: primaryColor, size: 20),
                            SizedBox(width: 8),
                            Text(
                              "Résultat Certifié",
                              style: TextStyle(
                                color: primaryColor,
                                fontWeight: FontWeight.bold,
                                fontSize: 15,
                              ),
                            ),
                          ],
                        ),
                        IconButton(
                          icon: const Icon(Icons.copy, color: Colors.white70, size: 20),
                          tooltip: "Copier le résultat",
                          onPressed: () {
                            Clipboard.setData(ClipboardData(text: _resultText!));
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text("Résultat copié dans le presse-papier !"),
                                duration: Duration(seconds: 2),
                              ),
                            );
                          },
                        ),
                      ],
                    ),
                    const Divider(color: Colors.white24),
                    const SizedBox(height: 6),
                    Text(
                      _resultText!,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 13.5,
                        height: 1.45,
                        fontFamily: 'monospace',
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  // --- 1. Formulaire Béton ---
  Widget _buildBetonForm(Color cardColor, Color primaryColor) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          DropdownButtonFormField<String>(
            initialValue: _betonType,
            dropdownColor: cardColor,
            style: const TextStyle(color: Colors.white, fontSize: 13),
            decoration: const InputDecoration(
              labelText: "Type d'ouvrage",
              labelStyle: TextStyle(color: Colors.white70),
              border: OutlineInputBorder(),
            ),
            items: const [
              DropdownMenuItem(
                value: 'beton_arme_fondation',
                child: Text("Béton armé fondation (350 kg/m³)"),
              ),
              DropdownMenuItem(
                value: 'dalle_sol',
                child: Text("Dalle au sol / terrasse (300 kg/m³)"),
              ),
              DropdownMenuItem(
                value: 'mortier_pose_agglo',
                child: Text("Mortier pose agglos (350 kg/m³)"),
              ),
              DropdownMenuItem(
                value: 'enduit_facade',
                child: Text("Enduit de façade (400 kg/m³)"),
              ),
              DropdownMenuItem(
                value: 'chape_finition',
                child: Text("Chape de finition (300 kg/m³)"),
              ),
            ],
            onChanged: (val) => setState(() => _betonType = val!),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _betonVolController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            style: const TextStyle(color: Colors.white),
            decoration: const InputDecoration(
              labelText: "Volume nécessaire (m³)",
              labelStyle: TextStyle(color: Colors.white70),
              border: OutlineInputBorder(),
              suffixText: "m³",
            ),
          ),
          const Spacer(),
          ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              backgroundColor: primaryColor,
              foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(vertical: 12),
            ),
            icon: const Icon(Icons.calculate),
            label: const Text("Calculer le dosage", style: TextStyle(fontWeight: FontWeight.bold)),
            onPressed: () {
              final vol = double.tryParse(_betonVolController.text) ?? 1.0;
              _runCalculation('calculer_dosage_beton_mortier', {
                'type_dosage': _betonType,
                'volume_m3': vol,
              });
            },
          ),
        ],
      ),
    );
  }

  // --- 2. Formulaire Câble NF C 15-100 ---
  Widget _buildCableForm(Color cardColor, Color primaryColor) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _cablePowerController,
                  keyboardType: TextInputType.number,
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(
                    labelText: "Puissance (Watts)",
                    labelStyle: TextStyle(color: Colors.white70),
                    border: OutlineInputBorder(),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: DropdownButtonFormField<int>(
                  initialValue: _cableVoltage,
                  dropdownColor: cardColor,
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                  decoration: const InputDecoration(
                    labelText: "Tension",
                    labelStyle: TextStyle(color: Colors.white70),
                    border: OutlineInputBorder(),
                  ),
                  items: const [
                    DropdownMenuItem(value: 230, child: Text("230 V Mono")),
                    DropdownMenuItem(value: 400, child: Text("400 V Tri")),
                  ],
                  onChanged: (val) => setState(() => _cableVoltage = val!),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _cableLengthController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            style: const TextStyle(color: Colors.white),
            decoration: const InputDecoration(
              labelText: "Longueur de ligne (mètres)",
              labelStyle: TextStyle(color: Colors.white70),
              border: OutlineInputBorder(),
              suffixText: "m",
            ),
          ),
          const Spacer(),
          ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              backgroundColor: primaryColor,
              foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(vertical: 12),
            ),
            icon: const Icon(Icons.electric_bolt),
            label: const Text("Dimensionner câble", style: TextStyle(fontWeight: FontWeight.bold)),
            onPressed: () {
              final p = double.tryParse(_cablePowerController.text) ?? 3500;
              final l = double.tryParse(_cableLengthController.text) ?? 25;
              _runCalculation('calculer_section_cable_nfc15100', {
                'puissance_watts': p,
                'tension_volts': _cableVoltage,
                'longueur_metres': l,
              });
            },
          ),
        ],
      ),
    );
  }

  // --- 3. Formulaire Plomberie DTU 60.11 ---
  Widget _buildPlomberieForm(Color cardColor, Color primaryColor) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          DropdownButtonFormField<String>(
            initialValue: _plombType,
            dropdownColor: cardColor,
            style: const TextStyle(color: Colors.white, fontSize: 13),
            decoration: const InputDecoration(
              labelText: "Appareil sanitaire",
              labelStyle: TextStyle(color: Colors.white70),
              border: OutlineInputBorder(),
            ),
            items: const [
              DropdownMenuItem(value: 'wc', child: Text("WC (Ø100 mm)")),
              DropdownMenuItem(value: 'douche', child: Text("Douche / Baignoire (Ø40 mm)")),
              DropdownMenuItem(value: 'evier', child: Text("Évier / Lave-linge (Ø40-50 mm)")),
              DropdownMenuItem(value: 'lavabo', child: Text("Lavabo / Bidet (Ø32-40 mm)")),
              DropdownMenuItem(value: 'collecteur', child: Text("Collecteur général (Ø100-110 mm)")),
            ],
            onChanged: (val) => setState(() => _plombType = val!),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _plombLengthController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            style: const TextStyle(color: Colors.white),
            decoration: const InputDecoration(
              labelText: "Longueur du parcours (mètres)",
              labelStyle: TextStyle(color: Colors.white70),
              border: OutlineInputBorder(),
              suffixText: "m",
            ),
          ),
          const Spacer(),
          ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              backgroundColor: primaryColor,
              foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(vertical: 12),
            ),
            icon: const Icon(Icons.water),
            label: const Text("Calculer pente & dénivelé", style: TextStyle(fontWeight: FontWeight.bold)),
            onPressed: () {
              final l = double.tryParse(_plombLengthController.text) ?? 4.0;
              _runCalculation('calculer_pente_evacuation_dtu60', {
                'type_appareil': _plombType,
                'longueur_metres': l,
              });
            },
          ),
        ],
      ),
    );
  }

  // --- 4. Formulaire Carrelage ---
  Widget _buildCarrelageForm(Color cardColor, Color primaryColor) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _carrSurfController,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(
                    labelText: "Surface (m²)",
                    labelStyle: TextStyle(color: Colors.white70),
                    border: OutlineInputBorder(),
                    suffixText: "m²",
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: DropdownButtonFormField<String>(
                  initialValue: _carrFormat,
                  dropdownColor: cardColor,
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                  decoration: const InputDecoration(
                    labelText: "Format",
                    labelStyle: TextStyle(color: Colors.white70),
                    border: OutlineInputBorder(),
                  ),
                  items: const [
                    DropdownMenuItem(value: '60x60', child: Text("60x60 cm")),
                    DropdownMenuItem(value: '30x30', child: Text("30x30 cm")),
                    DropdownMenuItem(value: '45x45', child: Text("45x45 cm")),
                    DropdownMenuItem(value: '80x80', child: Text("80x80 cm")),
                  ],
                  onChanged: (val) => setState(() => _carrFormat = val!),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<int>(
            initialValue: _carrWaste,
            dropdownColor: cardColor,
            style: const TextStyle(color: Colors.white, fontSize: 13),
            decoration: const InputDecoration(
              labelText: "Marge découpes",
              labelStyle: TextStyle(color: Colors.white70),
              border: OutlineInputBorder(),
            ),
            items: const [
              DropdownMenuItem(value: 10, child: Text("Pose droite classique (+10%)")),
              DropdownMenuItem(value: 15, child: Text("Pose diagonale / motifs (+15%)")),
            ],
            onChanged: (val) => setState(() => _carrWaste = val!),
          ),
          const Spacer(),
          ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              backgroundColor: primaryColor,
              foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(vertical: 12),
            ),
            icon: const Icon(Icons.grid_on),
            label: const Text("Estimer carreaux & mortier-colle", style: TextStyle(fontWeight: FontWeight.bold)),
            onPressed: () {
              final s = double.tryParse(_carrSurfController.text) ?? 25;
              _runCalculation('calculer_surface_carrelage_colle', {
                'surface_m2': s,
                'format_carreau': _carrFormat,
                'pourcentage_chute': _carrWaste.toDouble(),
              });
            },
          ),
        ],
      ),
    );
  }

  // --- 5. Formulaire Climatisation ---
  Widget _buildClimForm(Color cardColor, Color primaryColor) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _climSurfController,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(
                    labelText: "Surface (m²)",
                    labelStyle: TextStyle(color: Colors.white70),
                    border: OutlineInputBorder(),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: TextField(
                  controller: _climHeightController,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(
                    labelText: "Hauteur (m)",
                    labelStyle: TextStyle(color: Colors.white70),
                    border: OutlineInputBorder(),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<String>(
                  initialValue: _climSun,
                  dropdownColor: cardColor,
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                  decoration: const InputDecoration(
                    labelText: "Exposition",
                    labelStyle: TextStyle(color: Colors.white70),
                    border: OutlineInputBorder(),
                  ),
                  items: const [
                    DropdownMenuItem(value: 'normale', child: Text("Normale / Ombragé")),
                    DropdownMenuItem(value: 'forte', child: Text("Forte / Ouest / Tôle")),
                  ],
                  onChanged: (val) => setState(() => _climSun = val!),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: TextField(
                  controller: _climPersController,
                  keyboardType: TextInputType.number,
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(
                    labelText: "Occupants",
                    labelStyle: TextStyle(color: Colors.white70),
                    border: OutlineInputBorder(),
                  ),
                ),
              ),
            ],
          ),
          const Spacer(),
          ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              backgroundColor: primaryColor,
              foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(vertical: 12),
            ),
            icon: const Icon(Icons.ac_unit),
            label: const Text("Calculer puissance BTU/h", style: TextStyle(fontWeight: FontWeight.bold)),
            onPressed: () {
              final s = double.tryParse(_climSurfController.text) ?? 20;
              final h = double.tryParse(_climHeightController.text) ?? 2.8;
              final p = int.tryParse(_climPersController.text) ?? 2;
              _runCalculation('calculer_bilan_thermique_climatisation', {
                'surface_m2': s,
                'hauteur_sous_plafond': h,
                'exposition_soleil': _climSun,
                'nombre_personnes': p,
              });
            },
          ),
        ],
      ),
    );
  }
}
