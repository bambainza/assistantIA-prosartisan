# 🚀Assistan IA ProsArtisan

Assistant Ia permettant l'aide technique aux artisans

## 📋 Prérequis techniques
* PHP >= 8.2 / Node.js >= 20
* PostgreSQL >= 15
* Composer & NPM

## 🛠️ Installation en local

1. Cloner le dépôt :
   `git clone git@github.com:organisation/projet.git`
2. Installer les dépendances :
   `composer install && npm install`
3. Configurer l'environnement :
   `cp .env.example .env` (Puis ajoutez vos clés de base de données)
4. Générer la clé d'application et migrer :
   `php artisan key:generate && php artisan migrate`

## 🧪 Lancement des Tests
L'exécution des tests est obligatoire avant toute Pull Request.
`php artisan test`

## 🏗️ Architecture et Décisions Techniques
(Optionnel) Mentionnez ici les choix majeurs (ex: utilisation de Qdrant pour la recherche vectorielle, architecture orientée services, etc.).