# Projet Léa

Léa est une plateforme personnelle d'intelligence artificielle locale.

## Objectif actuel

Construire une base locale minimale et stable : interface React, backend FastAPI et modèle local restent limités à cette machine.

L’étape 7 ajoute un raisonnement équilibré, le contrôle local du cœur depuis
l’interface et un contexte de conversation strictement temporaire, sans
mémoire persistante.

## Philosophie

Une seule petite étape à la fois.

On ne commence jamais une nouvelle fonctionnalité tant que l'étape actuelle n'est pas stable, testée et validée.

## Technologies utilisées

- React + TypeScript + Vite
- Python + FastAPI
- llama.cpp avec le modèle local Qwen

## Technologies prévues plus tard

- SQLite
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

## Contexte temporaire de conversation

Les messages affichés sont conservés uniquement dans l’état React de la page
ouverte. À chaque question, le navigateur renvoie au backend les paires
complètes `user` / `assistant` déjà réussies. Le backend ne conserve aucun
historique : recharger ou fermer la page efface naturellement le contexte.
Le bouton `Nouvelle conversation` l’efface immédiatement dans l’interface.

Il n’y a ni fichier de conversation, ni `localStorage`, ni `IndexedDB`, ni
base de données. Une erreur technique et le raisonnement interne du modèle ne
sont jamais ajoutés à l’historique.

Le modèle utilise une fenêtre `-c 4096`. Le backend réserve 1 024 tokens pour
la réponse finale, 512 pour le raisonnement et 512 pour les instructions et le
template. Pour les 2 048 tokens restants, il emploie une borne haute prudente
d’un octet UTF-8 par token avec un coût fixe par message, conserve toujours la
question actuelle et retire d’abord les paires les plus anciennes.

Tout le reste est reporté : historique persistant, mémoire, Développement,
Santé animale, Vision, Web, RAG, voix, accès aux fichiers, automatisation.

## Stockage actuel

Projet :
`L:\Projet_Lea`

Workspace futur :
`L:\IA_WORKSPACE`

Jeux :
`L:\SteamLibrary`

Le dossier SteamLibrary est totalement indépendant du Projet Léa.
