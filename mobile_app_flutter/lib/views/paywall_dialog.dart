import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

/// Offres payantes (identiques à `TARIFS_PASS` côté serveur).
const List<Map<String, Object>> kOffresPass = [
  {'id': 'pass_24h', 'nom': 'Pass 24H Urgence', 'prix': 500},
  {'id': 'pass_mois', 'nom': 'Pass Mensuel Pro', 'prix': 3000},
  {'id': 'pack_50_requetes', 'nom': 'Pack 50 questions', 'prix': 1500},
];

/// Paywall Mobile Money : choix de l'offre et de l'opérateur, ouverture de la
/// page de paiement de l'opérateur (simulateur en mode démo), puis suivi du
/// statut de la transaction jusqu'à la confirmation reçue par le serveur.
class PaywallDialog extends StatefulWidget {
  final VoidCallback onDismiss;

  /// Crée le paiement : renvoie `payment_url` + `transaction_id`, ou `error`.
  final Future<Map<String, dynamic>> Function(String typePass, String operateur)
      startPayment;

  /// Statut d'une transaction ("PENDING", "ACCEPTED", "FAILED", "EXPIRED").
  final Future<String?> Function(String transactionId) checkPayment;

  /// Ouverture de l'URL de paiement (remplaçable en test).
  final Future<bool> Function(Uri url)? openUrl;

  final Duration pollInterval;

  const PaywallDialog({
    super.key,
    required this.onDismiss,
    required this.startPayment,
    required this.checkPayment,
    this.openUrl,
    this.pollInterval = const Duration(seconds: 3),
  });

  @override
  State<PaywallDialog> createState() => _PaywallDialogState();
}

class _PaywallDialogState extends State<PaywallDialog> {
  String _offre = 'pass_24h';
  bool _enCours = false;
  String? _transactionId;
  String? _message;
  bool _confirme = false;
  Timer? _poll;
  int _tentatives = 0;

  static const int _maxTentatives = 40; // ~2 minutes à 3 s d'intervalle

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<bool> _ouvrir(Uri url) {
    if (widget.openUrl != null) return widget.openUrl!(url);
    return launchUrl(url, mode: LaunchMode.externalApplication);
  }

  Future<void> _payer(String operateur) async {
    setState(() {
      _enCours = true;
      _message = null;
    });
    final res = await widget.startPayment(_offre, operateur);
    if (!mounted) return;
    if (res['error'] != null || res['payment_url'] == null) {
      setState(() {
        _enCours = false;
        _message = (res['error'] as String?) ?? 'Paiement momentanément indisponible.';
      });
      return;
    }
    final ouvert = await _ouvrir(Uri.parse(res['payment_url'] as String));
    if (!mounted) return;
    setState(() {
      _enCours = false;
      _transactionId = res['transaction_id'] as String?;
      _message = ouvert
          ? 'Finalisez le paiement puis revenez dans l\'application.'
          : 'Impossible d\'ouvrir la page de paiement.';
    });
    if (ouvert && _transactionId != null) {
      _tentatives = 0;
      _poll?.cancel();
      _poll = Timer.periodic(widget.pollInterval, (_) => _verifier());
    }
  }

  Future<void> _verifier() async {
    final id = _transactionId;
    if (id == null) return;
    _tentatives++;
    final statut = await widget.checkPayment(id);
    if (!mounted) return;
    if (statut == 'ACCEPTED') {
      _poll?.cancel();
      setState(() {
        _confirme = true;
        _message = '✅ Paiement confirmé : votre Pass est actif !';
      });
    } else if (statut == 'FAILED' || statut == 'EXPIRED') {
      _poll?.cancel();
      setState(() {
        _transactionId = null;
        _message = 'Paiement refusé ou expiré : aucun montant n\'a été débité.';
      });
    } else if (_tentatives >= _maxTentatives) {
      _poll?.cancel();
      setState(() {
        _message =
            'Confirmation en attente : votre Pass sera activé dès la confirmation de l\'opérateur.';
      });
    }
  }

  Widget _boutonOperateur(String operateur, String label, Color couleur) {
    return ElevatedButton(
      onPressed: _enCours || _confirme ? null : () => _payer(operateur),
      style: ElevatedButton.styleFrom(
        backgroundColor: couleur,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
      child: Text(label, style: const TextStyle(fontWeight: FontWeight.bold)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      backgroundColor: const Color(0xFF1E1E2C),
      title: const Text(
        '⚡ Quota épuisé',
        style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 18),
      ),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Pour continuer à poser des questions techniques sur le chantier, activez un Pass.',
              style: TextStyle(color: Colors.white70, fontSize: 14),
            ),
            const SizedBox(height: 12),
            RadioGroup<String>(
              groupValue: _offre,
              onChanged: (v) {
                if (_enCours || _confirme || v == null) return;
                setState(() => _offre = v);
              },
              child: Column(
                children: [
                  for (final offre in kOffresPass)
                    RadioListTile<String>(
                      key: Key('offre-${offre['id']}'),
                      value: offre['id'] as String,
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        '${offre['nom']} — ${offre['prix']} F CFA',
                        style: const TextStyle(color: Colors.white),
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 8),
            _boutonOperateur('WAVE', 'Payer avec Wave', const Color(0xFF1E90FF)),
            const SizedBox(height: 10),
            _boutonOperateur('ORANGE', 'Payer avec Orange Money', const Color(0xFFFF4500)),
            if (_enCours) ...[
              const SizedBox(height: 12),
              const Center(child: CircularProgressIndicator()),
            ],
            if (_message != null) ...[
              const SizedBox(height: 12),
              Text(
                _message!,
                key: const Key('paywall-message'),
                style: const TextStyle(color: Colors.white),
              ),
            ],
            if (_transactionId != null && !_confirme)
              TextButton(
                onPressed: _verifier,
                child: const Text('J\'ai payé — vérifier maintenant'),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () {
            Navigator.pop(context);
            widget.onDismiss();
          },
          child: Text(
            _confirme ? 'Continuer' : 'Plus tard',
            style: const TextStyle(color: Colors.grey),
          ),
        ),
      ],
    );
  }
}
