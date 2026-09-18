# TODO — Projet Léa

## Étapes terminées

- [x] Étape 1 — Interface localhost minimale.
- [x] Étape 2 — Backend FastAPI minimal.
- [x] Étape 3 — Connexion frontend / backend avec réponse fictive.
- [x] Étape 4 — Installation et test du premier modèle local.
- [x] Étape 5 — Première vraie réponse de Léa : frontend React, FastAPI et modèle local reliés et validés.

## ÉTAPE 6 — Démarrage et arrêt local — terminée

- [x] Créer une commande locale unique pour démarrer Léa.
- [x] Suivre uniquement les processus lancés par Léa.
- [x] Vérifier l’état des trois composants.
- [x] Arrêter proprement les processus et nettoyer l’état temporaire.
- [x] Vérifier deux cycles complets de démarrage et d’arrêt.

## ÉTAPE 7 — Raisonnement, contrôle local et contexte temporaire — terminée

- [x] Utiliser le raisonnement équilibré et ne jamais afficher la pensée interne.
- [x] Permettre le démarrage et l’arrêt local du cœur depuis l’interface.
- [x] Ajouter un contexte de conversation temporaire en mémoire vive seulement.
- [x] Réduire l’historique par paires complètes dans la fenêtre de contexte.

## ÉTAPE 8 — Conversations locales persistantes et fiables — terminée

- [x] Désactiver le raisonnement visible avec une directive interne jamais persistée.
- [x] Utiliser une fenêtre de contexte de 8 192 tokens et un seul slot modèle.
- [x] Ajouter SQLite avec migrations, WAL, clés étrangères et contraintes.
- [x] Faire du backend l’unique autorité de l’historique du modèle.
- [x] Persister, lister, rechercher, ouvrir, renommer et supprimer les conversations.
- [x] Gérer les échecs, interruptions et réessais sans faux message assistant.
- [x] Modifier et régénérer de façon destructive, sans branche implicite.
- [x] Protéger les écritures par révision et sérialiser les générations d’une conversation.
- [x] Valider les migrations, l’API, le contexte, l’interface et Microsoft Edge Stable.
- [x] Vérifier directement l’intégrité et le contenu de la base SQLite.

## ÉTAPE 9 — Mémoire générale explicite — terminée

- [x] Ajouter les migrations SQLite pour `memories` et sa provenance
  informative `memory_sources`.
- [x] Reconnaître les commandes explicites de mémorisation et d’oubli.
- [x] Normaliser les faits sans rapprochement sémantique et éviter les doublons.
- [x] Mémoriser ou oublier atomiquement sans appeler le modèle.
- [x] Injecter tous les souvenirs actifs comme données JSON dans le budget 8 192.
- [x] Exclure les tours de gestion mémoire du contexte tout en les conservant visibles.
- [x] Préserver les souvenirs globaux lors de la suppression d’une conversation
  et les supprimer uniquement par une commande explicite `Oublie que`.
- [x] Valider migrations, concurrence, capacité, modèle réel et Microsoft Edge Stable.

## ÉTAPE 10 — Multi-modèles et profil Programmation — terminée

Configuration Programmation validée : `Qwen2.5-Coder-7B-Instruct Q6_K`,
22 000 tokens, un slot, `llama.cpp` b10516 (`b95502ba9`) et OpenHands SDK /
Agent Server 1.43.1 minimal, sans Agent Canvas pendant les runs. Docker Desktop
reste un prérequis démarré manuellement.

- [x] 10A — Contrat global de fiabilité et anti-hallucination commun aux profils.
- [x] 10B — Registre modèles/profils unique et cohérent.
- [x] 10C — Profil Programmation local et disponibilité OpenHands vérifiable.
- [x] 10D — Commutation sûre Général ↔ Programmation avec rollback.
- [x] 10E — Sélecteur frontend des profils sans rechargement de conversation.
- [x] 10F — Projets confinés exactement à `L:\IA_WORKSPACE`.
- [x] 10G — Intégration agentique OpenHands : lecture, édition, terminal et annulation.
- [x] 10H — Checkpoints, consultation des changements, acceptation et rollback avec conflit.
- [x] 10I — Persistance SQLite compacte des runs, sessions et checkpoints.
- [x] 10J — Validation finale, sécurité minimale et non-régressions.

## Plus tard

Étape 11 — améliorations avancées du profil Programmation ; étape 12 — voix
partagée. Restent également reportés : refonte visuelle complète, mémoire
automatique ou sémantique, Santé animale, Vision, Web, RAG et autres fonctions.
