# Changelog — Projet Léa

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
