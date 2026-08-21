import 'package:flutter/material.dart';

class PaywallDialog extends StatelessWidget {
  final VoidCallback onDismiss;
  final VoidCallback onPaymentSuccess;

  const PaywallDialog({
    super.key,
    required this.onDismiss,
    required this.onPaymentSuccess,
  });

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      backgroundColor: const Color(0xFF1E1E2C),
      title: const Row(
        children: [
          Text(
            "⚡ Quota épuisé",
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 18),
          ),
        ],
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            "Pour continuer à poser des questions techniques en illimité sur le chantier, activez un Pass d'Accès instantané.",
            style: TextStyle(color: Colors.white70, fontSize: 14),
          ),
          const SizedBox(height: 24),
          
          // Option 1 : Wave
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              onPaymentSuccess();
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF1E90FF), // Bleu Wave
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
            child: const Text(
              "Payer par Wave (500 F CFA)",
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
          ),
          const SizedBox(height: 10),
          
          // Option 2 : Orange Money
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              onPaymentSuccess();
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFFFF4500), // Orange OM
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
            child: const Text(
              "Orange Money (500 F CFA)",
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () {
            Navigator.pop(context);
            onDismiss();
          },
          child: const Text("Plus tard", style: TextStyle(color: Colors.grey)),
        ),
      ],
    );
  }
}
