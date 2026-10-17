# AGENTS.md — Instructions obligatoires pour Codex

Tu travailles sur le Projet Léa.

## Règle absolue

Travaille uniquement sur la tâche explicitement demandée.

N'anticipe jamais l'étape suivante.

N'ajoute jamais une fonctionnalité « utile pour plus tard » sans demande explicite.

## Priorités

1. Fonctionnement.
2. Simplicité.
3. Lisibilité.
4. Stabilité.
5. Tests.
6. Performance.
7. Fonctionnalités supplémentaires.

## Méthode de travail

Avant toute modification :
1. Lis `README.md`.
2. Lis `TODO.md`.
3. Lis `AGENTS.md`.
4. Identifie précisément la tâche.
5. Explique brièvement ce que tu vas faire.
6. Liste les fichiers et dépendances concernés.

Après modification :
1. Lance les vérifications adaptées.
2. Vérifie que le projet démarre.
3. Liste les fichiers créés ou modifiés.
4. Indique les commandes utilisées.
5. Signale clairement les erreurs restantes.
6. Arrête-toi et attends la validation de l'utilisateur.

À la fin de chaque grande étape, avant la validation manuelle :
1. Relis l'ensemble du code concerné et recherche les incohérences restantes.
2. Retire uniquement le code dont l'inutilité est démontrée.
3. Ajoute un commentaire ou une docstring naturel à chaque fonction, méthode ou callback significatif.
4. Aère la mise en forme sans modifier le comportement.
5. Relance les vérifications ciblées et les tests de non-régression complets.

## Étape actuelle

Les étapes 10, 11 et 12 sont validées. L’étape 13 — Programmation avancée —
est techniquement complète ; sa validation manuelle finale reste attendue.
Voir `docs/ETAPE_13_VALIDATION.md` pour les preuves et limites.

Ne commence pas l’étape 14 sans une nouvelle autorisation explicite de l’utilisateur.

## Interdictions actuelles

Ne crée PAS :
- un nouveau backend FastAPI ;
- un nouveau serveur Python ;
- un nouveau modèle local ;
- une nouvelle installation de llama.cpp ;
- RAG ;
- accès Internet ;
- Tauri ;
- authentification ;
- télémétrie ;
- mémoire automatique ou sémantique ;
- une fonctionnalité reportée ou appartenant aux étapes ultérieures.

`config/models.json` (schéma 3) est l’unique registre. Les profils portent leurs
contrats et permissions ; `models` porte les paramètres des modèles et
`profiles[].model_id` les associe. Ne réintroduis pas de dépendance au nom de
Qwen dans le code métier ni de parseur concurrent dans les lanceurs.

Les préférences fonctionnelles sont dans SQLite (`user_preferences`, migrations 8–9),
pas dans le registre. Le contrôleur Vite peut les lire/sauver sans FastAPI ni
modèle chargé, via le CLI ponctuel existant. Ne déclenche pas la récupération
des générations en ouvrant les paramètres. Général Low/High prend effet à la
requête suivante ; aucun contrôle de raisonnement fictif pour Programmation.

Docker Desktop et l’interface OpenHands restent ouverts manuellement. Le seul
lancement explicite d’un run crée son conteneur Agent Server : ni l’activation
du profil ni sa finalisation ne doivent créer de serveur idle. L’automatisation
Edge par l’agent est reportée : aucun accès Web ou pont Windows arbitraire.
La surveillance reste en lecture seule, en RAM, sans arrêt automatique sur seuil.
Elle est commune à tous les profils IA actifs et cesse avec le cœur ; seuls
les contrôles Docker/OpenHands dépendent des besoins agentiques du profil.
Le diagramme est masqué par défaut ; les alertes restent indépendantes du réglage.
Un arrêt Docker incertain reste non terminal et interdit une nouvelle activité
modèle jusqu’à récupération vérifiée. Ne compense pas les décisions de Qwen.

## Validation avant une étape suivante

La validation manuelle doit confirmer Paramètres (ouverture, Low/High, Valider,
erreurs lisibles, retour sans perte de brouillon), également avec l’IA arrêtée,
puis la préférence conservée après redémarrage. Elle doit aussi confirmer le
flux utilisateur principal : démarrer
Docker manuellement, choisir Programmation, sélectionner un projet strictement
confiné à `L:\IA_WORKSPACE`, lancer un run OpenHands réel, consulter le diff,
puis accepter ou restaurer les changements sans régression du profil Général ni
de la mémoire. Elle doit également confirmer les conversations et les souvenirs
après redémarrage, le diagramme facultatif RAM/CPU/VRAM et les erreurs lisibles.
Le remplacement par configuration est documenté dans le
README ; ne télécharge aucun nouveau modèle pour cette validation.

Après cette validation, arrête-toi et attends une demande explicite avant toute
nouvelle étape.
