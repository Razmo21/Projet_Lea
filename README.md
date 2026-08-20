# Projet Léa

Léa est une plateforme personnelle d'intelligence artificielle locale.

## Objectif actuel

Construire une base locale minimale et stable : interface React, backend
FastAPI, base SQLite et modèle local restent limités à cette machine.

L’étape 9 ajoute une mémoire générale explicite aux conversations persistantes.
Le backend reste l’unique autorité de l’historique et des souvenirs, SQLite
conserve les données localement et l’interface permet de reprendre, rechercher
et gérer les conversations.

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
10. Multi-modèles et profil Programmation — planifiée, non commencée.

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

Le modèle utilise une fenêtre `-c 8192` avec un seul slot. Le backend réserve
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
budget global de 8 192 tokens avant la sélection des paires d’historique.

Pour isoler une base lors d’un test :

```powershell
$env:LEA_DB_PATH = 'data/lea-test.sqlite3'
```

Toutes ces données résident dans `data/lea.sqlite3` : les conversations dans
`conversations`, leurs échanges dans `messages`, les faits actifs issus de
`Retiens que...` dans `memories` et leur provenance facultative dans
`memory_sources`. Une mémoire globale peut donc ne plus avoir de source après
la suppression de sa conversation d’origine.

Tout le reste est reporté : refonte visuelle complète, mémoire automatique ou
sémantique, Santé animale, Vision, Web, RAG, voix, accès aux fichiers et
automatisation. L’étape 10 planifiera seulement le multi-modèles et un profil
Programmation ; elle n’est pas commencée.

## Stockage actuel

Projet :
`L:\Projet_Lea`

Workspace futur :
`L:\IA_WORKSPACE`

Jeux :
`L:\SteamLibrary`

Le dossier SteamLibrary est totalement indépendant du Projet Léa.
