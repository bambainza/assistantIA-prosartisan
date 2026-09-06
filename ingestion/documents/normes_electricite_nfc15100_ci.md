# Normes & Bonnes Pratiques d'Installation Électrique Basse Tension (NF C 15-100 & Réseau CIE)

## 1. Dimensionnement des Conducteurs et Protections Divisionnaires

### 1.1 Sections Minimales de Câbles Cuivre et Calibres de Disjoncteurs

- **Circuit Éclairage** :
  - Section minimale du fil de cuivre : **1.5 mm²**
  - Protection : Disjoncteur magnétothermique divisionnaire **10A ou 16A**
  - Nombre maximum de points lumineux : **8 points par circuit**.
- **Prises de Courant Ordinaires (16A)** :
  - Section minimale : **2.5 mm²**
  - Protection : Disjoncteur divisionnaire **16A ou 20A**
  - Nombre maximal de prises : **8 prises sur circuit 2.5 mm²**.
- **Circuit Climatiseur / Split (Fréon)** :
  - Section minimale : **2.5 mm²** (climatiseur ≤ 1.5 CV / 12000 BTU) ou **4 mm²** (≥ 2 CV / 18000 BTU)
  - Protection dédiée obligatoire : Disjoncteur divisionnaire courbe C **16A ou 20A dédié par climatiseur**.
- **Chauffe-eau Électrique (Cumulus)** :
  - Section minimale : **2.5 mm²**
  - Protection : Disjoncteur **20A** avec interrupteur bipolaire ou disjoncteur différentiel 30 mA dédié.
- **Cuisinière / Plaque de cuisson électrique forte puissance** :
  - Section minimale : **6 mm²** en monophasé
  - Protection : Disjoncteur divisionnaire **32A**.

---

## 2. Protection Différentielle et Mise à la Terre

### 2.1 Protection Différentielle Haute Sensibilité (30 mA)

- Obligation d'installer au moins un **Interrupteur Différentiel 30 mA (Type AC ou Type A)** en tête de chaque rangée du tableau de répartition.
- **Type A** obligatoire pour les circuits alimentant des appareils électroniques, ordinateurs, onduleurs et machines à laver (sensible aux courants résiduels continus).
- **Type AC** pour les circuits prises et éclairages standards.

### 2.2 Prise de Terre et Régime de Neutre (TT)

- En Côte d'Ivoire (réseau CIE), le régime de neutre standard en distribution basse tension est le **Régime TT** (Neutre à la terre côté transformateur, masses métalliques reliées à la terre chez l'usager).
- **Valeur de résistance maximale de la terre** : **R ≤ 100 Ohms** (mesurée au tellurohmètre).
- **Réalisation pratique du puits de terre** :
  - Piquet de terre en acier cuivré de longueur minimale 1.5 m à 2 m enfoncé dans un sol humide non remblayé.
  - Câblette de terre en cuivre nu de section **25 mm²** reliant le piquet à la barrette de mesure/coupure.
  - Conducteur principal de protection (vert/jaune) de section **10 mm² ou 16 mm²** reliant la barrette au bornier de terre du tableau électrique.
  - En terrain très sec ou latéritique, utiliser de la bentonite ou du charbon végétal broyé avec du sel gemme en fond de regard pour stabiliser la conductivité.

---

## 3. Schémas de Câblage Fréquents

### 3.1 Schéma Va-et-Vient (2 points de commande pour 1 éclairage)

- **Phase (Marron/Rouge)** : Raccordée à la borne commune (L ou 1) du premier interrupteur va-et-vient.
- **Navettes (Orange ou Violet, 2 fils)** : Relient les bornes de navettes (1 et 2) du premier interrupteur aux bornes (1 et 2) du second interrupteur.
- **Retour Lampe (Noir ou Gris)** : Part de la borne commune du second interrupteur vers la lampe.
- **Neutre (Bleu clair)** : Raccordé directement à la lampe depuis le tableau ou la boîte de dérivation.
- **Terre (Vert/Jaune)** : Raccordée à la carcasse métallique du luminaire.

### 3.2 Protection contre les Surtensions et Onduleurs

- **Parafoudre / Écrêteur de surtension (Type 2)** : Recommandé en tête de tableau dans les zones à forte activité orageuse pour protéger l'appareillage contre la foudre.
- **Inverseur de source (Secteur CIE / Groupe électrogène / Solaire)** : Doit obligatoirement couper simultanément la Phase ET le Neutre (tétrapolaire en triphasé, bipolaire en monophasé) avec verrouillage mécanique pour interdire tout retour de courant vers le réseau public.
