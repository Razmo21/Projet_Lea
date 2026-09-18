# Changelog — Projet Léa

## [0.0.10] — Profil Programmation et runs OpenHands

### Ajouté
- Un contrat de fiabilité commun aux profils Général et Programmation, avec des
  règles explicites contre l’invention de fichiers, d’outils, de tests, de
  sources et de résultats.
- Un registre versionné unique pour les profils, prompts, capacités, moteurs et
  limites. Le profil Programmation validé utilise
  `Qwen2.5-Coder-7B-Instruct Q6_K`, une fenêtre de 22 000 tokens, un slot et
  `llama.cpp` b10516 (`b95502ba9`).
- L’intégration locale d’OpenHands SDK / Agent Server 1.43.1 minimal pour les
  runs Programmation ; Agent Canvas n’est pas une dépendance de fonctionnement.
- Le registre SQLite des projets sous `L:\IA_WORKSPACE`, les runs agentiques et
  leurs checkpoints. Seul le résumé utile du run est conservé dans SQLite ; le
  journal détaillé reste dans l’état OpenHands.
- La consultation des changements, leur acceptation et le rollback complet des
  fichiers créés, modifiés ou supprimés par un run.

### Sécurisé
- Un run fige immuablement son `project_id` et son chemin canonique : une autre
  sélection de projet ne peut pas rediriger un run en cours.
- La racine autorisée est exactement `L:\IA_WORKSPACE` ; remontées, chemins
  absolus extérieurs, autres lecteurs, UNC, liens et reparse points sont refusés.
- Les changements externes détectés avant un rollback deviennent un conflit au
  lieu d’être écrasés silencieusement. L’annulation attend l’arrêt effectif du
  run avant d’être annoncée comme terminée.
- Aucun modèle cloud ni modèle local de secours n’est utilisé. Docker Desktop
  reste un prérequis manuel ; Léa ne le démarre pas automatiquement.
- Mise à niveau vers FastAPI 0.141.1 et Starlette 1.6.0 afin de retirer les avis
  de sécurité associés à l’ancienne Starlette 0.46.2.
- Les réponses locales ne sont plus mises en cache et refusent le framing, le
  MIME sniffing, le DNS rebinding et la transmission d’un referrer vers un tiers.
- La politique OpenHands refuse désormais les cibles `file_editor` hors du
  projet ainsi que les sorties terminal explicites de `/workspace`.
- Avant de réutiliser un conteneur OpenHands, Léa vérifie aussi son utilisateur,
  sa commande, son port loopback, ses limites de ressources et sa politique de
  redémarrage. Les processus OpenHands utilisent la table de coûts LiteLLM
  embarquée sans requête distante implicite ; les exécutables Windows système
  sont lancés par leur chemin absolu plutôt que depuis le dossier courant.

### Nettoyé
- Suppression de l'ancienne boucle agentique maison, de son tool calling et de
  ses exécuteurs fichiers/terminal devenus sans appel depuis l'intégration
  OpenHands, ainsi que de leurs tests exclusivement historiques.
- Ajout de commentaires et docstrings naturels aux fonctions applicatives, puis
  aération du frontend et du lanceur sans changement de comportement.
- Retrait de deux imports Python et de règles CSS sans usage ou sans effet.

### Validé
- Commutation réelle Général ↔ Programmation, disponibilité Qwen/OpenHands et
  absence de dépendance à Agent Canvas pour le fonctionnement normal.
- Runs OpenHands réels sur projets Python et React/TypeScript : lecture,
  outils, correction, retest vert, rapport final, checkpoint puis rollback.
- Persistance des conversations, souvenirs, runs et checkpoints après le
  redémarrage du backend, avec les garanties de l’étape 9 conservées.
- Tests de confinement, annulation, conflit externe, prompt injection et
  non-régressions backend, frontend et build.

### Limitation connue
- Qwen2.5-Coder-7B peut échouer sur des tâches agentiques multi-fichiers longues lorsque file_editor exige des remplacements textuels exacts. Léa détecte ces boucles, refuse les mutations invalides, valide les changements par des tests et peut restaurer le checkpoint.
- `Lea_FinalValidation_Test` reste un benchmark difficile destiné à la future
  comparaison de GLM-5.3-Flash avec Qwen ; il n'est plus une barrière de
  clôture de l'étape 10.

## [0.0.9.2] — Mémoire globale et reprise de saisie

### Corrigé
- Les souvenirs explicites restent globaux après la suppression de leur
  conversation d’origine ; seule une commande exacte `Oublie que` les retire.
- La provenance SQLite devient informative et accepte un souvenir sans source.
- Après la suppression d’une conversation, le focus revient automatiquement
  dans la zone de question afin que la saisie clavier reste immédiate.

### Validé
- Suppression de la dernière conversation, saisie Edge réelle, persistance au
  redémarrage et oubli global depuis une autre conversation.

## [0.0.9.1] — Provenance et suppression définitive — remplacée en 0.0.9.2

### Corrigé
- Ajout de la migration SQLite v3 et de `memory_sources` pour rattacher chaque
  souvenir explicite à sa ou ses conversations sources.
- Suppression atomique du souvenir quand sa dernière conversation source est
  supprimée depuis l’interface ; un fait ayant une autre source est conservé.
- Migration des sources v2 encore vérifiables et purge des souvenirs déjà
  orphelins qui continuaient auparavant à être injectés au modèle.

### Validé
- Suppression, redémarrage, oubli exact, doublons multi-conversations,
  transactions, concurrence, modèle réel et Microsoft Edge Stable.

## [0.0.9] — Mémoire générale explicite

### Ajouté
- Migration SQLite v2 avec table indépendante `memories`, clé normalisée unique
  et classification des tours de conversation ou de gestion mémoire.
- Commandes françaises explicites de mémorisation et d’oubli, confirmations
  déterministes et conservation de la mémoire après suppression de la source
  (ancien comportement, remplacé par la correction 0.0.9.1).
- Injection de tous les souvenirs actifs comme données JSON échappées, avec une
  capacité dédiée de 1 800 tokens estimés et sans troncature silencieuse.
- Tests du parser, des transactions, de la concurrence, de la capacité, du
  payload modèle, du modèle réel et de Microsoft Edge Stable.

### Sécurisé
- Mémorisation et oubli atomiques, sans appel au modèle et avec révision
  obligatoire pour une conversation existante.
- Oubli limité à l’égalité normalisée exacte, sans fuzzy matching ni suppression
  sémantique.
- Tours mémoire visibles et copiables, mais exclus du contexte modèle et non
  modifiables ou régénérables comme des tours normaux.
- Prévalidation mémoire + contexte avant une modification ou régénération
  destructive, afin de conserver l’ancienne réponse en cas de dépassement.

### Validé
- Mémoire disponible entre conversations et après redémarrage du cœur ; la
  conservation après suppression de la source décrite dans cette version est
  remplacée par la provenance de 0.0.9.1.
- Migration v1 vers v2 sans perte, WAL, intégrité et clés étrangères valides.
- Non-régression des conversations de l’étape 8, de la fenêtre 8 192, des
  protections PID/ports et de la libération de la VRAM.

## [0.0.8] — Conversations locales persistantes

### Ajouté
- Base SQLite locale avec migrations transactionnelles, WAL, clés étrangères,
  contraintes, index et chemin de test `LEA_DB_PATH`.
- API de conversations avec liste, recherche, lecture, renommage, suppression,
  réessai, modification destructive et régénération destructive.
- Interface persistante avec restauration par URL, gestion des échecs et
  protection des conflits entre onglets.
- Tests backend, frontend et scénario réel Microsoft Edge Stable.

### Modifié
- Fenêtre du modèle portée à 8 192 tokens avec un seul slot.
- Suppression des options de raisonnement ; `/no_think` est ajouté uniquement
  à la requête interne et les marqueurs de pensée sont filtrés défensivement.
- Le backend devient l’unique autorité de l’historique envoyé au modèle.

### Validé
- Persistance après actualisation et redémarrage du cœur.
- Reprise sûre après interruption, révisions concurrentes et cascades SQLite.
- Deux cycles complets de démarrage et d’arrêt, avec libération des ports et de
  la VRAM.

## [0.0.1] — Préparation

### Ajouté
- Dépôt Git créé.
- SSD préparé.
- Dossier `Projet_Lea` créé.
- Dossier `IA_WORKSPACE` créé.
- Stratégie de développement incrémentale définie.
- Instructions initiales pour Codex préparées.

### État
Aucun code applicatif n'a encore été développé.
