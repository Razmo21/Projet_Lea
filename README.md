# Projet Léa

Léa est une plateforme personnelle d'intelligence artificielle locale.

## Objectif actuel

Construire une base locale minimale et stable : interface React, backend
FastAPI, base SQLite et modèle local restent limités à cette machine.

L’étape 8 ajoute des conversations persistantes fiables. Le backend est
l’unique autorité de l’historique, SQLite conserve les échanges localement et
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

Le modèle utilise une fenêtre `-c 8192` avec un seul slot. Le backend réserve
1 024 tokens pour la réponse finale et 512 pour les instructions et le
template, puis applique une borne conservatrice d’un octet UTF-8 par token.
La directive `/no_think` existe uniquement dans la copie interne envoyée au
modèle : ni elle, ni les balises de pensée, ni une pensée interne ne sont
renvoyées à l’interface ou enregistrées dans SQLite.

Pour isoler une base lors d’un test :

```powershell
$env:LEA_DB_PATH = 'data/lea-test.sqlite3'
```

Tout le reste est reporté : refonte visuelle complète, mémoire sémantique,
Développement, Santé animale, Vision, Web, RAG, voix, accès aux fichiers et
automatisation.

## Stockage actuel

Projet :
`L:\Projet_Lea`

Workspace futur :
`L:\IA_WORKSPACE`

Jeux :
`L:\SteamLibrary`

Le dossier SteamLibrary est totalement indépendant du Projet Léa.
