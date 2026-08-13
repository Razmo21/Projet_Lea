# Décisions validées — Projet Léa

## D-001 — Développement incrémental
Une seule petite étape à la fois.

## D-002 — Première étape
Créer uniquement une interface locale dans le navigateur.

## D-003 — Frontend
React + TypeScript + Vite.

## D-004 — Séparation Léa / modèles
Léa est la plateforme ; les modèles seront interchangeables.

## D-005 — Stockage
Projet : `L:\Projet_Lea`
Workspace futur : `L:\IA_WORKSPACE`
Jeux : `L:\SteamLibrary`

## D-006 — Accès aux fichiers
Aucun accès aux fichiers personnels dans la première version.

## D-007 — Fonctionnalités futures
Mémoire, Développement, Santé animale, Vision, Web, RAG, voix et automatisation sont reportés.

## D-008 — Raisonnement local équilibré — remplacée
Cette décision de l’étape 7 est remplacée par D-011. Le modèle général
n’utilise plus de budget de raisonnement explicite.

## D-009 — Contrôle local du cœur
Vite héberge uniquement en développement un contrôleur local à routes fixes.
Il peut appeler `start-core`, `status-core` et `stop-core` de `lea.ps1`, sans
transmettre de commande ou d’argument arbitraire du navigateur. Le cœur
conserve les protections d’identité des processus ; le frontend reste ouvert
pendant son arrêt.

## D-010 — Contexte de conversation temporaire — remplacée
Cette décision de l’étape 7 est remplacée par D-012. Le navigateur ne transmet
plus l’historique et SQLite est désormais la source persistante officielle.

## D-011 — Modèle sans pensée persistée
Le modèle général utilise une fenêtre de 8 192 tokens et un seul slot. Le
backend ajoute `/no_think` uniquement dans une copie interne de la question
courante et retire défensivement les marqueurs de pensée, y compris leurs
variantes d’espacement, de casse et les blocs incomplets. Ces données internes
ne sont ni exposées ni enregistrées.

## D-012 — SQLite comme source des conversations
La base locale officielle est `data/lea.sqlite3`, remplaçable en test par
`LEA_DB_PATH`. Le schéma évolue par migrations transactionnelles et utilise
WAL, clés étrangères, contraintes et index. Seules les tables de migration,
de conversations et de messages sont créées. Le backend relit les messages
validés dans SQLite et construit lui-même le contexte du modèle.

## D-013 — Mutations destructives et concurrence explicite
Modifier un message utilisateur ou régénérer une réponse supprime la suite de
conversation devenue incohérente ; aucune branche implicite n’est conservée.
Chaque mutation exige la révision attendue, et une seule génération peut être
active par conversation. Les appels au modèle sont exécutés hors transaction
SQLite longue. Une génération interrompue est récupérée comme échec sûr au
prochain démarrage.
