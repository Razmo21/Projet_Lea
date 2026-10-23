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

## ÉTAPE 11 — Architecture indépendante des modèles — terminée

- [x] 11A — Auditer les dépendances aux modèles, moteurs et lanceurs existants.
- [x] 11B — Centraliser le registre validé et supprimer les parseurs concurrents.
- [x] 11C — Séparer les modèles des contrats, permissions et budgets des profils.
- [x] 11D — Isoler le protocole et les arguments llama.cpp dans un adaptateur simple.
- [x] 11E — Conserver le cycle de vie sûr et adapter les consommateurs OpenHands.
- [x] 11F — Valider résolution, erreurs, sécurité, non-régressions et vrais modèles.
- [x] 11G — Relire, commenter, nettoyer les doublons prouvés et documenter.
- [x] Validation manuelle confirmée par l’utilisateur dans l’autorisation de l’étape 12.

Preuves réelles : Général, historique, mémoire explicite après redémarrage,
commutation, deux petits runs OpenHands validés, rollback exact et Accept.
Substitution/partage de modèle validés en configuration de test, sans nouveau
GGUF. Aucun benchmark difficile relancé, aucun mécanisme de récupération ajouté.

## ÉTAPE 12 — Centre de paramètres de Léa — terminée

- [x] 12A — Audit du cycle de vie et de la persistance existants.
- [x] 12B — Préférences SQLite indépendantes, migration additive et contrôle local hors IA.
- [x] 12C — Page dédiée, navigation préservée, validation explicite et erreurs visibles.
- [x] 12D — Général Low par défaut / High, directives réellement testées et filtrage privé.
- [x] 12E — Audit Programmation : aucun contrôle fictif ; comportement OpenHands conservé.
- [x] 12F — Conflits, corruptions, indisponibilité et sauvegardes pendant génération/run.
- [x] 12G — Extension localisée démontrée par une colonne de test, sans réglage futur livré.
- [x] 12H — Edge, vrais modèles, run OpenHands validé, rollback et persistance après reprise.
- [x] 12I — Relecture, commentaires, documentation et ménage ciblé.
- [x] 12J — Non-régression complète et clôture technique sans commit/push.
- [x] Validation manuelle confirmée par l’utilisateur dans l’autorisation de l’étape 13.

Programmation : aucun mécanisme Low/High suffisamment fiable n’a été établi
avec Qwen2.5-Coder. Pas de faux High par défaut ni de réduction des protections.
Le choix d’une éventuelle stratégie agentique distincte est reporté, sans bloquer
le centre de paramètres.

## ÉTAPE 13 — Programmation avancée — terminée

- [x] 13A — Audit KEEP / IMPROVE / ADD / REMOVE et périmètre confirmé.
- [x] 13B — Timeout parent, identité du résultat, erreurs publiques sûres, arrêt confirmé.
- [x] 13C — Reprise fail-closed, slot bloqué si incertain, panne réelle puis Rollback exact.
- [x] 13D — Surveillance native RAM/CPU, NVIDIA et disponibilité locale, coût mesuré.
- [x] 13E — Hystérésis, alertes indépendantes, diagramme facultatif, préférence SQLite 9.
- [x] Complément 13D/E — Surveillance commune à tous les profils actifs, sondes
  Docker réservées à OpenHands ; encadré « Votre question » réutilisant le style existant.
- [x] 13F — Choix utilisateur appliqué : applications manuelles, conteneur au seul lancement du run.
- [x] 13G — Barrière examinée ; report de l’automatisation Edge approuvé, aucune capacité livrée.
- [x] 13H — Audit : propriétaires existants suffisants, aucun pont Windows arbitraire.
- [x] 13I — Suppression du seul conteneur arrêté/validé vérifié, sans volume ni prune.
- [x] 13J — Général, mémoire, historique, OpenHands, Accept, panne/Rollback et UI réels.
- [x] 13K — Relecture, commentaires, nettoyage ciblé et documentation.
- [x] 13L — Suites complètes, clôture technique, aucun commit/push.
- [x] Validation manuelle et finalisation confirmées par le prompt de l’étape 14.

Preuves et limites : `docs/ETAPE_13_VALIDATION.md`. Qwen et les politiques
d’outils restent inchangés. Edge agentique non livré ; Docker Desktop manuel.
La demande explicite de l’étape 14 autorise uniquement le périmètre vocal ci-dessous.

## ÉTAPE 14 — Microphone et conversation vocale — terminée

Le prompt 14 remplace le périmètre initial « Entrées multimodales » par la voix
seule, sans renuméroter la suite. Accord de téléchargement obtenu (10 Go maximum),
installation CPU isolée effectuée. Décisions D-030 à D-032 et preuves détaillées :
`docs/ETAPE_14_VALIDATION.md`. Les essais synthétiques restent distingués de la
validation physique finalement confirmée par l’utilisateur.

- [x] 14A — Whisper Small Q5_1/Piper SIWIS CPU, accord et mesures.
- [x] 14B — Capture explicite, bornée, annulable et nettoyée ; périphérique synthétique testé.
- [x] 14C — Dictée dans le brouillon, sans écrasement/envoi, également cœur arrêté.
- [x] 14D — Interface vocale dédiée sans contenu textuel des échanges.
- [x] 14E — Échanges deux clics, sériels, sans écoute automatique ; Général et retour d’échec Programmation testés.
- [x] 14F — TTS français local, lecture navigateur, interruption et écoute physique validées.
- [x] 14G — Historique existant, aucun doublon ni conservation audio automatique.
- [x] 14H — Retour vocal réel failed/Rollback ; run écrit validated/Accept ; règles inchangées.
- [x] 14I — Préférences réelles validées, volume/High persistés après arrêt complet.
- [x] 14J — Mesures moteurs RAM/VRAM/CPU/latence avec les deux profils, limites documentées.
- [x] 14K — Suites et essais intégrés documentés, échecs Qwen distingués des tests réussis.
- [x] Diagnostic du décodage : Opus refusé dans VS Code intégré, comparaison identique réussie dans Edge ; message explicite et tests de finalisation partagés.
- [x] Pocket TTS `french` intégré comme « Léa — Voix naturelle française » par défaut ; Piper/SIWIS conservé et sélection persistante migrée.
- [x] 14L — Bilan, nettoyage et validation physique/manuelle utilisateur terminés ; banc d’essai externe supprimé après contrôle.
- [x] Maintenance finale — workspace vidé par l’utilisateur puis vérifié vide,
  mémoire de test supprimée après sauvegarde, SQLite compacté et suppression
  des conversations durcie par `secure_delete`.
- [x] Audit final — 151 fichiers inventoriés, deux imports inutiles retirés,
  suites complètes et cycle local réel isolé réussis sans commencer l’étape 15.

## ÉTAPE 15 — Vétérinaire et optimisation des contrats — validation manuelle requise

- [x] Modèle local `Qwen3.5-9B-Q4_K_M`, empreinte et compatibilité llama.cpp vérifiés.
- [x] Troisième profil direct sans Web, vision, outil ni accès workspace.
- [x] Contexte 16 384, un slot, ressources mesurées et commutations sûres entre les trois profils.
- [x] Low/High Vétérinaire natif, indépendant de Général ; migration SQLite 12 et paramètres persistants.
- [x] Conversations, suppression, historique, mémoire explicite, surveillance et voix réutilisés.
- [x] Scénarios vétérinaires comparés avec corrigé indépendant et erreurs scientifiques documentées.
- [x] Contrat commun audité puis conservé intact après échec des tests de sécurité ; Général, mémoire et Vétérinaire clarifiés.
- [x] Tentative de raccourcissement Programmation annulée après régression réelle `file_editor`.
- [x] Runs OpenHands isolés : succès de référence, échecs détectés et rollbacks exacts, aucune heuristique Qwen ajoutée.
- [x] Rapport technique : `docs/ETAPE_15_VALIDATION.md`.
- [ ] Validation manuelle dans Microsoft Edge autonome.

## Roadmap validée — après la validation manuelle de l’étape 15

- Étape 16 — Accès Web.
- Étape 17 — Génération d’images.
- Étape 19 — Speech-to-Speech.
- Étape 20 — Refonte visuelle.
- Étape 21 — Mémoire avancée.
- Étape 22 — Fine-tuning optionnel.
- Étape 23 — Sécurité finale.
- Étape 24 — Tests finaux.
- Étape 25 — Logiciel desktop final.

La vision en entrée est suspendue et reportée. Le profil Auxiliaire est supprimé
définitivement. Aucune de ces étapes suivantes n'est commencée.
