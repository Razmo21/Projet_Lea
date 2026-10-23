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

Les étapes 10 à 14 sont validées manuellement et terminées. L’étape 15 intègre
le profil Vétérinaire local Qwen3.5-9B Q4_K_M et optimise les contrats seulement
lorsque la comparaison ne révèle pas de régression. Son implémentation technique,
ses mesures, ses erreurs scientifiques connues et ses essais sont consignés dans
`docs/ETAPE_15_VALIDATION.md`; la validation manuelle dans Edge reste requise.

Ne commence pas l’étape 16 — Web. La vision reste suspendue et reportée ; le
profil Auxiliaire est supprimé définitivement de la roadmap. Ne réintroduis ni
l’un ni l’autre. Aucun commit ni push sans demande explicite.

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

L’exception d’installation des moteurs et poids STT/TTS locaux était strictement
limitée à l’étape 14 et est désormais close. Le modèle vétérinaire déjà fourni
par l’utilisateur est le seul poids ajouté à l’étape 15. Aucun remplacement de
Qwen, réduction de contexte, téléchargement automatique au fonctionnement normal
ou API distante.

`config/models.json` (schéma 3) est l’unique registre. Les profils portent leurs
contrats et permissions ; `models` porte les paramètres des modèles et
`profiles[].model_id` les associe. Ne réintroduis pas de dépendance au nom de
Qwen dans le code métier ni de parseur concurrent dans les lanceurs.

Les préférences fonctionnelles sont dans SQLite (`user_preferences`, migrations 8–12),
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

## Non-régression acquise aux étapes 14 et 15

La non-régression doit conserver Paramètres (ouverture, Low/High, Valider,
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

La validation manuelle de l’étape 14 a confirmé le microphone, les deux voix et
leurs paramètres. Le profil Vétérinaire réutilise ces chemins sans audio privé
persistant et sans nouvelle capacité. Conserver la distinction entre essais
simulés et physiques, les mesures de ressources et toutes les barrières vocales.
Low/High Vétérinaire utilise uniquement le paramètre natif Qwen3.5 validé et
reste indépendant de Général ; Programmation ne reçoit aucun faux contrôle.
Ne commencer aucune étape suivante sans demande explicite.
