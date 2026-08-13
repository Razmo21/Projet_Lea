# PROMPT ÉTAPE 7 — RAISONNEMENT ÉQUILIBRÉ, CONTRÔLE DU CŒUR ET CONVERSATION TEMPORAIRE

## 0. Mission

Tu travailles directement dans le dépôt local de **Projet Léa**.

La semi-étape 6.5 a été validée manuellement par l’utilisateur :

- le modèle actif est `models/general/Huihui-Qwen3-4B-abliterated-v2-Q4_K_M.gguf` ;
- sa taille validée est de `2 497 276 672` octets ;
- CUDA et les performances ont été validés ;
- `lea.ps1 start` rend réellement le terminal interactif ;
- l’ancien modèle `models/general/Qwen3-4B-Q4_K_M.gguf` est encore conservé comme solution de retour arrière ;
- Léa est normalement arrêtée proprement au début de cette étape.

L’étape 7 doit être réalisée dans **un seul travail Codex**, mais elle contient trois sous-étapes strictement séquentielles :

```text
7A — modèle et raisonnement équilibré
↓
tests et validation 7A
↓ seulement si 7A fonctionne
7B — contrôle du cœur depuis le frontend
↓
tests et validation 7B
↓ seulement si 7B fonctionne
7C — contexte temporaire de conversation
↓
tests complets
↓
arrêt obligatoire
```

Tu disposes d’une autonomie technique encadrée, car l’utilisateur peut être absent pendant l’exécution. Tu peux :

- choisir entre plusieurs implémentations simples et équivalentes ;
- corriger les bugs directement liés à l’étape ;
- faire plusieurs essais raisonnables ;
- ajouter de petits tests ciblés ;
- ajuster légèrement un paramètre si le build local de `llama.cpp` l’exige.

Cette autonomie ne permet pas de :

- commencer l’étape 8 ou l’étape 9 ;
- ajouter une fonctionnalité non demandée ;
- transformer l’architecture générale ;
- supprimer des données en dehors du fichier GGUF explicitement autorisé en 7A ;
- exposer un service sur le réseau ;
- faire un commit Git.

---

## 1. Lecture obligatoire avant toute modification

Depuis la racine du dépôt, lis intégralement au minimum :

```text
AGENTS.md
README.md
TODO.md
CHANGELOG.md
docs/DECISIONS.md
prompts/PROMPT_ETAPE_7_CODEX.md
```

Inspecte ensuite les fichiers réellement concernés, notamment :

```text
lea.ps1
backend/app/main.py
backend/requirements.txt
backend/README.md
src/App.tsx
src/index.css
vite.config.ts
package.json
package-lock.json
```

Adapte cette liste à la structure réelle du dépôt. Ne suppose pas que le code correspond exactement à un ancien compte rendu : vérifie-le.

Avant de modifier quoi que ce soit :

1. exécute `git status --short` ;
2. repère les modifications déjà présentes ;
3. ne supprime, ne restaure et ne remplace aucune modification appartenant à l’utilisateur ;
4. si une modification existante chevauche directement un fichier que tu dois changer et qu’elle ne correspond pas au résultat validé de 6.5, arrête-toi et explique le conflit ;
5. présente un plan bref, limité à 7A, 7B et 7C.

Ne lance pas automatiquement un téléchargement et n’utilise pas Internet. Tous les composants nécessaires doivent déjà être locaux.

---

## 2. Règles globales obligatoires

Pendant toute l’étape :

- travaille uniquement avec des chemins relatifs à la racine du projet ;
- dans PowerShell, continue d’utiliser `$PSScriptRoot` ;
- n’inscris jamais `L:\Projet_Lea` en dur dans le code ;
- conserve tous les services sur `127.0.0.1` ;
- n’utilise jamais `0.0.0.0` ;
- conserve les protections PID et les validations d’identité des processus ;
- ne tue jamais un processus seulement parce qu’il occupe un port ;
- ne tue jamais un processus étranger ;
- conserve le nettoyage en cas d’échec partiel ;
- conserve le comportement sûr lors d’un double démarrage ou d’un double arrêt ;
- ne casse pas les commandes existantes `start`, `status` et `stop` de `lea.ps1` ;
- n’ajoute ni Docker, ni Ollama, ni Tauri, ni service Windows, ni tâche planifiée ;
- évite toute nouvelle dépendance si la bibliothèque standard ou les dépendances présentes suffisent ;
- si une dépendance est réellement nécessaire, justifie-la et mets correctement à jour les fichiers de verrouillage ;
- ne modifie pas `IA_WORKSPACE` et ne donne aucun accès aux fichiers personnels ;
- n’ajoute aucun accès Internet au modèle ;
- n’ajoute ni base de données, ni SQLite, ni RAG, ni mémoire permanente ;
- n’ajoute pas le streaming des tokens ;
- ne réalise pas la refonte visuelle de l’étape 8 ;
- ne fais aucun commit Git.

La priorité reste : fonctionnalité, simplicité, lisibilité, stabilité et tests.

---

# 7A — MODÈLE ACTIF ET RAISONNEMENT ÉQUILIBRÉ

## 3. Objectifs de 7A

Le modèle Général doit maintenant pouvoir réfléchir avec un niveau par défaut **équilibré**, sans afficher sa pensée interne.

Le résultat attendu est :

```text
question simple
→ réflexion courte si nécessaire
→ réponse rapide

question plus complexe
→ réflexion interne bornée
→ réponse finale seulement
```

Le comportement suivant doit disparaître du fonctionnement normal :

```text
/no_think ajouté automatiquement à chaque question
```

L’utilisateur ne veut pas voir :

```text
[Start thinking]
[End thinking]
<think>
</think>
reasoning_content
```

Il veut uniquement la réponse finale.

---

## 4. Vérifications préalables du modèle

Avant toute suppression :

1. vérifie que `Huihui-Qwen3-4B-abliterated-v2-Q4_K_M.gguf` existe ;
2. vérifie sa taille ;
3. calcule son SHA-256 et consigne le résultat complet dans le compte rendu ;
4. vérifie que `lea.ps1` lance réellement ce nouveau fichier ;
5. vérifie que l’ancien fichier `Qwen3-4B-Q4_K_M.gguf` existe encore ;
6. ne renomme et ne supprime encore aucun GGUF.

Si le nouveau modèle est absent, corrompu, de taille inattendue ou non utilisé par le script, arrête 7A. Ne télécharge rien et ne supprime pas l’ancien modèle.

---

## 5. Mise en œuvre du raisonnement équilibré

Inspecte les capacités exactes du build local de `llama.cpp` et de son API. Utilise les paramètres réellement supportés par ce build ; n’invente pas un champ d’API.

Objectif de référence :

```text
budget de raisonnement visé : environ 512 tokens
```

Cette valeur est une cible, pas une obligation aveugle. Tu peux l’ajuster légèrement si l’API locale fonctionne différemment, à condition de respecter ces critères :

- le raisonnement est activé ;
- il reste borné ;
- une question ordinaire ne provoque pas plusieurs minutes d’attente ;
- le budget de raisonnement ne remplace pas par erreur la limite de la réponse finale ;
- seule la réponse finale est renvoyée au frontend ;
- aucun raisonnement interne n’est enregistré dans l’historique conversationnel de 7C.

Supprime toute injection automatique de `/no_think` dans le flux normal.

Gère correctement le format réellement renvoyé par `llama-server` : champ séparé de raisonnement, balises dans le contenu ou autre format local. Préfère une extraction structurée lorsqu’elle est disponible. Si une défense supplémentaire contre des balises est nécessaire, elle doit être ciblée et ne pas supprimer une réponse finale légitime.

Ne crée pas de sélecteur utilisateur `rapide / équilibré / long` à cette étape. Le mode Général utilise simplement le réglage équilibré par défaut.

Documente dans le code ou dans la documentation opérationnelle l’endroit exact où ce réglage est défini.

---

## 6. Tests obligatoires de 7A

Teste d’abord le serveur modèle directement, puis le backend FastAPI. Termine par un essai via l’interface si elle est disponible à ce moment.

Effectue au minimum les tests suivants :

### Test simple

```text
Quelle est la capitale du Canada ?
```

### Respect strict du format

```text
Réponds uniquement par le mot oui : est-ce que la semaine comporte sept jours ?
```

### Test technique

```text
Explique brièvement la différence entre la pile et le tas en C++.
```

### Test demandant un peu de raisonnement

Utilise un petit problème logique ou technique légal et non ambigu permettant de vérifier que le raisonnement est actif sans demander une réponse interminable.

Pour chaque couche testée, vérifie :

- réponse correcte et non vide ;
- absence de `/no_think` visible ;
- absence de balises ou de contenu de raisonnement visible ;
- latence raisonnable ;
- backend toujours stable après plusieurs questions ;
- CUDA toujours utilisée ;
- modèle non rechargé entre deux questions.

Consigne les paramètres exacts finalement retenus et les temps approximatifs observés.

---

## 7. Suppression autorisée de l’ancien modèle

Seulement après la réussite de tous les tests précédents :

1. arrête proprement Léa ;
2. confirme qu’aucun processus n’utilise encore les fichiers ;
3. vérifie une dernière fois que le nouveau modèle est bien le modèle configuré ;
4. supprime uniquement le fichier exact :

```text
models/general/Qwen3-4B-Q4_K_M.gguf
```

Interdictions absolues :

- ne pas utiliser de joker pour cette suppression ;
- ne pas supprimer le dossier `models/general/` ;
- ne supprimer aucun autre `.gguf` ;
- ne jamais supprimer le nouveau modèle.

Après la suppression, relance un cycle minimal et confirme que Léa démarre et répond encore avec le nouveau modèle. Arrête-la ensuite proprement.

La suppression de cet ancien fichier est la seule suppression matérielle explicitement autorisée dans cette étape.

---

## 8. Barrière 7A

Tu peux commencer 7B uniquement si :

- le nouveau modèle est vérifié ;
- le raisonnement équilibré fonctionne ;
- `/no_think` n’est plus injecté automatiquement ;
- aucune pensée interne n’apparaît ;
- les réponses restent utilisables et suffisamment rapides ;
- le backend est stable ;
- l’ancien modèle a été supprimé seulement après validation ;
- Léa est laissée dans un état propre.

Si un critère échoue, essaie les corrections raisonnables appartenant à 7A. Si tu ne peux pas obtenir un résultat fiable, arrête-toi, nettoie les processus démarrés, conserve l’ancien modèle s’il n’a pas encore été supprimé et rends un compte rendu. **Ne commence pas 7B.**

---

# 7B — CONTRÔLE DU CŒUR DE LÉA DEPUIS LE FRONTEND

## 9. Expérience utilisateur exigée

Le nouveau flux quotidien doit être :

```text
npm run dev
↓
le frontend léger devient disponible sur 127.0.0.1:5173
↓
le modèle et FastAPI restent arrêtés
↓
l’utilisateur clique sur « Démarrer Léa »
↓
le modèle et FastAPI démarrent
↓
Léa devient prête à répondre
```

Puis :

```text
l’utilisateur clique sur « Arrêter Léa »
↓
le modèle et FastAPI s’arrêtent
↓
la VRAM est libérée
↓
le frontend reste ouvert et fonctionnel
↓
le bouton « Démarrer Léa » reste disponible
```

Lancer seulement `npm run dev` ne doit pas charger le modèle et ne doit pas démarrer le backend conversationnel.

---

## 10. Contrôleur local minimal

Une page web seule ne peut pas démarrer un backend totalement arrêté. Mets donc en place le mécanisme local minimal permettant au frontend toujours actif de contrôler le cœur.

Solution privilégiée si elle s’intègre proprement au projet actuel :

- un middleware ou contrôleur local très limité associé au serveur Vite ;
- ou une solution locale équivalente, petite et lisible, lancée par `npm run dev`.

Le choix exact t’appartient, mais il doit respecter toutes les contraintes suivantes :

- il reste actif lorsque FastAPI et le modèle sont arrêtés ;
- il écoute uniquement sur `127.0.0.1` ;
- il n’accepte que les opérations fixes `start-core`, `status-core` et `stop-core`, ou des noms strictement équivalents ;
- aucune commande, aucun chemin et aucun argument arbitraire ne vient du navigateur ;
- il ne devient pas un terminal distant ;
- il ne donne aucun accès générique au système de fichiers ;
- les opérations de mutation utilisent `POST`, pas `GET` ;
- il renvoie des états et erreurs structurés au frontend ;
- il gère simplement les demandes concurrentes ou répétées sans créer de course dangereuse ;
- il réutilise autant que possible la logique sûre de `lea.ps1` au lieu de créer un second gestionnaire de processus incohérent.

N’ajoute pas un gros framework ou un gestionnaire externe pour ce contrôleur.

---

## 11. Évolution de `lea.ps1`

Ajoute si nécessaire les commandes :

```powershell
.\lea.ps1 start-core
.\lea.ps1 status-core
.\lea.ps1 stop-core
```

Des noms légèrement différents sont permis seulement s’ils rendent l’ensemble réellement plus clair.

Comportement attendu :

- `start-core` démarre uniquement `llama-server` puis FastAPI ;
- `status-core` vérifie uniquement le modèle et FastAPI ;
- `stop-core` arrête uniquement FastAPI et le modèle ;
- `stop-core` ne doit jamais arrêter Vite ou le contrôleur léger ;
- `start`, `status` et `stop` continuent de fonctionner pour la pile complète ;
- la logique commune doit être factorisée raisonnablement pour éviter deux implémentations divergentes ;
- les protections PID, identité, heure, chemin, port occupé et nettoyage partiel restent actives ;
- stdin reste correctement détaché pour les processus en arrière-plan ;
- aucun processus étranger n’est tué.

Ne remplace pas cette logique par un simple `taskkill` basé sur le nom ou le port.

---

## 12. Modifications fonctionnelles minimales du frontend

Ajoute uniquement ce qui est nécessaire à cette étape :

- un bouton `Démarrer Léa` ;
- un bouton `Arrêter Léa` ;
- un état visible parmi des états équivalents à :

```text
Léa arrêtée
Démarrage…
Léa prête
Arrêt…
Erreur
```

- un message d’erreur clair si une opération échoue ;
- désactivation cohérente des boutons pendant une transition ;
- désactivation ou gestion claire de l’envoi d’un message lorsque le cœur est arrêté ;
- actualisation légère de l’état, sans boucle agressive.

Le design doit rester minimal. Ne commence pas :

- la nouvelle palette ;
- les grands effets visuels ;
- les animations complexes ;
- la grande refonte des composants ;
- le rendu Markdown complet prévu pour l’étape 8.

---

## 13. Tests obligatoires de 7B

Teste au minimum :

### Flux principal depuis le frontend

1. tout arrêter ;
2. lancer uniquement `npm run dev` ;
3. vérifier que la page est accessible ;
4. vérifier que FastAPI et le modèle sont encore arrêtés ;
5. démarrer Léa depuis le contrôle frontend ;
6. attendre l’état `Léa prête` ;
7. envoyer une question et obtenir une réponse réelle ;
8. arrêter Léa depuis le frontend ;
9. vérifier que FastAPI et le modèle sont arrêtés ;
10. vérifier que la page et le contrôleur restent disponibles ;
11. refaire un second cycle complet depuis les boutons.

### Commandes PowerShell

Teste séparément, lorsque Vite n’occupe pas déjà son port :

```powershell
.\lea.ps1 start
Write-Output "TERMINAL_LIBRE_ETAPE_7"
.\lea.ps1 status
.\lea.ps1 stop
.\lea.ps1 status
```

Teste également les nouvelles commandes du cœur directement.

### Robustesse

Vérifie :

- démarrage du cœur déjà démarré ;
- arrêt du cœur déjà arrêté ;
- clics répétés ou requêtes rapprochées ;
- échec partiel de démarrage et nettoyage ;
- processus tiers sur un port du cœur : refus clair et aucun kill ;
- `stop-core` ne ferme jamais le frontend ;
- `stop` complet libère toujours les trois ports lorsqu’il possède les processus ;
- après arrêt du cœur, aucun `llama-server` ne reste et la VRAM redescend.

Si un test de panne modifie temporairement un fichier ou un état, restaure-le immédiatement après le test.

---

## 14. Barrière 7B

Tu peux commencer 7C uniquement si :

- `npm run dev` laisse le cœur arrêté ;
- les boutons démarrent et arrêtent réellement FastAPI et le modèle ;
- le frontend reste disponible après `stop-core` ;
- deux cycles complets fonctionnent ;
- les anciennes commandes PowerShell restent fonctionnelles ;
- la sécurité des PID et des ports n’a pas régressé ;
- aucun service n’écoute publiquement ;
- les erreurs sont propres et compréhensibles.

Si un critère échoue, corrige les problèmes appartenant à 7B. Si le résultat ne peut pas être rendu fiable, arrête et rends un compte rendu. **Ne commence pas 7C.**

---

# 7C — CONTEXTE TEMPORAIRE DE CONVERSATION

## 15. Objectif fonctionnel

Aujourd’hui, chaque question est indépendante. Après 7C, le scénario suivant doit fonctionner :

```text
Utilisateur : Mon chien s’appelle Rex.
Léa : D’accord.

Utilisateur : Comment s’appelle mon chien ?
Léa : Rex.
```

Il s’agit uniquement d’un contexte temporaire de la conversation en cours.

Il ne s’agit pas encore de :

- mémoire permanente ;
- historique conservé après fermeture ;
- SQLite ;
- base de données ;
- RAG ;
- mémoire vectorielle ;
- extraction automatique de souvenirs ;
- commande `Souviens-toi` ou `Oublie`.

---

## 16. Stratégie de conversation

Choisis l’implémentation la plus simple et la plus fiable compatible avec l’application actuelle.

Contraintes obligatoires :

- l’historique temporaire contient uniquement les messages utiles `user` et `assistant` ;
- le raisonnement caché du modèle n’est jamais ajouté à l’historique ;
- un message d’erreur technique n’est pas mémorisé comme une réponse de Léa ;
- les données restent en mémoire vive seulement ;
- aucun fichier de conversation n’est créé ;
- aucun `localStorage`, `IndexedDB` ou autre stockage durable n’est utilisé ;
- un rechargement complet ou une fermeture de la session peut faire disparaître le contexte ;
- le backend valide les rôles, types, tailles et contenus reçus ;
- le client ne peut pas injecter arbitrairement un rôle système interne ;
- la route actuelle `/chat` reste simple et, si raisonnable, compatible avec une requête ne contenant qu’une question.

Le frontend doit afficher au minimum la suite des messages de la conversation, avec un style fonctionnel très simple. Une commande minimale `Nouvelle conversation` ou `Effacer la conversation` peut être ajoutée afin de vider explicitement le contexte temporaire, sans anticiper la gestion persistante de l’étape 9.

Si le cœur est arrêté puis redémarré alors que la page reste ouverte, conserver la conversation affichée et pouvoir la renvoyer au backend est souhaitable si cela découle naturellement de l’architecture retenue. Cela ne doit pas conduire à un stockage persistant.

---

## 17. Gestion de la fenêtre de contexte

Le serveur utilise actuellement une fenêtre d’environ :

```text
-c 4096
```

Mets en place une stratégie simple empêchant l’historique de dépasser cette fenêtre.

La stratégie doit :

- réserver suffisamment de place pour les instructions internes, le raisonnement et la réponse finale ;
- conserver le message utilisateur le plus récent ;
- conserver autant que possible les échanges récents complets ;
- retirer d’abord les plus anciens échanges lorsque le budget est dépassé ;
- éviter de conserver une réponse sans la question correspondante ;
- ne jamais produire une requête invalide ou une erreur 500 simplement parce que la conversation devient longue.

Utilise le comptage de tokens fourni localement par `llama.cpp` s’il est disponible de manière simple et fiable. Sinon, utilise une estimation conservatrice, documentée et testée. Ne construis pas un système de résumé automatique, de RAG ou de mémoire vectorielle.

---

## 18. Tests obligatoires de 7C

Teste au minimum :

### Mémoire temporaire immédiate

```text
Mon chien s’appelle Rex.
Comment s’appelle mon chien ?
```

La seconde réponse doit identifier Rex.

### Plusieurs tours

Effectue une conversation d’au moins quatre messages utilisateur liés entre eux et vérifie que Léa conserve le contexte récent.

### Réinitialisation

Réinitialise ou recrée la conversation, puis vérifie que Léa ne prétend plus connaître Rex à partir de l’ancien échange.

### Historique long

Teste un historique synthétique assez long pour déclencher la suppression des échanges les plus anciens. Vérifie :

- aucune erreur de dépassement de contexte ;
- conservation des messages récents ;
- retrait cohérent des anciennes paires ;
- réponse finale toujours visible sans pensée interne.

### Erreur intermédiaire

Simule ou provoque proprement une indisponibilité du modèle, puis vérifie qu’une erreur ne corrompt pas l’historique. Restaure immédiatement l’état normal.

### Compatibilité

Vérifie que :

- une première question sans historique fonctionne ;
- les contrôles start/stop de 7B fonctionnent toujours ;
- le modèle n’est pas rechargé entre deux messages ;
- aucune donnée de conversation n’est créée sur disque.

---

# TESTS GLOBAUX, DOCUMENTATION ET ARRÊT

## 19. Tests globaux obligatoires

Après 7A, 7B et 7C, exécute tous les tests existants pertinents ainsi que, au minimum :

```text
npm run build
python -m compileall backend/app
git diff --check
```

Utilise l’interpréteur du `.venv` du projet pour Python sous Windows.

Ajoute ou adapte de petits tests automatisés lorsque cela améliore réellement la fiabilité, en particulier pour :

- la validation et la réduction de l’historique ;
- les réponses du contrôleur local ;
- les nouvelles commandes de `lea.ps1` si elles peuvent être vérifiées sans fragilité excessive.

Effectue ensuite un test complet réel :

```text
npm run dev
→ frontend disponible, cœur arrêté
→ Démarrer Léa
→ conversation liée sur plusieurs tours
→ Arrêter Léa
→ frontend encore disponible
→ second démarrage
→ réponse réelle
→ arrêt final
```

Vérifie à la fin :

- ports `5173`, `8000` et `8080` libérés ;
- aucun processus Léa résiduel ;
- aucun `llama-server` actif ;
- VRAM revenue près de son niveau de repos ;
- terminal utilisable ;
- `git diff --check` propre.

Laisse **Léa complètement arrêtée** à la fin, y compris Vite et le contrôleur léger.

---

## 20. Documentation à mettre à jour

Mets à jour uniquement la documentation réellement affectée, notamment selon les besoins :

```text
README.md
backend/README.md
CHANGELOG.md
docs/DECISIONS.md
AGENTS.md
TODO.md
```

La documentation doit expliquer clairement :

- le nouveau comportement de raisonnement équilibré ;
- le fait que la pensée interne reste cachée ;
- le flux quotidien `npm run dev` puis boutons start/stop ;
- les commandes complètes et les commandes du cœur dans `lea.ps1` ;
- le rôle limité du contrôleur local ;
- le caractère temporaire du contexte de conversation ;
- la stratégie simple de réduction de l’historique.

À la fin, `TODO.md` doit refléter :

```text
Étapes 1 à 7 : terminées
Étape 8 : prochaine étape — refonte visuelle complète
Étape 9 : planifiée — historique local persistant et gestion des conversations
```

L’étape 9 utilisera probablement SQLite, mais **ne doit absolument pas être commencée maintenant**.

`docs/DECISIONS.md` doit enregistrer les décisions d’architecture réellement prises pendant 7A, 7B et 7C, sans inventer de choix futurs non validés.

Tu peux mettre à jour la mention de l’étape courante dans `AGENTS.md`, mais ne supprime aucune règle générale de travail ou de sécurité.

Ne modifie pas le présent fichier de prompt.

---

## 21. Interdictions finales de périmètre

Ne profite pas de cette étape pour ajouter :

- refonte CSS complète ;
- rendu Markdown complet ;
- coloration syntaxique avancée ;
- streaming ;
- historique persistant ;
- SQLite ;
- mémoire personnelle ;
- RAG ;
- accès à `IA_WORKSPACE` ;
- outils système pour le modèle ;
- recherche Web ;
- voix ;
- images ;
- profils Développement, Santé animale ou Vision ;
- application desktop ;
- authentification ;
- télémétrie externe.

N’effectue aucun travail préparatoire caché pour les étapes 8 ou 9.

---

## 22. Compte rendu final obligatoire

À la fin, fournis un compte rendu concis mais complet contenant :

1. le résultat de 7A, 7B et 7C séparément ;
2. le réglage exact de raisonnement retenu et pourquoi ;
3. la confirmation que la pensée interne n’est jamais affichée ;
4. la confirmation et le chemin exact de l’ancien GGUF supprimé ;
5. l’architecture choisie pour le contrôleur local ;
6. le fonctionnement exact de `start-core`, `status-core` et `stop-core` ;
7. l’emplacement temporaire de l’historique et la stratégie de réduction ;
8. tous les fichiers créés, modifiés ou supprimés ;
9. toutes les commandes de test exécutées ;
10. les résultats des deux cycles start/stop ;
11. les performances approximatives du modèle ;
12. les limites ou points restant à tester manuellement ;
13. le résultat final de `git status --short` ;
14. la confirmation que Léa est complètement arrêtée.

Ne fais pas de commit. L’utilisateur effectuera lui-même le test manuel final et le commit après validation.

---

## 23. Point d’arrêt absolu

Lorsque l’étape 7 et ses tests sont terminés :

```text
STOP
```

Ne commence ni l’étape 8 ni l’étape 9.
