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

À la fin de chaque grande étape, avant la validation manuelle :
1. Relis l'ensemble du code concerné et recherche les incohérences restantes.
2. Retire uniquement le code dont l'inutilité est démontrée.
3. Ajoute un commentaire ou une docstring naturel à chaque fonction, méthode ou callback significatif.
4. Aère la mise en forme sans modifier le comportement.
5. Relance les vérifications ciblées et les tests de non-régression complets.

## Étape actuelle

L’étape 10 — multi-modèles et profil Programmation — est techniquement complète.
Ses barrières automatisées et ses validations réelles sont terminées ; la
validation manuelle finale de l’utilisateur reste attendue.

Ne commence ni l’étape 11 ni l’étape 12 sans une nouvelle autorisation explicite
de l’utilisateur.

## Interdictions actuelles

Ne crée PAS :
- un nouveau backend FastAPI ;
- un nouveau serveur Python ;
- un nouveau modèle local ;
- une nouvelle installation de llama.cpp ;
- RAG ;
- accès Internet ;
- Tauri ;
- authentification ;
- télémétrie ;
- mémoire automatique ou sémantique ;
- une fonctionnalité reportée aux étapes 11 ou 12.

## Validation avant une étape suivante

La validation manuelle doit confirmer le flux utilisateur principal : démarrer
Docker manuellement, choisir Programmation, sélectionner un projet strictement
confiné à `L:\IA_WORKSPACE`, lancer un run OpenHands réel, consulter le diff,
puis accepter ou restaurer les changements sans régression du profil Général ni
de la mémoire.

Après cette validation, arrête-toi et attends une demande explicite avant toute
nouvelle étape.
