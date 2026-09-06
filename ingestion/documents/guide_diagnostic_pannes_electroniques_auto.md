# Guide de Diagnostic Électronique Automobile (Injection & Calculateurs)

## 1. Outils de Diagnostic de Base

- **Valise de diagnostic OBD-II** : port de diagnostic obligatoire sur tout véhicule essence depuis 2001 et diesel depuis 2004 (normes européennes, applicables à la majorité du parc importé en Côte d'Ivoire). Permet de lire les codes défauts (DTC) mémorisés par le calculateur moteur.
- **Multimètre automobile** : indispensable pour vérifier tensions d'alimentation capteurs (souvent 5V ou 12V), continuité de câblage et résistance des composants (bobines, capteurs résistifs).
- **Oscilloscope portable** : nécessaire pour les signaux dynamiques (capteur de vilebrequin, injecteurs) qu'un multimètre ne peut pas analyser correctement dans le temps.

## 2. Lecture et Interprétation des Codes Défauts

- Un code défaut (ex : P0301 "raté d'allumage cylindre 1") indique le symptôme détecté par le calculateur, **pas nécessairement la pièce défaillante en cause** : un raté d'allumage peut venir de la bougie, de la bobine, de l'injecteur ou d'une compression insuffisante du cylindre.
- **Toujours effacer les codes après réparation puis refaire un cycle de conduite d'essai** pour confirmer qu'ils ne réapparaissent pas, avant de rendre le véhicule au client.
- Un code effacé sans traitement de la cause réapparaîtra rapidement : ne jamais se contenter d'un effacement de code pour "faire disparaître" un voyant sans résoudre le problème sous-jacent.

## 3. Pannes Électroniques Fréquentes en Climat Tropical

- **Oxydation des connecteurs** : l'humidité ambiante élevée (saison des pluies) et la poussière fine (harmattan) favorisent la corrosion des contacts électriques, provoquant des faux-contacts intermittents difficiles à diagnostiquer (défauts qui n'apparaissent pas systématiquement à l'atelier).
- **Capteur de température moteur en dérive** : donne une info fausse au calculateur, provoquant un mélange air/carburant mal dosé (surconsommation, démarrage à froid difficile, ou fumée à l'échappement).
- **Sonde lambda (oxygène) encrassée** : fréquente sur carburant de qualité variable ; provoque une gestion incorrecte de la richesse du mélange et une surconsommation progressive.

## 4. Méthodologie de Diagnostic Structuré

1. Lire les codes défauts en mémoire et noter leur statut (actif / mémorisé / en attente de confirmation).
2. Consulter les paramètres en temps réel (données live) : régime moteur, température, richesse, pression collecteur, pour repérer une valeur incohérente même sans code défaut déclenché.
3. Vérifier le câblage et les connecteurs du circuit suspecté avant de remplacer un capteur ou un calculateur, l'oxydation d'un connecteur étant une cause bien plus fréquente et économique à corriger qu'une pièce électronique interne défaillante.
4. Effectuer un essai routier reproduisant les conditions du symptôme signalé par le client (à froid, en charge, à vitesse stabilisée) avant de conclure au diagnostic final.

## 5. Précautions sur les Systèmes Modernes

- **Batterie et calculateurs** : ne jamais débrancher la batterie moteur tournant, et utiliser une alimentation de secours (maintien mémoire) sur les véhicules récents pour éviter la perte de paramètres d'adaptation (ralenti, boîte automatique) qui nécessiteraient une réinitialisation en concession.
- **Reprogrammation calculateur** : à réserver aux outils constructeur ou multimarques certifiés ; une reprogrammation incomplète ou interrompue (coupure de courant pendant le flashage) peut rendre le calculateur définitivement inopérant.
