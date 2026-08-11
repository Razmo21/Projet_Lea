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

Étape 5 — connecter le frontend React, FastAPI et le modèle local déjà installé afin d’afficher une première vraie réponse de Léa.

## Interdictions actuelles

Ne crée PAS :
- backend FastAPI ;
- serveur Python ;
- modèle local ;
- llama.cpp ;
- mémoire ;
- base de données ;
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
- `npm install` fonctionne ;
- `npm run dev` démarre sans erreur ;
- localhost est accessible ;
- le titre « Léa » est visible ;
- l'utilisateur peut écrire une question ;
- le bouton Envoyer fonctionne ;
- la réponse fictive apparaît ;
- aucune fonctionnalité supplémentaire n'a été ajoutée.

Une fois ces critères atteints : arrête-toi.
