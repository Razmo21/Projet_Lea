# AGENTS.md — Instructions obligatoires pour Codex

Tu travailles sur le Projet Léa.

## Règle absolue

Travaille uniquement sur la tâche explicitement demandée.

N'anticipe jamais l'étape suivante.

N'ajoute jamais une fonctionnalité « utile pour plus tard » sans demande explicite.

## Priorités

1. Fonctionnement.
2. Simplicité.
3. Lisibilité.
4. Stabilité.
5. Tests.
6. Performance.
7. Fonctionnalités supplémentaires.

## Méthode de travail

Avant toute modification :
1. Lis `README.md`.
2. Lis `TODO.md`.
3. Lis `AGENTS.md`.
4. Identifie précisément la tâche.
5. Explique brièvement ce que tu vas faire.
6. Liste les fichiers et dépendances concernés.

Après modification :
1. Lance les vérifications adaptées.
2. Vérifie que le projet démarre.
3. Liste les fichiers créés ou modifiés.
4. Indique les commandes utilisées.
5. Signale clairement les erreurs restantes.
6. Arrête-toi et attends la validation de l'utilisateur.

## Étape actuelle

Étape 8 terminée — conversations locales persistantes, fiables et contrôlées.

Attendre la validation de l'utilisateur avant toute étape suivante.

## Interdictions actuelles

Ne crée PAS :
- un nouveau backend FastAPI ;
- un nouveau serveur Python ;
- un nouveau modèle local ;
- une nouvelle installation de llama.cpp ;
- RAG ;
- accès à IA_WORKSPACE ;
- accès Internet ;
- profils multiples ;
- Tauri ;
- Docker ;
- authentification ;
- télémétrie.

## Validation de l'étape

L'étape est terminée uniquement si :
- le modèle fonctionne avec une fenêtre de 8 192 tokens, un seul slot et sans
  raisonnement interne exposé ou persisté ;
- SQLite conserve les conversations dans `data/lea.sqlite3`, avec migrations,
  WAL, clés étrangères, révisions et reprise sûre des générations interrompues ;
- le backend reste l'unique autorité de l'historique envoyé au modèle ;
- l'interface permet de créer, retrouver, rechercher, renommer, supprimer,
  modifier, régénérer et réessayer les conversations ;
- les conflits entre onglets sont refusés sans écrasement silencieux ;
- `.\lea.ps1 start`, `status` et `stop` restent fiables et sûrs ;
- les tests backend, frontend et Microsoft Edge Stable passent ;
- aucune fonctionnalité de l'étape suivante n'a été ajoutée ;
- aucune fonctionnalité supplémentaire n'a été ajoutée.

Une fois ces critères atteints : arrête-toi.
