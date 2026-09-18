# Projet Léa

Léa est une plateforme personnelle d'intelligence artificielle locale.

## Objectif actuel

Construire une base locale minimale et stable : interface React, backend
FastAPI, base SQLite et modèle local restent limités à cette machine.

L’étape 9 ajoute une mémoire générale explicite aux conversations persistantes.
L’étape 10 ajoute un profil Programmation local, ses projets confinés et des
runs agentiques contrôlés. Le backend reste l’unique autorité de l’historique,
des souvenirs, des profils et des runs ; SQLite conserve les données locales et
l’interface permet de reprendre, rechercher et gérer les conversations.

## Philosophie

Une seule petite étape à la fois.

On ne commence jamais une nouvelle fonctionnalité tant que l'étape actuelle n'est pas stable, testée et validée.

## Technologies utilisées

- React + TypeScript + Vite
- Python + FastAPI
- llama.cpp avec le modèle local Qwen
- SQLite

## Technologies prévues plus tard

- Qdrant
- Tauri

## Ordre de développement

1. Interface localhost minimale — terminée.
2. Backend minimal — terminée.
3. Connexion frontend/backend avec réponse fictive — terminée.
4. Installation et test du premier modèle local — terminée.
5. Connexion du modèle au backend — terminée.
6. Démarrage et arrêt local — terminée.
7. Raisonnement, contrôle local et contexte temporaire — terminée.
8. Conversations locales persistantes et fiables — terminée.
9. Mémoire générale explicite et persistante — terminée.
10. Multi-modèles et profil Programmation — terminée.

## Démarrage local

Depuis la racine du projet, utilise une seule commande pour gérer les trois composants locaux :

```powershell
.\lea.ps1 start
.\lea.ps1 status
.\lea.ps1 stop
```

Après `start`, ouvre l’interface à l’adresse `http://127.0.0.1:5173`. La commande normale pour arrêter Léa est `stop`.

## Contrôle quotidien du cœur

Pour laisser l’interface ouverte sans charger le modèle ni FastAPI, démarre seulement Vite :

```powershell
npm run dev
```

Ouvre ensuite `http://127.0.0.1:5173` et utilise les boutons `Démarrer Léa` et `Arrêter Léa`. Le contrôleur local limité de Vite lance ou arrête uniquement le modèle et FastAPI ; il n’accepte aucune commande du navigateur.

Les mêmes opérations sont disponibles en ligne de commande :

```powershell
.\lea.ps1 start-core
.\lea.ps1 status-core
.\lea.ps1 stop-core
```

Les commandes existantes `start`, `status` et `stop` continuent de gérer la pile complète, y compris Vite lorsqu’il a été lancé par Léa.

## Conversations persistantes

Les conversations sont enregistrées dans `data/lea.sqlite3`. Elles survivent
à l’actualisation de la page, à l’arrêt du cœur et au redémarrage de Léa. Une
nouvelle conversation vide n’est créée qu’au premier message valide.

L’interface permet de lister, rechercher, ouvrir, renommer et supprimer une
conversation. Elle permet aussi de réessayer une génération échouée, modifier
un ancien message utilisateur ou régénérer une réponse ; ces deux dernières
opérations suppriment volontairement la suite devenue incohérente. Les
révisions empêchent un onglet périmé d’écraser silencieusement un autre onglet.

Le navigateur ne transmet jamais l’historique, un rôle `system` ou
`/no_think`. Le backend relit uniquement les messages validés dans SQLite,
sélectionne les paires complètes les plus récentes et construit lui-même la
requête du modèle. Aucun échange n’est stocké dans `localStorage`,
`sessionStorage` ou `IndexedDB`.

## Mémoire générale explicite

La mémoire générale est distincte de l’historique envoyé au modèle, mais chaque
souvenir garde la trace de sa ou de ses conversations sources. Elle est ajoutée
uniquement quand un message commence par une commande reconnue :

```text
Retiens que ...
Souviens-toi que ...
Souviens toi que ...
Mémorise que ...
Memorise que ...
Oublie que ...
```

`Retiens`, `Souviens-toi` et `Mémorise` enregistrent le fait dans la table
SQLite `memories`, sans appeler le modèle. La table `memory_sources` relie ce
fait aux conversations encore présentes où il a été explicitement retenu ;
cette provenance reste informative et ne limite pas sa durée de vie. `Oublie` supprime
uniquement une correspondance normalisée exacte : aucun rapprochement flou ou
sémantique n’est effectué. Un doublon exact ne crée pas une seconde ligne de
mémoire, mais ajoute sa conversation comme source si elle est différente.

Les commandes et leurs confirmations restent visibles dans leur conversation,
mais ne sont jamais renvoyées au modèle comme historique normal. Supprimer une
conversation supprime ses messages et ses liens de provenance dans la même
transaction, sans supprimer les faits globaux. Les souvenirs actifs survivent
à la suppression de leur conversation d’origine, à l’actualisation, aux
nouvelles conversations et aux redémarrages. Seule une commande explicite
`Oublie que ...` supprime le fait correspondant dans toutes les conversations.

Une phrase ordinaire comme `Je m'appelle Stan.` n’est jamais mémorisée
automatiquement. Il n’existe ni panneau mémoire, ni extraction automatique, ni
RAG ou embeddings à cette étape. Pour oublier un fait, il faut employer
`Oublie que ...` avec le même fait après normalisation déterministe.

Le profil Général utilise une fenêtre `-c 8192` avec un seul slot. Le backend réserve
1 024 tokens pour la réponse finale et 512 pour les instructions et le
template, puis applique une borne conservatrice d’un octet UTF-8 par token.
La directive `/no_think` existe uniquement dans la copie interne envoyée au
modèle : ni elle, ni les balises de pensée, ni une pensée interne ne sont
renvoyées à l’interface ou enregistrées dans SQLite.

Les souvenirs sont sérialisés dans un bloc JSON échappé et présentés comme des
données utilisateur, jamais comme des directives système. Leur capacité dédiée
est de 1 800 tokens estimés avec la borne conservatrice actuelle d’un octet
UTF-8 par token. Un ajout qui dépasserait cette capacité est refusé sans
supprimer ni tronquer les souvenirs existants ; la mémoire compte aussi dans le
budget global de 8 192 tokens du profil Général avant la sélection des paires d’historique.

Pour isoler une base lors d’un test :

```powershell
$env:LEA_DB_PATH = 'data/lea-test.sqlite3'
```

Toutes ces données résident dans `data/lea.sqlite3` : les conversations dans
`conversations`, leurs échanges dans `messages`, les faits actifs issus de
`Retiens que...` dans `memories` et leur provenance facultative dans
`memory_sources`. Une mémoire globale peut donc ne plus avoir de source après
la suppression de sa conversation d’origine.

## Profils et projets de programmation

Le registre `config/models.json` décrit les profils Général et Programmation,
leurs modèles, prompts, capacités, moteurs et limites : il est la source de
vérité de cette configuration. Général reste toujours le profil du prochain
démarrage complet. L'interface peut charger Programmation, revenir à Général et
poursuivre la même conversation ; chaque réponse assistant garde le profil et
l'alias du modèle qui l'a produite.

La configuration Programmation validée est strictement locale :

- `Qwen2.5-Coder-7B-Instruct Q6_K` ;
- fenêtre de contexte de 22 000 tokens et un seul slot ;
- `llama.cpp` b10516 (`b95502ba9`) ;
- OpenHands SDK / Agent Server 1.43.1 minimal comme moteur agentique.

Agent Canvas peut rester un outil administratif, mais il n’est pas requis pour
un run. Docker Desktop doit actuellement être démarré manuellement : Léa ne le
démarre pas elle-même et signale clairement son indisponibilité. Aucun modèle
cloud ni modèle local de secours n’est utilisé pour le profil Programmation.

En profil Programmation, la liste des projets provient uniquement des
sous-dossiers réels de `L:\IA_WORKSPACE`. Le registre SQLite conserve un UUID,
un nom, un chemin relatif et l'unique sélection active ; aucun chemin absolu
n'est exposé au navigateur. L'actualisation refuse les remontées, autres
lecteurs, chemins UNC, liens symboliques, junctions et reparse points.

Chaque run OpenHands fige de manière immuable son `project_id` et son chemin
canonique au démarrage. Un changement de projet dans une autre session ne peut
donc pas modifier son montage ni sa cible. Le run crée un checkpoint avant les
modifications ; l’interface permet de consulter les changements, de les
accepter ou de restaurer intégralement l’état initial. Une modification externe
détectée avant un rollback est signalée comme conflit et n’est jamais écrasée
silencieusement.

SQLite conserve un résumé compact des runs, de leur checkpoint et de leur état
(y compris acceptation ou rollback), sans dupliquer tout l’historique interne
d’OpenHands. Les détails agentiques restent dans l’état OpenHands prévu à cet
effet. La politique d’outils refuse les chemins `file_editor` hors du projet et
les sorties terminal explicites de `/workspace`; l’identité, la commande, le
port loopback et les limites du conteneur sont revérifiés avant réutilisation.
Exécuter le code d'un projet reste plus risqué que le lire : Léa fournit
une exécution locale contrôlée avec Docker, pas une garantie mathématique
d'isolation du noyau Windows. Le durcissement réseau Docker avancé est reporté
à l’étape 11. Ne sélectionne pour exécution que des projets dont tu acceptes le
code.

Limitation connue du modèle actuel :

> Qwen2.5-Coder-7B peut échouer sur des tâches agentiques multi-fichiers longues lorsque file_editor exige des remplacements textuels exacts. Léa détecte ces boucles, refuse les mutations invalides, valide les changements par des tests et peut restaurer le checkpoint.

`Lea_FinalValidation_Test` reste un benchmark difficile conservé pour comparer
un futur GLM-5.3-Flash avec Qwen ; sa réussite complète avec Qwen n'est pas un
critère de validation de cette étape.

## Roadmap

Les étapes suivantes ne sont pas implémentées dans cette version :

- Étape 11 — améliorations avancées du profil Programmation.
- Étape 12 — voix partagée.

Le reste demeure reporté : refonte visuelle complète, mémoire automatique ou
sémantique, Santé animale, Vision, Web, RAG et voix.

## Stockage actuel

Projet :
`L:\Projet_Lea`

Workspace des projets de programmation :
`L:\IA_WORKSPACE`

Jeux :
`L:\SteamLibrary`

Le dossier SteamLibrary est totalement indépendant du Projet Léa.
