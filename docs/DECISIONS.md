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
WAL, clés étrangères, contraintes et index. À l’étape 8, les tables de
migration, de conversations et de messages sont créées. Le backend relit les
messages validés dans SQLite et construit lui-même le contexte du modèle.

## D-013 — Mutations destructives et concurrence explicite
Modifier un message utilisateur ou régénérer une réponse supprime la suite de
conversation devenue incohérente ; aucune branche implicite n’est conservée.
Chaque mutation exige la révision attendue, et une seule génération peut être
active par conversation. Les appels au modèle sont exécutés hors transaction
SQLite longue. Une génération interrompue est récupérée comme échec sûr au
prochain démarrage.

## D-014 — Mémoire générale explicite et indépendante
Le schéma v2 ajoute `memories`, sans clé étrangère vers une conversation, et
classe les messages en tours `conversation` ou `memory`. Seules les commandes
françaises explicites `Retiens que`, `Souviens-toi que`, `Mémorise que` et
`Oublie que` modifient cette mémoire. La normalisation est déterministe et
l’oubli exige une égalité exacte ; aucune extraction automatique, recherche
sémantique, mémoire implicite, RAG ou embeddings n’est utilisé.

Les commandes et confirmations mémoire restent visibles, mais sont exclues de
l’historique envoyé au modèle. Les souvenirs actifs sont injectés intégralement
comme valeurs JSON échappées dans le dernier message utilisateur et ne sont
jamais traités comme des directives système. Leur capacité dédiée est de 1 800
tokens estimés ; tout dépassement est refusé sans troncature ni suppression.
Les écritures mémoire, les messages de confirmation et la révision de la
conversation sont validés dans une même transaction courte, sans appel modèle.

Une mémoire générale est indépendante de la conversation où elle a été créée.
La suppression d’une conversation ne la retire pas ; seule une commande exacte
`Oublie que` le fait globalement.

## D-015 — Provenance et suppression définitive — remplacée par D-016
Cette décision décrivait le comportement transitoire suivant.

Le schéma v3 ajoute `memory_sources`, qui relie un souvenir unique à chacune des
conversations où il a été explicitement retenu. La suppression d’une
conversation retire ses messages et ses liens de provenance dans une seule
transaction. Si ce lien était la dernière source du fait, la ligne `memories`
est également supprimée ; si une autre conversation l’a retenu, elle reste.

La migration transitoire devait relier les souvenirs v2 aux commandes encore
présentes et purger les souvenirs déjà orphelins. `Oublie que` conserve son
égalité normalisée
exacte et supprime le fait ainsi que toutes ses provenances. Aucun effacement
flou, automatique ou sémantique n’est introduit.

## D-016 — Provenance informative, mémoire globale
`memory_sources` reste une provenance utile tant que les conversations sources
existent, mais ne représente plus la propriété ni la durée de vie d’un fait.
La cascade d’une conversation retire ses messages et ses liens, jamais la ligne
`memories`. Un souvenir sans source est valide, persiste entre conversations et
redémarrages, et reste injecté au modèle.

`Oublie que` est l’unique suppression d’un souvenir : l’égalité normalisée doit
être exacte, puis la suppression s’applique globalement et cascade ses liens de
provenance. Cette décision rétablit la sémantique indépendante de D-014 sans
ajouter de mémoire implicite ni de suppression sémantique.
