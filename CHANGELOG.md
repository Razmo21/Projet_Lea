# Changelog — Projet Léa

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
