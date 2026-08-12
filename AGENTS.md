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

Étape 6 — simplifier et fiabiliser le démarrage, l’état et l’arrêt local de Léa.

## Interdictions actuelles

Ne crée PAS :
- un nouveau backend FastAPI ;
- un nouveau serveur Python ;
- un nouveau modèle local ;
- une nouvelle installation de llama.cpp ;
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
- `.\lea.ps1 start` démarre le modèle, FastAPI puis Vite sans erreur ;
- `.\lea.ps1 status` reflète correctement leur état ;
- l'interface locale répond et affiche une vraie réponse de Léa ;
- `.\lea.ps1 stop` arrête uniquement les processus gérés et libère les ports ;
- aucune fonctionnalité de l'étape suivante n'a été ajoutée ;
- aucune fonctionnalité supplémentaire n'a été ajoutée.

Une fois ces critères atteints : arrête-toi.
