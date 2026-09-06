# Guide Technique d'Installation Solaire Photovoltaïque en Côte d'Ivoire

## 1. Dimensionnement d'une Installation Résidentielle

### 1.1 Estimation du Besoin Énergétique

- Lister les équipements et leur puissance (ex : réfrigérateur 150 W, éclairage LED 10 W/point, télévision 80 W, ventilateur 60 W) et leur durée d'usage quotidien pour obtenir la consommation en Wh/jour.
- Prévoir une marge de sécurité de 20 à 30% sur le dimensionnement pour absorber les pertes de conversion (onduleur, câblage) et les jours de faible ensoleillement (saison des pluies, harmattan poussiéreux réduisant le rayonnement).

### 1.2 Ensoleillement en Côte d'Ivoire

- Irradiation moyenne : environ 4,5 à 5,5 kWh/m²/jour selon la région (plus élevée au nord, réduite au sud et en zone lagunaire à cause de la nébulosité).
- Orientation optimale des panneaux : plein sud avec une inclinaison de 5 à 10° (proximité de l'équateur), suffisante pour l'écoulement des eaux de pluie sans sur-inclinaison inutile.

## 2. Composants du Système

- **Panneaux photovoltaïques** : monocristallins (meilleur rendement, préférés en surface de toit limitée) ou polycristallins (coût moindre, surface plus importante requise).
- **Régulateur de charge MPPT** : à privilégier systématiquement sur PWM pour son meilleur rendement (5 à 20% de production supplémentaire), essentiel en système autonome avec batteries.
- **Batteries** : lithium (LiFePO4, cycles de vie élevés ~3000 à 5000 cycles, tolère mieux la chaleur ambiante) recommandées sur les batteries plomb-acide classiques (cycles de vie plus courts, dégradation accélérée par les températures élevées fréquentes en Côte d'Ivoire).
- **Onduleur (inverter)** : convertit le courant continu (DC) des panneaux/batteries en courant alternatif (AC) 220V pour les appareils domestiques ; dimensionner sa puissance nominale au-dessus de la somme des puissances des appareils démarrés simultanément (pic de démarrage des moteurs, réfrigérateur notamment).

## 3. Installation et Sécurité Électrique

- **Câblage DC** : sections de câbles dimensionnées pour limiter la chute de tension à moins de 3% entre panneaux et régulateur, avec protection par fusible/disjoncteur DC adapté à la tension du système (12V, 24V ou 48V).
- **Mise à la terre** : le cadre métallique des panneaux et la structure de fixation doivent être reliés à la terre pour la protection contre les décharges électrostatiques et la foudre, fréquente en saison des pluies en Afrique de l'Ouest.
- **Parafoudre DC** : fortement recommandé en toiture exposée compte tenu de la fréquence des orages tropicaux, pour protéger le régulateur et l'onduleur des surtensions induites.
- **Fixation au vent** : les structures de fixation doivent être dimensionnées pour résister aux vents de saison des tornades (mars-avril), avec ancrages renforcés sur toiture en tôle.

## 4. Entretien Préventif

- Nettoyage des panneaux tous les 15 à 30 jours en saison sèche (harmattan, poussière) pour maintenir le rendement, à l'eau claire sans détergent abrasif, de préférence tôt le matin ou en fin de journée pour éviter le choc thermique sur le verre.
- Vérification annuelle du serrage des connexions électriques (les cycles de dilatation thermique jour/nuit desserrent progressivement les bornes).
- Contrôle de la tension de charge des batteries plomb-acide (niveau d'électrolyte) tous les 2 à 3 mois si ce type de batterie est utilisé.

## 5. Systèmes Hybrides (Solaire + Réseau CIE)

- Un système hybride permet de basculer automatiquement sur le réseau de la Compagnie Ivoirienne d'Électricité (CIE) en cas d'ensoleillement insuffisant ou de batteries déchargées, garantissant la continuité de service.
- Le point de bascule doit intégrer un dispositif anti-retour empêchant toute injection de courant vers le réseau CIE, obligatoire pour la sécurité des techniciens intervenant sur le réseau public.
