# Prompt Codex — Étape 8 complète de Projet Léa

Tu dois réaliser **l’étape 8 au complet**, de **8A à 8F**, directement dans le projet situé ici :

```text
L:\Projet_Lea
```

Tu dois travailler de manière **totalement autonome** jusqu’à ce que l’implémentation, les tests réels, la documentation et le nettoyage final soient terminés.

---

# 1. Autorisation totale et règles impératives

Tu as mon autorisation explicite pour effectuer, sans me demander de confirmation, **toutes les actions techniques nécessaires** à la réalisation complète de cette étape, notamment :

- inspecter l’intégralité du dépôt et son historique Git ;
- lire les diffs et retrouver précisément les changements des étapes précédentes ;
- modifier, créer, déplacer ou supprimer les fichiers du projet ;
- restructurer du code lorsque cela est techniquement nécessaire ;
- exécuter PowerShell, Python, npm, Node, Vite, FastAPI, SQLite et les outils de compilation ;
- démarrer, arrêter ou tuer les processus de Léa ;
- utiliser les ports locaux du projet ;
- lancer le véritable modèle local ;
- effectuer des mesures GPU, VRAM, CPU et performances ;
- créer des bases SQLite temporaires ;
- lancer Microsoft Edge Stable ;
- automatiser Microsoft Edge ;
- utiliser un profil Edge temporaire et isolé ;
- installer une dépendance de développement ou de test réellement indispensable ;
- écrire des scripts temporaires de diagnostic ou de test ;
- corriger automatiquement tous les problèmes rencontrés ;
- adapter le plan d’exécution lorsqu’une commande ou une approche échoue ;
- relancer les tests autant de fois que nécessaire.

## Interdiction absolue

Tu ne dois faire :

- **aucun commit Git** ;
- aucun `git push` ;
- aucun tag ;
- aucune modification irréversible de l’historique Git ;
- aucune modification des fichiers personnels extérieurs au projet ;
- aucune utilisation de mon profil Microsoft Edge personnel ;
- aucune suppression de données extérieures au projet ou aux environnements temporaires créés pour les tests.

Tu peux utiliser Git pour inspecter l’historique, les commits, les diffs et l’état du dépôt, mais tu dois laisser toutes les modifications finales **non commitées**.

## Autonomie obligatoire

Tu ne dois pas me demander :

- de confirmer une modification ;
- d’exécuter une commande ;
- de démarrer ou d’arrêter un service ;
- de choisir entre plusieurs solutions techniques ;
- d’autoriser l’installation d’un outil nécessaire ;
- de tester manuellement une fonctionnalité ;
- de décider quoi faire après une erreur ;
- de répondre à une question intermédiaire.

Lorsqu’un problème survient :

1. diagnostique-le ;
2. consulte les fichiers, les logs et les outils disponibles ;
3. essaie une autre approche ;
4. corrige le problème ;
5. relance les tests concernés ;
6. continue jusqu’à la fin.

Ne t’arrête pas après une implémentation partielle. Ne laisse aucun faux bouton, aucun code temporaire, aucun comportement simulé et aucun `TODO` remplaçant une fonctionnalité demandée.

Tu dois fournir **uniquement ton compte rendu final lorsque tout le travail est terminé**. Ne me demande rien pendant l’exécution.

---

# 2. État actuel à préserver

L’étape 7 a été entièrement vérifiée et validée.

## 7A actuellement

Le modèle Général actif est :

```text
Huihui-Qwen3-4B-abliterated-v2-Q4_K_M.gguf
```

Informations connues :

```text
Taille    : 2 497 276 672 octets
SHA-256   : B5573DC1AEC4AB39B0BDCE907F7354034CA78A16635288765A4D51AE61E5B6A4
```

Le modèle fonctionne actuellement avec :

```text
--reasoning on
--reasoning-budget 512
-c 4096
```

Le backend utilise actuellement un maximum de réponse distinct d’environ :

```text
max_tokens = 1024
```

Le filtrage défensif des pensées internes existe déjà.

## 7B actuellement

Le contrôle du cœur fonctionne :

- démarrage depuis l’interface ;
- consultation de l’état ;
- arrêt depuis l’interface ;
- Vite reste ouvert lorsque le cœur est arrêté ;
- les ports du modèle et du backend sont libérés correctement ;
- les routes de mutation sont locales et protégées ;
- Vite est limité à `127.0.0.1` ;
- le port 5173 est strict ;
- les processus sont identifiés et protégés par leurs informations réelles ;
- les commandes PowerShell `start-core`, `status-core` et `stop-core` fonctionnent.

Tu ne dois pas casser ces mécanismes.

## 7C actuellement

Le contexte temporaire fonctionne :

- l’historique est actuellement conservé uniquement en RAM dans le frontend ;
- le backend valide strictement les rôles et les messages ;
- seuls les rôles `user` et `assistant` sont autorisés ;
- les paires d’historique sont contrôlées ;
- les rôles système venant du client sont refusés ;
- les champs inconnus et les contenus invalides sont refusés ;
- le reset envoie un historique vide ;
- les erreurs n’ajoutent pas de faux message ;
- le modèle n’est pas rechargé entre les messages.

L’étape 8 remplacera la RAM comme source officielle par SQLite, mais tu dois préserver les protections de validation pertinentes.

---

# 3. Inspection obligatoire avant toute modification

Avant de modifier le projet :

1. exécute `git status` ;
2. inspecte les derniers commits ;
3. inspecte les diffs pertinents ;
4. retrouve précisément les modifications introduites pendant 7A ;
5. identifie les parties de fichiers qui appartiennent à 7B et 7C ;
6. lis au minimum :
   - `AGENTS.md` ;
   - `TODO.md` ;
   - `CHANGELOG.md` ;
   - `lea.ps1` ;
   - le backend FastAPI ;
   - le frontend React/Vite ;
   - les tests existants ;
   - les configurations de lancement ;
7. confirme dans le code les chemins, ports, paramètres et versions réellement utilisés ;
8. exécute les tests de référence existants avant de commencer ;
9. mesure la situation actuelle à 4 096 tokens avant de la modifier.

Tu dois restaurer uniquement ce qui concerne le retour à `/no_think`. Tu ne dois jamais annuler globalement un fichier ou un commit si ce fichier contient aussi des améliorations de 7B ou 7C.

Évite les restaurations aveugles comme un remplacement complet d’un fichier par une ancienne version.

---

# 4. Périmètre de la mémoire permanente pour l’étape 8

L’architecture générale prévue pour Léa est :

```text
Léa
│
├── conversations
│   ├── Conversation 1
│   │   ├── message utilisateur
│   │   ├── réponse Léa
│   │   └── ...
│   └── Conversation 2
│
├── souvenirs
│   ├── prénom
│   ├── préférences
│   ├── projets
│   └── faits explicitement mémorisés
│
└── recherche mémoire
    └── retrouve seulement ce qui est pertinent
```

Cependant, le périmètre précis de **cette étape 8** est le suivant :

- implémenter la persistance locale complète des **conversations** ;
- implémenter la persistance des **messages** ;
- implémenter la recherche locale parmi les conversations ;
- faire de FastAPI et SQLite la source officielle de l’historique ;
- préparer une architecture propre et migrable pour les futures fonctions.

Ne pas encore implémenter :

- la mémoire personnelle entre conversations ;
- les souvenirs comme le prénom ou les préférences ;
- la table fonctionnelle `memories` ;
- le RAG ;
- les embeddings ;
- la recherche sémantique ;
- les index vectoriels ;
- les pièces jointes ;
- les dossiers de projets ;
- les permissions avancées ;
- les paramètres persistants de Léa.

L’architecture future pourra éventuellement devenir :

```text
L:\Projet_Lea\
├── data\
│   ├── lea.sqlite3
│   ├── attachments\
│   └── indexes\
```

Mais, pendant l’étape 8, le fichier principal à créer est précisément :

```text
L:\Projet_Lea\data\lea.sqlite3
```

N’utilise pas un ensemble de fichiers `.txt` représentant chaque conversation.

Ne crée pas de tables spéculatives inutilisées uniquement pour imiter l’architecture future. Utilise plutôt un système de migrations permettant de les ajouter proprement plus tard.

---

# 5. Contrainte visuelle

## Aucune refonte CSS pendant cette étape

Tu dois conserver autant que possible :

- l’apparence actuelle ;
- les couleurs actuelles ;
- la typographie actuelle ;
- les espacements généraux actuels ;
- la structure visuelle actuelle ;
- le fonctionnement actuel du panneau de contrôle du cœur.

Tu peux faire les petites modifications CSS strictement nécessaires pour :

- afficher la liste des conversations ;
- afficher les boutons fonctionnels ;
- indiquer une erreur ;
- afficher un état de chargement ;
- rendre les nouvelles commandes utilisables ;
- empêcher un débordement ou une interface cassée.

Tu ne dois pas :

- refaire tout le design ;
- créer un nouveau thème ;
- déplacer inutilement toutes les sections ;
- remplacer la structure visuelle globale ;
- effectuer une refonte responsive générale ;
- transformer cette étape fonctionnelle en chantier esthétique.

La refonte visuelle sera simplement indiquée comme reportée, sans lui attribuer un nouveau numéro d’étape.

---

# 6. Étape 8A — Retour permanent à `/no_think` et contexte étendu

## 8A.1 Retour permanent au mode sans réflexion

Le modèle Général doit redevenir constamment en mode sans réflexion.

Il n’y aura :

- aucun sélecteur utilisateur ;
- aucun bouton réflexion ;
- aucun mode équilibré ;
- aucun budget de raisonnement ;
- aucune pensée interne visible.

Tu dois :

1. retrouver dans l’historique Git le mécanisme automatique `/no_think` utilisé avant 7A ;
2. restaurer uniquement ce mécanisme ;
3. supprimer les paramètres de raisonnement introduits en 7A ;
4. retirer notamment :
   - `--reasoning on` ;
   - `--reasoning-budget 512` ;
5. ne pas restaurer d’anciens éléments qui annuleraient 7B ou 7C ;
6. conserver les protections de filtrage des balises de pensée ;
7. renforcer le filtre afin qu’il gère aussi correctement :
   - `<think>...</think>` ;
   - une balise `<think>` incomplète ;
   - une balise fermante isolée `</think>` ;
   - plusieurs blocs de pensée ;
   - les variations raisonnables de casse ou d’espacement si le format le permet ;
8. considérer une réponse vide après filtrage comme un échec propre, et non comme une réponse réussie.

## 8A.2 Règle absolue pour `/no_think`

`/no_think` doit être injecté uniquement dans une **copie interne** de la requête construite par le backend pour le modèle.

Il ne doit jamais être :

- affiché dans l’interface ;
- ajouté au texte original de l’utilisateur ;
- renvoyé par l’API comme contenu utilisateur ;
- conservé dans l’état React ;
- stocké dans SQLite ;
- ajouté à l’historique de conversation ;
- inclus dans le titre automatique ;
- visible dans les requêtes envoyées par le frontend ;
- inscrit dans un export futur ;
- sauvegardé comme message ;
- exposé dans une erreur utilisateur.

Le message enregistré dans SQLite doit rester exactement le message réel de l’utilisateur, sous réserve d’une normalisation minimale et clairement justifiée.

Le backend doit construire séparément :

```text
message_original_persisté
```

et :

```text
copie_interne_envoyée_au_modèle_avec_no_think
```

## 8A.3 Contexte de 8 192 tokens

Commence par établir un point de référence réel à 4 096 tokens, puis passe le serveur à :

```text
8192
```

Tu dois adapter ensemble :

- le lancement de `llama-server` ;
- le budget du backend ;
- la réduction de l’historique ;
- les constantes et configurations ;
- les tests ;
- la documentation.

Évite que le frontend, le backend et PowerShell possèdent des valeurs contradictoires.

Utilise de préférence une source de configuration claire, ou une transmission explicite de la valeur entre le lanceur et le backend.

## 8A.4 Budget du contexte

Il n’y a plus de réserve de 512 tokens pour le raisonnement.

Le budget cible peut partir de cette logique :

```text
Contexte total                  : 8192
Réponse finale réservée         : 1024
Instructions système/template   : réserve prudente
Question + historique           : reste disponible
```

Une première estimation raisonnable serait environ :

```text
8192 - 1024 - 512 = 6656
```

Mais ne transforme pas ce chiffre en valeur magique incorrecte si le template réel exige une autre marge.

Tu dois :

- mesurer ou estimer prudemment le coût du template ;
- conserver une réserve de sécurité ;
- ne jamais envoyer une requête dépassant la fenêtre réelle ;
- conserver les échanges les plus récents ;
- préserver l’ordre chronologique ;
- conserver uniquement des paires utilisateur/réponse complètes pour l’ancien historique ;
- toujours réserver la place nécessaire au nouveau message ;
- retourner une erreur claire si le nouveau message seul est trop grand ;
- conserver tous les anciens messages dans SQLite même lorsqu’ils ne sont plus envoyés au modèle.

Tu peux conserver l’estimation conservatrice actuelle si elle est fiable, ou utiliser une méthode de tokenisation déjà disponible localement. Ne prétends pas disposer d’un compte exact si tu utilises seulement une estimation.

## 8A.5 Aucun RoPE ou YaRN

Ne configure pas :

- YaRN ;
- une mise à l’échelle RoPE ;
- un facteur de contexte artificiel ;
- une extension non nécessaire de la fenêtre du modèle.

Utilise la fenêtre native et les capacités réelles prises en charge par la version locale de `llama-server`.

## 8A.6 Un seul cache de conversation

Vérifie les options réellement prises en charge par la version locale de `llama-server`.

Assure-toi qu’un seul usage conversationnel ne provoque pas l’allocation accidentelle de plusieurs caches complets de 8 192 tokens.

Vérifie notamment :

- le nombre de slots ;
- le parallélisme ;
- les options équivalentes à un seul slot si elles sont nécessaires ;
- l’absence de plusieurs instances du modèle ;
- l’absence de rechargement entre deux messages ;
- la conservation du même PID pendant une conversation normale.

N’invente pas un paramètre de ligne de commande sans vérifier qu’il est pris en charge par le binaire utilisé.

## 8A.7 Mesures de performance

Avant modification, mesure à 4 096 tokens :

- temps de démarrage du modèle ;
- temps avant la première réponse ou premier token mesurable ;
- temps total de réponse ;
- débit de génération si disponible ;
- utilisation VRAM totale ;
- présence du processus dans `nvidia-smi` ;
- PID du modèle ;
- comportement sur plusieurs messages.

Après passage à 8 192, répète les mêmes mesures avec :

- les mêmes prompts ;
- le même modèle ;
- le modèle déjà chaud pour les comparaisons de réponses courtes ;
- plusieurs exécutions ;
- une comparaison fondée de préférence sur la médiane plutôt qu’une seule mesure.

## 8A.8 Critères d’acceptation de 8 192

Conserve 8 192 si :

- toutes les couches prévues restent sur CUDA ;
- il n’y a pas de débordement vers le CPU ;
- aucune erreur CUDA ne survient ;
- aucune saturation VRAM critique ne survient ;
- il reste une marge VRAM raisonnable, idéalement au moins environ 700 Mo ;
- une réponse courte ne perd pas plus d’environ 10 % de vitesse par rapport au point de référence, après mesures répétées et modèle chaud ;
- le modèle garde le même PID entre les messages ;
- le modèle ne se recharge pas ;
- une conversation synthétique proche de la limite fonctionne ;
- aucune pensée interne n’est affichée ;
- aucune pensée interne n’est enregistrée ;
- `/no_think` n’apparaît nulle part dans les données visibles ou persistées ;
- le serveur reste stable durant plusieurs tours.

Sous WDDM, si la mémoire par processus apparaît comme `N/A`, utilise des preuves complémentaires :

- mémoire GPU totale avant/après ;
- PID présent ;
- logs CUDA ;
- nombre de couches chargées ;
- absence de fallback CPU ;
- stabilité réelle.

## 8A.9 Valeurs de secours automatiques

Si 8 192 échoue réellement malgré un diagnostic et des corrections raisonnables :

1. teste automatiquement 7 168 ;
2. si nécessaire, teste automatiquement 6 144 ;
3. conserve la plus grande valeur stable.

Ne me demande pas quelle valeur choisir.

Ne baisse pas la valeur uniquement pour gagner du temps ou éviter un test.

Si 8 192 dépasse légèrement un seuil à cause d’une mesure manifestement bruitée, répète les mesures avant de conclure.

Si 8 192, 7 168 et 6 144 échouent tous après diagnostic, restaure la dernière valeur réellement stable, termine les autres parties de l’étape et explique précisément les preuves dans le compte rendu final.

---

# 7. Étape 8B — Base SQLite locale

Après avoir validé la configuration retenue en 8A, implémente la base SQLite locale.

## 8B.1 Emplacement

Le chemin par défaut doit être :

```text
L:\Projet_Lea\data\lea.sqlite3
```

Le code ne doit cependant pas dépendre d’un chemin codé en dur impossible à tester.

Ajoute une configuration telle que :

```text
LEA_DB_PATH
```

ou une solution équivalente claire.

Comportement attendu :

- chemin par défaut vers `data\lea.sqlite3` ;
- possibilité de fournir une base temporaire pendant les tests ;
- création automatique du dossier `data` s’il n’existe pas ;
- erreurs propres si le chemin est réellement inaccessible.

## 8B.2 Fichiers exclus de Git

Ajoute les exclusions nécessaires pour :

```text
*.sqlite
*.sqlite3
*.db
*.sqlite-wal
*.sqlite-shm
*.sqlite3-wal
*.sqlite3-shm
*.db-wal
*.db-shm
```

Adapte les motifs au dépôt sans exclure accidentellement des fichiers source pertinents.

Tu peux conserver le dossier `data` dans Git avec un fichier approprié si nécessaire, mais la vraie base et ses fichiers WAL/SHM ne doivent pas être versionnés.

## 8B.3 Mode SQLite

Configure explicitement et vérifie :

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
```

Ajoute également des réglages raisonnables comme un délai d’attente en cas de verrouillage, sans sacrifier l’intégrité.

Utilise :

- des requêtes paramétrées ;
- des transactions explicites ;
- des clés étrangères ;
- des contraintes `CHECK` ;
- des index utiles ;
- une gestion propre de la connexion ;
- des fermetures propres ;
- des horodatages cohérents en UTC.

## 8B.4 Migrations

Implémente un véritable mécanisme de migration local et testable.

Il doit :

- reconnaître la version actuelle du schéma ;
- créer une base vide ;
- appliquer les migrations dans l’ordre ;
- être idempotent ;
- refuser ou signaler proprement une version future inconnue ;
- exécuter chaque migration de façon transactionnelle lorsque SQLite le permet ;
- permettre l’ajout ultérieur de `memories`, `attachments`, `indexes`, `projects`, `permissions` et `settings` sans réécrire tout le système.

Une table de version telle que `schema_migrations` est acceptable.

N’introduis pas un ORM lourd si le projet n’en utilise pas et si SQLite standard suffit.

## 8B.5 Table `conversations`

La table doit au minimum permettre de stocker :

- un identifiant stable ;
- un titre ;
- l’origine du titre, automatique ou manuelle ;
- la date de création ;
- la date de dernière modification ;
- une révision entière pour le contrôle de concurrence ;
- les métadonnées réellement nécessaires au fonctionnement.

Le titre automatique doit être déterministe et local, par exemple à partir du premier message utilisateur :

- espaces normalisés ;
- longueur raisonnablement limitée ;
- aucune requête supplémentaire au modèle ;
- aucun `/no_think` ;
- aucune balise interne.

Un titre renommé manuellement ne doit pas être remplacé automatiquement plus tard.

Si le premier message est modifié et que le titre est toujours automatique, le titre peut être recalculé. S’il est manuel, il doit rester inchangé.

## 8B.6 Table `messages`

La table doit au minimum permettre de stocker :

- un identifiant stable ;
- l’identifiant de la conversation ;
- un ordre explicite dans la conversation ;
- le rôle ;
- le contenu ;
- l’état ;
- une erreur éventuelle ;
- la date de création ;
- la date de modification.

Rôles permis :

```text
user
assistant
```

Aucun rôle `system` ne doit être stocké comme message de conversation.

États fonctionnels obligatoires :

```text
pending
completed
failed
```

Ils peuvent être affichés en français dans l’interface :

```text
en attente
terminé
échec
```

La contrainte d’ordre doit empêcher deux messages d’occuper silencieusement la même position dans une conversation.

La suppression d’une conversation doit supprimer ses messages par clé étrangère avec cascade.

## 8B.7 Sémantique des états

Pour concilier l’enregistrement de la question avant génération et l’absence de fausse réponse :

- le message utilisateur est enregistré avant de lancer le modèle ;
- il est initialement associé à une génération en attente ;
- aucune ligne de réponse assistant vide ou fictive ne doit être créée ;
- en cas de réussite :
  - la réponse finale filtrée est insérée ;
  - l’état de la question devient terminé ;
- en cas d’échec :
  - la question reste dans SQLite ;
  - elle devient échouée ;
  - l’erreur interne est réduite à une information sûre ;
  - aucune réponse assistant fictive n’est enregistrée ;
  - la question peut être réessayée.

Tu peux organiser les colonnes précisément comme tu le juges le plus propre, mais ces comportements sont obligatoires.

Au démarrage du backend, toute génération restée `pending` à cause d’un arrêt brutal doit être détectée et convertie en état récupérable, généralement `failed`, afin que l’utilisateur puisse réessayer.

## 8B.8 Données interdites dans SQLite

Ne stocke jamais :

- `/no_think` ;
- le prompt système interne ;
- une pensée `<think>` ;
- une réponse brute contenant le raisonnement si une version filtrée existe ;
- un rôle système injecté par un client ;
- un faux message assistant ;
- le contenu d’une erreur technique détaillée contenant des secrets ou des chemins sensibles inutiles.

---

# 8. Étape 8C — Backend et conversations persistantes

FastAPI devient la source officielle de l’historique.

Le frontend ne doit plus envoyer tout l’historique comme autorité.

## 8C.1 Requête principale

Pour un nouveau message, le frontend doit principalement transmettre :

```text
conversation_id
nouveau message
révision attendue
```

Pour une nouvelle conversation, `conversation_id` peut être absent ou nul selon l’API retenue.

Le backend doit alors :

1. créer la conversation si nécessaire ;
2. charger l’historique depuis SQLite ;
3. vérifier la révision ;
4. vérifier qu’aucune génération concurrente n’est active ;
5. enregistrer le message utilisateur ;
6. construire le contexte compatible avec la fenêtre active ;
7. injecter `/no_think` uniquement dans la copie interne ;
8. appeler le modèle ;
9. filtrer la réponse ;
10. enregistrer uniquement la réponse finale valide ;
11. retourner les identifiants, les messages et la nouvelle révision nécessaires au frontend.

## 8C.2 API stricte

Utilise des modèles Pydantic stricts.

Refuse :

- les champs inconnus ;
- les rôles fournis arbitrairement ;
- un rôle système ;
- un historique complet fourni par le navigateur ;
- un identifiant de conversation invalide ;
- un message vide après normalisation ;
- les caractères NUL ;
- les contenus trop grands ;
- une révision périmée ;
- une mutation pendant une autre génération de la même conversation.

Si une ancienne route est conservée temporairement pour compatibilité, elle ne doit pas permettre au client de redevenir la source d’autorité de l’historique.

## 8C.3 Routes fonctionnelles

Implémente une API claire couvrant au minimum :

- créer ou commencer une conversation ;
- lister les conversations ;
- rechercher les conversations ;
- lire une conversation et ses messages ;
- envoyer un nouveau message ;
- renommer une conversation ;
- supprimer une conversation ;
- modifier un message utilisateur ;
- régénérer une réponse ;
- réessayer une génération échouée.

Les noms exacts des routes peuvent respecter l’architecture existante, mais doivent être cohérents, documentés et testés.

Utilise des codes HTTP explicites, notamment lorsque pertinent :

- `400` ou `422` pour les données invalides ;
- `404` pour une conversation ou un message absent ;
- `409` pour une révision périmée ou une génération concurrente ;
- `503` lorsque le cœur ou le modèle n’est pas disponible ;
- une erreur serveur propre pour les problèmes inattendus.

## 8C.4 Sélection de l’historique

Le backend doit sélectionner uniquement ce qui entre dans le budget actif.

Règles :

- commencer par les échanges les plus récents ;
- préserver l’ordre chronologique final ;
- ne pas envoyer une moitié d’ancienne paire ;
- exclure les questions en échec qui n’ont pas encore de réponse réussie, sauf lorsqu’elles constituent précisément la question à réessayer ;
- inclure la nouvelle question ;
- réserver la place à la réponse ;
- ne jamais dépasser le contexte actif ;
- conserver malgré tout la totalité des anciens messages dans SQLite.

Le backend doit être la seule autorité responsable de cette réduction.

## 8C.5 Concurrence et révisions

Ajoute un contrôle de concurrence robuste.

Chaque conversation doit posséder une révision croissante.

Toute mutation d’une conversation existante doit vérifier une `expected_revision` ou un mécanisme équivalent.

Si deux onglets possèdent la révision 5 et que le premier modifie la conversation :

- la conversation passe à la révision 6 ;
- le second onglet ne doit pas écraser silencieusement la nouvelle version ;
- sa mutation doit recevoir une erreur `409` ;
- l’interface doit recharger ou proposer clairement l’état actualisé.

Bloque également deux générations simultanées dans la même conversation.

Utilise :

- un verrou applicatif par conversation ;
- des transactions SQLite ;
- une comparaison atomique de la révision ;
- ou une combinaison équivalente robuste.

Ne garde pas une transaction SQLite ouverte pendant toute la génération du modèle.

Workflow recommandé :

1. verrouiller logiquement la conversation ;
2. transaction courte pour valider et enregistrer la question ;
3. fermer la transaction ;
4. générer tout en gardant le verrou logique de la conversation ;
5. transaction courte pour enregistrer le résultat ou l’échec ;
6. libérer le verrou.

## 8C.6 Redémarrage complet

Après arrêt complet de Léa puis redémarrage :

- les conversations doivent toujours apparaître ;
- leurs titres doivent être conservés ;
- les messages doivent être restaurés ;
- les états d’échec doivent être restaurés ;
- la conversation doit pouvoir continuer ;
- aucun ancien message ne doit dépendre de l’ancien état React ;
- aucune donnée ne doit dépendre de `localStorage`, `sessionStorage` ou IndexedDB.

Le frontend peut utiliser l’URL pour identifier la conversation active, par exemple un paramètre ou une route contenant son identifiant.

---

# 9. Étape 8D — Gestion fonctionnelle des conversations

Ajoute les fonctions suivantes sans refonte CSS.

## 8D.1 Nouvelle conversation

Le bouton « Nouvelle conversation » doit :

- vider la vue active ;
- préparer une nouvelle conversation ;
- ne pas supprimer les anciennes conversations ;
- ne pas immédiatement remplir la base d’une conversation vide inutile.

Une conversation vide ne doit pas encombrer la liste.

La solution recommandée est une création différée :

- l’interface passe en mode nouvelle conversation ;
- la ligne SQLite est créée seulement au premier message valide.

## 8D.2 Liste des conversations

Afficher une liste locale des conversations contenant au minimum :

- le titre ;
- une indication raisonnable de dernière activité ;
- la conversation active ;
- un état de chargement ;
- un état vide ;
- les conversations triées de façon cohérente, idéalement par dernière modification décroissante.

L’ouverture d’une conversation doit charger son contenu depuis FastAPI et SQLite.

## 8D.3 Restauration après actualisation

Lorsqu’une conversation est ouverte puis que la page est actualisée :

- elle doit être restaurée depuis le backend ;
- les messages doivent réapparaître ;
- aucun historique ne doit dépendre seulement de la RAM ;
- le frontend ne doit pas renvoyer un ancien historique local comme vérité.

Utilise l’URL ou une autre méthode non persistante côté navigateur pour retrouver la conversation active.

## 8D.4 Titres

Implémente :

- titre automatique à la première question ;
- renommage manuel ;
- conservation du titre manuel ;
- validation d’un titre vide ;
- longueur raisonnable ;
- caractères spéciaux correctement affichés ;
- absence de HTML interprété ;
- absence de `/no_think` et de pensée interne.

## 8D.5 Recherche locale

Ajoute une recherche locale parmi les conversations.

Elle peut rechercher :

- le titre ;
- éventuellement le contenu des messages, si cela reste simple et performant.

Elle doit utiliser SQLite ou les données locales chargées depuis SQLite.

Ne mets pas en place :

- RAG ;
- embeddings ;
- moteur vectoriel ;
- service externe.

La recherche doit gérer correctement :

- majuscules/minuscules ;
- espaces ;
- aucun résultat ;
- caractères spéciaux ;
- requêtes SQL malveillantes grâce aux paramètres SQL.

## 8D.6 Suppression

La suppression d’une conversation doit :

- demander une confirmation claire ;
- supprimer la conversation ;
- supprimer ses messages par cascade ;
- actualiser immédiatement la liste ;
- actualiser la conversation active si elle a été supprimée ;
- ne laisser aucun message orphelin.

## 8D.7 Copie d’un message

Chaque message doit pouvoir être copié.

La copie doit utiliser le texte visible final :

- sans HTML caché ;
- sans `/no_think` ;
- sans `<think>` ;
- sans métadonnées internes.

Prévois une rétroaction légère de succès ou d’échec, sans refaire le design.

## 8D.8 Échec et nouvelle tentative

Lorsqu’une génération échoue :

- la question reste visible ;
- un indicateur d’échec apparaît ;
- aucune fausse réponse assistant n’apparaît ;
- un bouton « Réessayer » est disponible ;
- le réessai utilise le message réel stocké ;
- le réessai ne crée pas une copie supplémentaire de la question ;
- une réussite ajoute la réponse et remet le tour dans un état terminé.

## 8D.9 États pendant la génération

Pendant une génération :

- bloquer un nouvel envoi dans la même conversation ;
- empêcher les doubles clics ;
- désactiver les mutations destructives incompatibles ;
- afficher un état de chargement raisonnable ;
- permettre aux autres conversations d’être consultées seulement si cela ne crée pas d’incohérence ;
- conserver la protection côté serveur même si la protection frontend est contournée.

---

# 10. Étape 8E — Modification et régénération destructives

Le système ne doit créer ni branche ni variante.

Exemple initial :

```text
Q1
R1
Q2
R2
```

Après modification de `Q1`, l’état intermédiaire doit devenir :

```text
Q1 modifiée
```

Les éléments suivants doivent être supprimés :

```text
R1
Q2
R2
```

Puis le modèle génère :

```text
Q1 modifiée
Nouvelle R1
```

## 8E.1 Modification d’un message utilisateur

Seuls les messages `user` peuvent être modifiés.

Lorsqu’un message utilisateur est modifié :

1. vérifier l’existence du message ;
2. vérifier son appartenance à la conversation ;
3. vérifier son rôle `user` ;
4. vérifier la révision attendue ;
5. vérifier qu’aucune génération incompatible n’est active ;
6. valider le nouveau contenu ;
7. supprimer transactionnellement tous les messages situés après ce message ;
8. remplacer son contenu ;
9. mettre son état en attente ;
10. mettre à jour la conversation et sa révision ;
11. valider définitivement cette modification en base ;
12. générer une nouvelle réponse à partir du nouvel historique ;
13. enregistrer la nouvelle réponse uniquement si elle réussit.

La suppression de la suite et la modification de la question doivent être transactionnelles.

La génération du modèle doit avoir lieu après cette transaction, sans garder la transaction SQLite ouverte.

Si la génération échoue :

- la question modifiée reste enregistrée ;
- les anciens messages supprimés ne réapparaissent pas ;
- la question apparaît comme échouée ;
- elle peut être réessayée ;
- aucune ancienne réponse n’est restaurée automatiquement.

## 8E.2 Régénération d’une réponse

La régénération d’une réponse assistant doit :

1. identifier la question utilisateur associée ;
2. supprimer la réponse ciblée ;
3. supprimer tous les messages placés après cette réponse ;
4. remettre la question associée en attente ;
5. incrémenter la révision ;
6. lancer une nouvelle génération ;
7. enregistrer uniquement la nouvelle réponse réussie.

La régénération ne doit jamais :

- garder l’ancienne réponse comme variante ;
- créer une branche ;
- afficher deux réponses concurrentes ;
- réutiliser une réponse mise en cache ;
- réinjecter des messages déjà supprimés.

Si la régénération échoue :

- la question reste ;
- l’ancienne réponse reste supprimée ;
- la question devient réessayable.

## 8E.3 Suppression physique et ordre

Les messages suivants doivent être réellement supprimés de SQLite.

Après une suppression destructive :

- aucun trou incohérent ne doit casser l’ordre ;
- les positions restantes doivent être cohérentes ;
- les contraintes d’unicité doivent rester valides ;
- la lecture de la conversation doit produire exactement la séquence attendue.

Tu peux conserver les positions existantes ou les recalculer, à condition que l’ordre soit explicite, déterministe et testé.

## 8E.4 Deux onglets et version périmée

Teste réellement ce cas :

1. ouvrir la même conversation dans deux onglets ;
2. les deux possèdent la même révision ;
3. modifier la conversation dans le premier ;
4. essayer ensuite une modification dans le second.

Le second doit recevoir un conflit et ne doit pas écraser la première modification.

L’interface du second onglet doit :

- afficher une erreur compréhensible ;
- recharger la conversation actuelle ;
- ne pas inventer une fusion silencieuse.

## 8E.5 Envois concurrents

Teste deux envois presque simultanés dans la même conversation.

Un seul doit être accepté comme génération active.

Le second doit être :

- bloqué côté frontend ;
- et refusé proprement côté backend si le frontend est contourné.

---

# 11. Sécurité et invariants à préserver

Pendant toute l’étape :

- conserver Vite sur `127.0.0.1` ;
- conserver les ports locaux attendus ;
- conserver la vérification d’origine pour les mutations sensibles ;
- ne pas exposer Léa sur le réseau ;
- conserver les protections de PID de 7B ;
- ne pas permettre de tuer un processus arbitraire ;
- ne pas accepter de commande système fournie par le navigateur ;
- utiliser des requêtes SQL paramétrées ;
- empêcher l’injection SQL ;
- empêcher l’interprétation HTML des titres et messages ;
- ne pas faire confiance aux identifiants du client sans vérification ;
- refuser les rôles système envoyés par le client ;
- ne jamais persister le prompt système ;
- ne jamais persister une pensée interne ;
- ne jamais persister `/no_think` ;
- ne pas envoyer la totalité de la base au modèle ;
- ne pas utiliser de service cloud ;
- ne pas ajouter de télémétrie ;
- ne pas ajouter de compte utilisateur ou d’authentification non demandée ;
- ne pas modifier ou remplacer le fichier du modèle.

Vérifie à la fin que le modèle utilisé est toujours le bon fichier.

---

# 12. Étape 8F — Tests complets

Tu dois écrire et exécuter les tests nécessaires.

Ne considère pas l’étape terminée simplement parce que le build réussit.

Lorsqu’un test échoue :

1. trouve la cause ;
2. corrige le code ;
3. relance le test ;
4. relance les tests connexes ;
5. continue jusqu’à obtenir un état stable.

## 8F.1 Tests SQLite

Teste au minimum :

- création d’une base vide ;
- création automatique du dossier ;
- application de toutes les migrations ;
- seconde exécution idempotente ;
- version de schéma ;
- rejet d’une version future inconnue ;
- clés étrangères actives ;
- mode WAL actif ;
- cascade lors de la suppression d’une conversation ;
- ordre des messages ;
- unicité de l’ordre ;
- rôles autorisés ;
- rejet du rôle système ;
- états autorisés ;
- titre automatique ;
- titre manuel conservé ;
- révision croissante ;
- transaction de modification destructive ;
- transaction de régénération destructive ;
- récupération des éléments restés en attente après interruption ;
- base temporaire fournie par configuration ;
- absence d’utilisation accidentelle de la vraie base pendant les tests.

## 8F.2 Tests de migrations

Teste :

- migration depuis une base vide ;
- migration rejouée sans duplication ;
- erreur pendant une migration et rollback approprié ;
- base partiellement migrée simulée si pertinent ;
- intégrité après migration ;
- index créés ;
- contraintes créées.

## 8F.3 Tests API FastAPI

Teste au minimum :

- nouvelle conversation au premier message ;
- liste des conversations ;
- lecture d’une conversation ;
- recherche ;
- renommage ;
- suppression ;
- envoi d’un message ;
- réponse réussie ;
- réponse échouée ;
- réessai ;
- modification d’un message utilisateur ;
- refus de modification d’un message assistant ;
- régénération ;
- suppression de toute la suite ;
- révision périmée ;
- deux requêtes concurrentes ;
- conversation absente ;
- message absent ;
- message vide ;
- caractère NUL ;
- contenu trop grand ;
- rôle système ;
- champs inconnus ;
- historique injecté par le client ;
- cœur indisponible ;
- modèle indisponible ;
- réponse vide après filtrage ;
- réponse contenant `<think>` ;
- réponse contenant uniquement `</think>` ;
- absence de `/no_think` dans les réponses API et dans SQLite.

Utilise un modèle simulé pour les tests unitaires rapides, puis le véritable modèle pour les tests d’intégration finaux.

## 8F.4 Tests du budget de contexte

Teste plusieurs cas :

- historique court ;
- historique exactement sous la limite ;
- historique dépassant légèrement la limite ;
- historique très long ;
- ancien échange retiré ;
- paires complètes conservées ;
- ordre chronologique final correct ;
- question actuelle toujours conservée ;
- question actuelle seule trop grande ;
- réserve de réponse respectée ;
- contexte choisi à 8 192 ou à la meilleure valeur de secours validée ;
- aucune ancienne donnée supprimée de SQLite uniquement parce qu’elle est hors contexte.

Crée une conversation synthétique approchant réellement la limite retenue.

Ne te contente pas d’un petit dialogue de quelques phrases.

## 8F.5 Tests de redémarrage

Teste réellement :

1. démarrer Léa ;
2. créer une conversation ;
3. envoyer plusieurs messages ;
4. arrêter complètement le modèle et le backend ;
5. vérifier que les processus et ports sont libérés ;
6. redémarrer ;
7. recharger la conversation depuis SQLite ;
8. poursuivre la conversation ;
9. vérifier que le modèle utilise l’historique chargé par le backend.

## 8F.6 Tests d’interruption et reprise

Simule au minimum une interruption pendant une génération :

- arrêt du modèle ;
- arrêt du backend ;
- ou interruption contrôlée de la requête.

Après redémarrage :

- la question ne doit pas disparaître ;
- aucun faux assistant ne doit apparaître ;
- l’état ne doit pas rester éternellement en attente ;
- le bouton « Réessayer » doit fonctionner ;
- la nouvelle réponse doit être enregistrée correctement.

## 8F.7 Vérification directe de la base

Inspecte directement la base SQLite avec des requêtes.

Vérifie notamment :

- conversations présentes ;
- ordre des messages ;
- révisions ;
- états ;
- cascade ;
- absence de messages supprimés après modification destructive ;
- absence de réponses fictives ;
- absence de rôle système ;
- absence de `/no_think` ;
- absence de `<think>` ;
- absence de `</think>` isolé ;
- absence de raisonnement brut.

## 8F.8 Build et validations techniques

Exécute au minimum les équivalents pertinents de :

```text
npm run build
python -m compileall backend\app
tests Python
tests frontend
analyse syntaxique PowerShell
git diff --check
```

Ajoute les commandes de lint ou de type-check existantes dans le projet.

Ne masque pas une erreur avec une désactivation globale d’un test ou d’un linter.

---

# 13. Tests obligatoires avec le véritable Microsoft Edge Stable

Tu dois utiliser le véritable **Microsoft Edge Stable**, pas seulement Chromium générique.

## 13.1 Localisation d’Edge

Localise proprement Edge Stable, par exemple via :

- les chemins standards ;
- le registre Windows ;
- les outils déjà présents.

Vérifie qu’il s’agit bien de Microsoft Edge Stable.

## 13.2 Profil isolé

Tous les tests automatisés Edge doivent utiliser :

- un dossier de profil temporaire ;
- un `user-data-dir` isolé ;
- aucune fenêtre Edge personnelle ;
- aucune donnée personnelle ;
- aucune extension personnelle ;
- une base SQLite temporaire réservée aux tests.

Nettoie ensuite :

- le profil de test ;
- la base de test ;
- les fichiers WAL/SHM de test ;
- les captures ou traces temporaires devenues inutiles ;
- les processus Edge de test.

Ne ferme pas une fenêtre Edge personnelle qui ne t’appartient pas.

## 13.3 Automatisation

Utilise l’outil déjà présent dans le projet si possible.

Si aucun outil d’automatisation compatible n’existe, tu es autorisé à ajouter une dépendance de développement ou de test réellement nécessaire, par exemple une solution capable de lancer le canal Microsoft Edge.

Toute dépendance ajoutée doit :

- être justifiée ;
- être réellement utilisée ;
- être inscrite proprement dans les fichiers du projet ;
- être mentionnée dans le compte rendu final ;
- ne pas être ajoutée uniquement pour un test jetable si une solution locale existante suffit.

## 13.4 Parcours Edge visible

Effectue au moins un parcours avec Edge visible lorsque l’environnement le permet.

Si un affichage visible est techniquement impossible dans l’environnement d’exécution :

- exécute le parcours automatisé avec Edge Stable en mode disponible ;
- conserve les preuves techniques ;
- explique exactement la limitation dans le rapport final.

Ne te contente pas d’affirmer qu’Edge fonctionnerait.

## 13.5 Scénario Edge complet

Le scénario doit vérifier au minimum :

1. démarrage de Vite ;
2. ouverture de Léa dans Microsoft Edge Stable ;
3. vérification que le cœur est initialement arrêté si c’est l’état attendu ;
4. démarrage du cœur depuis les vrais boutons de l’interface ;
5. attente de l’état prêt ;
6. création d’une conversation ;
7. envoi de plusieurs messages ;
8. vérification que le modèle garde le contexte ;
9. actualisation complète de la page ;
10. restauration de la conversation ;
11. arrêt du cœur depuis l’interface ;
12. vérification que Vite reste ouvert ;
13. vérification que les ports du backend et du modèle sont libérés ;
14. redémarrage du cœur ;
15. restauration de la conversation après redémarrage complet ;
16. modification de la première question ;
17. vérification que toutes les réponses et questions suivantes disparaissent ;
18. vérification directe dans SQLite que ces messages ont été supprimés ;
19. génération de la nouvelle réponse ;
20. régénération d’une réponse ;
21. simulation ou déclenchement d’un échec ;
22. affichage de l’indicateur d’échec ;
23. utilisation du bouton « Réessayer » ;
24. copie d’un message ;
25. renommage de la conversation ;
26. recherche de la conversation ;
27. ouverture depuis les résultats ;
28. ouverture de la même conversation dans deux onglets ;
29. test d’une révision périmée ;
30. suppression avec confirmation ;
31. vérification qu’une conversation vide n’encombre pas la liste ;
32. vérification qu’aucun `/no_think` n’est visible ;
33. vérification qu’aucun `<think>` n’est visible ;
34. vérification qu’aucun raisonnement n’est présent dans la base.

## 13.6 Console et réseau

Pendant les tests Edge, inspecte et conserve les résultats concernant :

- erreurs JavaScript non gérées ;
- erreurs React ;
- requêtes réseau échouées ;
- codes HTTP inattendus ;
- réponses `409` attendues ;
- payloads envoyés ;
- absence d’historique complet envoyé par le frontend ;
- absence de rôle système ;
- absence de `/no_think` dans les requêtes frontend ;
- absence de données internes dans les réponses ;
- absence d’erreur CORS ou d’origine ;
- absence de boucle de requêtes ;
- absence de double envoi.

Le parcours final doit se terminer sans erreur JavaScript non expliquée.

---

# 14. Tests réels du modèle et du GPU

Pour la configuration finale :

- utilise le vrai modèle Général ;
- confirme le nom et le chemin du modèle ;
- confirme son SHA-256 ou vérifie qu’il n’a pas changé ;
- confirme le contexte actif ;
- confirme l’absence du budget de raisonnement ;
- confirme l’injection interne de `/no_think` ;
- confirme le filtrage de pensée ;
- confirme le PID ;
- confirme que le même PID reste actif pendant plusieurs messages ;
- confirme l’utilisation GPU ;
- confirme l’absence de fallback CPU inattendu ;
- confirme l’absence de rechargement du modèle ;
- mesure la VRAM avant, pendant et après ;
- mesure les performances comparatives ;
- teste une conversation proche de la fenêtre retenue.

Utilise des prompts déterministes ou suffisamment courts pour les mesures comparatives.

Évite de comparer deux prompts totalement différents.

---

# 15. Nettoyage obligatoire après les tests

Lorsque tous les tests sont terminés :

1. arrête le cœur ;
2. arrête le backend ;
3. arrête le modèle ;
4. arrête Vite ;
5. ferme uniquement les processus Edge créés pour les tests ;
6. supprime le profil Edge temporaire ;
7. supprime les bases SQLite temporaires ;
8. supprime les WAL/SHM temporaires ;
9. supprime les scripts jetables non utiles au projet ;
10. vérifie les ports :
    - 5173 ;
    - 8000 ;
    - 8080 ;
11. vérifie qu’aucun `llama-server` de Léa ne reste actif ;
12. vérifie que les processus du projet sont arrêtés ;
13. vérifie le retour de la VRAM vers son état de repos raisonnable ;
14. ne supprime pas la vraie base de production ;
15. ne supprime pas les migrations ou tests utiles ;
16. ne fais aucun commit.

L’état final attendu est :

```text
Modèle    : arrêté
Backend   : arrêté
Frontend  : arrêté
Edge test : arrêté
Ports     : libres
VRAM      : revenue au repos raisonnable
```

---

# 16. Documentation de fin d’étape

Seulement après réussite des tests :

## Mettre à jour `TODO.md`

Indique clairement que l’étape 8 comprend maintenant :

- mode Général permanent sans réflexion ;
- injection interne de `/no_think` ;
- contexte étendu à la plus grande valeur stable validée ;
- SQLite locale ;
- conversations persistantes ;
- restauration après redémarrage ;
- liste et recherche des conversations ;
- renommage et suppression ;
- échecs et réessais ;
- modification destructive ;
- régénération destructive ;
- contrôle de concurrence ;
- tests Microsoft Edge Stable.

Ne marque pas un élément comme terminé s’il n’a pas réellement été validé.

## Mettre à jour `AGENTS.md`

Le document indique encore une étape ancienne.

Mets-le à jour pour refléter :

- l’état réel du projet ;
- les commandes actuelles ;
- la base SQLite ;
- les règles de test ;
- les nouvelles responsabilités du backend ;
- la valeur finale du contexte ;
- l’interdiction de persister `/no_think` ou les pensées.

## Mettre à jour `CHANGELOG.md`

Ajoute une entrée précise pour l’étape 8.

Évite une description vague.

## Mettre à jour les autres documents concernés

Selon l’architecture réelle, mets à jour :

- README ;
- documentation des commandes ;
- documentation de l’API ;
- documentation des variables d’environnement ;
- documentation de la base et des migrations ;
- commentaires devenus incorrects.

## Refonte visuelle

Indique simplement que la refonte visuelle est reportée.

Ne lui attribue pas arbitrairement une nouvelle étape numérotée.

---

# 17. Critères globaux de réussite

L’étape 8 est terminée seulement si :

- le modèle Général est toujours en mode `/no_think` ;
- aucun raisonnement interne n’est visible ;
- aucun raisonnement interne n’est stocké ;
- la meilleure fenêtre stable parmi 8 192, 7 168 et 6 144 a été validée ;
- le modèle ne se recharge pas entre les messages ;
- les couches restent sur CUDA comme attendu ;
- FastAPI est la source officielle de l’historique ;
- SQLite restaure les conversations après redémarrage ;
- l’ancien historique complet n’est plus fourni par le frontend ;
- les conversations peuvent être créées, ouvertes, renommées, recherchées et supprimées ;
- une conversation vide n’encombre pas la liste ;
- les erreurs restent réessayables ;
- les modifications suppriment toute la suite ;
- les régénérations suppriment toute la suite ;
- aucun système de branche n’existe ;
- les révisions périmées sont refusées ;
- les générations concurrentes sont bloquées ;
- la sécurité locale de 7B reste fonctionnelle ;
- les tests unitaires réussissent ;
- les tests API réussissent ;
- les tests de migrations réussissent ;
- le build frontend réussit ;
- l’analyse PowerShell réussit ;
- les tests réels avec Microsoft Edge Stable réussissent ;
- la console Edge ne contient pas d’erreur non expliquée ;
- la base ne contient ni `/no_think`, ni `<think>`, ni rôle système ;
- aucune refonte CSS n’a été effectuée ;
- aucun commit n’a été créé ;
- tous les processus sont arrêtés à la fin.

---

# 18. Compte rendu final obligatoire

Ne fournis ton compte rendu qu’une fois le travail terminé.

Le compte rendu final doit contenir exactement les catégories suivantes.

## Verdict général

Indique :

```text
Étape 8 : réussie
```

ou un verdict honnête et précis si un blocage matériel réel reste présent après toutes les tentatives.

## Verdict par sous-étape

Présente un tableau pour :

- 8A ;
- 8B ;
- 8C ;
- 8D ;
- 8E ;
- 8F.

## Configuration finale du modèle

Indique :

- modèle ;
- hash ;
- contexte final choisi ;
- paramètres de lancement pertinents ;
- absence du budget de raisonnement ;
- fonctionnement de `/no_think` ;
- PID stable ;
- GPU ;
- VRAM ;
- comparaison des performances 4 096 contre valeur finale.

## Base SQLite

Indique :

- chemin par défaut ;
- variable de configuration ;
- tables ;
- version du schéma ;
- migrations ;
- mode WAL ;
- clés étrangères ;
- stratégie de révision ;
- stratégie des états ;
- récupération des générations interrompues.

## Backend et API

Indique :

- routes ajoutées ou modifiées ;
- validation ;
- chargement de l’historique ;
- réduction du contexte ;
- concurrence ;
- erreurs et réessais ;
- modification et régénération.

## Frontend

Indique :

- nouvelles fonctions ;
- absence de refonte CSS ;
- restauration ;
- recherche ;
- renommage ;
- suppression ;
- copie ;
- échec ;
- réessai ;
- modification ;
- régénération.

## Tests

Liste toutes les commandes exécutées et leurs résultats.

Sépare :

- tests unitaires ;
- migrations ;
- API ;
- contexte ;
- modèle réel ;
- GPU ;
- build ;
- PowerShell ;
- tests Edge ;
- inspection directe de SQLite ;
- redémarrage ;
- interruption ;
- concurrence.

## Tests Microsoft Edge

Indique :

- version ou chemin d’Edge Stable ;
- mode visible ou limitation exacte ;
- profil isolé ;
- base isolée ;
- parcours effectué ;
- console JavaScript ;
- réseau ;
- résultat du test à deux onglets.

## Fichiers modifiés

Liste les fichiers créés, modifiés et supprimés avec une description courte.

## Vérification de la base

Confirme explicitement l’absence de :

- `/no_think` ;
- `<think>` ;
- `</think>` isolé ;
- rôle système ;
- réponse fictive ;
- messages qui auraient dû être supprimés.

## État final

Indique :

- état du modèle ;
- état du backend ;
- état du frontend ;
- état d’Edge ;
- ports ;
- processus ;
- VRAM ;
- présence de la vraie base ;
- suppression des bases temporaires ;
- résultat de `git status` ;
- confirmation qu’aucun commit n’a été créé.

Tu ne dois pas faire de commit, même si tous les tests réussissent.