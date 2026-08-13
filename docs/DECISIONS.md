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

## D-008 — Raisonnement local équilibré
Le modèle général local utilise le raisonnement avec un budget de 512 tokens.
Le backend retire les balises de pensée interne et ne renvoie que la réponse
finale à l’interface.

## D-009 — Contrôle local du cœur
Vite héberge uniquement en développement un contrôleur local à routes fixes.
Il peut appeler `start-core`, `status-core` et `stop-core` de `lea.ps1`, sans
transmettre de commande ou d’argument arbitraire du navigateur. Le cœur
conserve les protections d’identité des processus ; le frontend reste ouvert
pendant son arrêt.

## D-010 — Contexte de conversation temporaire
L’historique de conversation vit uniquement dans l’état React de la page. Le
client transmet des paires `user` / `assistant` complètes au backend, qui les
valide et réduit les paires les plus anciennes avec un budget conservateur.
Ni le backend ni le navigateur ne créent de stockage persistant.
