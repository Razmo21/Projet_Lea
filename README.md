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

L’étape 11 sépare désormais les profils, les modèles remplaçables et le moteur
d’inférence. Les deux Qwen actuels, les données et le parcours OpenHands sont
conservés. L’étape 11 a été validée manuellement par l’utilisateur avant
l’autorisation de l’étape 12.

L’étape 12 ajoute le centre de paramètres de Léa, utilisable sans modèle ni
FastAPI chargés, et a été validée manuellement. L’étape 13 fiabilise les runs
interrompus et ajoute une surveillance légère avec diagramme facultatif.
Elle est validée manuellement et finalisée, confirmation apportée par le prompt 14.
L’étape 14 ajoute le microphone, la dictée locale et la conversation vocale tour
par tour. Elle est terminée et validée manuellement ; ses essais et limites sont
consignés dans `docs/ETAPE_14_VALIDATION.md`. L’installation avait été autorisée
explicitement dans la limite de 10 Go.
L’étape 15 ajoute le profil Vétérinaire local et compare les contrats de réponse
avant de conserver leurs optimisations. L'intégration technique est prête ; ses
limites scientifiques et la procédure de validation manuelle sont consignées
dans `docs/ETAPE_15_VALIDATION.md`.

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
11. Architecture indépendante des modèles — terminée.
12. Centre de paramètres de Léa — terminé.
13. Programmation avancée — terminée.
14. Microphone et conversation vocale — terminée.
15. Profil Vétérinaire et optimisation des contrats — validation manuelle requise.

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

## Microphone et conversation vocale — étape 14

Pour les deux modes vocaux, ouvre `http://127.0.0.1:5173` dans une **fenêtre
Microsoft Edge externe**, pas dans le navigateur intégré de VS Code. Ce dernier
peut enregistrer du WebM/Opus tout en échouant à le décoder (`Unable to decode
audio data`), avant tout envoi à Whisper. Ce défaut a été reproduit avec VS Code
1.140.0 sur des données synthétiques identiques décodées correctement dans Edge.
Copier l’adresse dans la barre d’Edge évite l’ouverture intégrée des liens localhost.

Deux commandes distinctes se trouvent sous la zone de question :

- **Dicter au microphone** : premier clic pour enregistrer, second pour
  transcrire localement. Le texte s’ajoute au brouillon sans effacer les
  modifications ; relire puis cliquer soi-même sur Envoyer ou Lancer le run.
  Cette dictée fonctionne avec Vite seul, même si l’IA est arrêtée.
- **Conversation vocale** : vue dédiée masquant les échanges écrits. Cliquer
  sur Parler à Léa, puis Terminer et envoyer ; Léa transcrit, traite la demande
  avec le profil actif, conserve le texte et lit la réponse. Aucun microphone
  ne se rallume automatiquement. Arrêter la lecture coupe le son, sans effacer
  la réponse. Retour aux conversations ferme le microphone et l’audio.

Le mode vocal exige un profil prêt, mais ne le démarre jamais implicitement.
En Programmation, choisir d’abord un projet ; les demandes passent uniquement
par OpenHands. Le résultat impose un retour explicite au diff pour accepter
ou restaurer, jamais une décision automatique. Fermer l’audio ne signifie pas
annuler un run déjà lancé : son bouton d’annulation reste dans l’interface classique.

Paramètres conserve dans SQLite le microphone (ou défaut système), la langue
français/anglais, la lecture activée, la voix installée, le volume (0–100 %)
et la vitesse SIWIS (0,75–1,5×). La voix naturelle de Léa utilise honnêtement
sa vitesse native fixe à 1× ; le curseur est désactivé pour cette voix sans
effacer la valeur SIWIS mémorisée. « Autoriser et lister les microphones » demande
l’autorisation puis libère immédiatement le périphérique. Aucun faux réglage
de sensibilité. Un périphérique mémorisé mais absent est signalé.

Capture limitée à 120 secondes : le dépassement annule, sans envoi. Les sons
restent en RAM et ne sont pas conservés. Whisper Small Q5_1, Pocket TTS et
Piper/SIWIS fonctionnent en CPU, dans un environnement séparé ; aucun changement des Qwen,
de leur contexte ou du backend Python. Pas d’API distante, VAD, écoute permanente,
vision ou téléchargement pendant l’utilisation normale. La lecture des blocs
de code ou réponses très longues est annoncée comme partielle ; le texte
complet reste dans l’historique.

En cas d’erreur de capture, la console locale (`F12`) contient un diagnostic
`[Lea microphone]` : MIME réel, tailles des morceaux, durée écoulée, finalisation,
conteneur et étape de décodage/conversion. Aucun son, transcription ou identifiant
de microphone n’y est journalisé ; ces diagnostics ne sont pas envoyés au serveur.

Installation administrative explicite (Internet nécessaire uniquement ici) :

```powershell
.\tools\voice\install.ps1
```

Les versions CPU sont figées dans `tools/voice/requirements.txt`. Binaires dans
`runtime/voice/`, poids dans `models/voice/`, paramètres techniques dans l’unique
`config/models.json` ; ces gros fichiers sont ignorés par Git. Le sélecteur propose
« Léa — Voix naturelle française » (Pocket TTS `french`, choix par défaut) et
« SIWIS — Voix classique » (Piper). Whisper et Pocket TTS : MIT pour le code ;
poids Pocket TTS : CC-BY 4.0 et conditions Kyutai ; Piper : GPL-3.0-or-later ;
dépôt des voix Piper : MIT, corpus SIWIS : CC-BY 4.0.
Provenance, attribution, mesures et procédure physique :
[`docs/ETAPE_14_VALIDATION.md`](docs/ETAPE_14_VALIDATION.md).

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
une directive de raisonnement ajoutée par l’interface. Le backend relit uniquement les messages validés dans SQLite,
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
1 024 tokens pour la génération (réflexion éventuelle comprise) et 1 024 pour les instructions et le
template, puis applique une borne conservatrice d’un octet UTF-8 par token.
La directive `/no_think` (Low) ou `/think` (High) existe uniquement dans la copie interne envoyée au
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

La suppression d’une conversation est une suppression SQLite réelle et
transactionnelle, jamais un masquage frontend. La clé étrangère efface ses
messages et ses liens `memory_sources`; les `agent_runs` indépendants conservent
leur audit avec un `conversation_id` mis à `NULL`, ainsi que leurs checkpoints.
Chaque connexion active les clés étrangères et `secure_delete`. Ce dernier
limite la conservation de contenu dans les cellules libérées, mais ne constitue
pas une promesse d’effacement forensique du support, des sauvegardes ou des blocs SSD.
Une maintenance hors service peut en plus effectuer un checkpoint WAL et `VACUUM`.

## Profils locaux et projets de programmation

Le registre `config/models.json` décrit Général, Programmation et Vétérinaire,
leurs modèles, prompts, capacités, moteurs et limites : il est la source de
vérité de cette configuration. Général reste toujours le profil du prochain
démarrage complet. L'interface peut changer de profil et poursuivre la même
conversation ; chaque réponse assistant garde le profil et l'alias du modèle
qui l'a produite. Un seul modèle est chargé à la fois.

La configuration Programmation validée est strictement locale :

- `Qwen2.5-Coder-7B-Instruct Q6_K` ;
- fenêtre de contexte de 22 000 tokens et un seul slot ;
- `llama.cpp` b10516 (`b95502ba9`) ;
- OpenHands SDK / Agent Server 1.43.1 minimal comme moteur agentique.

Agent Canvas peut rester un outil administratif, mais il n’est pas requis pour
un run. Docker Desktop doit actuellement être démarré manuellement : Léa ne le
démarre pas elle-même et signale clairement son indisponibilité. Léa n’ouvre pas
non plus l’interface OpenHands. Le conteneur Agent Server est créé uniquement
au lancement explicite d’un run, jamais à l’activation du profil ni après sa fin.
Aucun modèle
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
d'isolation du noyau Windows. Le durcissement réseau Docker avancé reste reporté
aux étapes ultérieures ; il ne fait pas partie de l’étape 11. Ne sélectionne
pour exécution que des projets dont tu acceptes le code.

Limitation connue du modèle actuel :

> Qwen2.5-Coder-7B peut échouer sur des tâches agentiques multi-fichiers longues lorsque file_editor exige des remplacements textuels exacts. Léa détecte ces boucles, refuse les mutations invalides, valide les changements par des tests et peut restaurer le checkpoint.

`Lea_FinalValidation_Test` reste un benchmark difficile conservé pour comparer
un futur GLM-5.3-Flash avec Qwen ; sa réussite complète avec Qwen n'est pas un
critère de validation de cette étape.

### Profil Vétérinaire — étape 15

Le profil Vétérinaire utilise localement `Qwen3.5-9B Q4_K_M`, servi par la même
installation llama.cpp que Général. Le fichier est
`models/veterinary/Qwen3.5-9B-Q4_K_M.gguf`; le registre en vérifie la taille et
le SHA-256 avant tout lancement. Sa fenêtre Léa est de 16 384 tokens, avec un
seul slot, KV Q8_0 et une sortie maximale de 4 096 tokens. Il n'a ni outil, ni
workspace, ni Web, ni vision et ne démarre jamais Docker.

Ses deux vocations sont de même importance : apprentissage vétérinaire et
raisonnement clinique théorique. Le contrat demande l'espèce, distingue données,
hypothèses et informations manquantes, signale les urgences et refuse d'inventer
une source, une maladie ou une posologie. Il ne remplace pas un vétérinaire ni
une référence scientifique actualisée. Les erreurs importantes observées lors
des essais — ambiguïté de « abattue », surinterprétation d'une kaliémie,
confusion entre classes d'opioïdes et catégorie inventée pour un nom fictif —
sont détaillées dans le rapport de validation plutôt que masquées par le prompt.

Dans Paramètres, Vétérinaire commence en **High** et peut être réglé sur **Low**.
Le choix est indépendant de Général et s'applique à la requête suivante. Il
pilote réellement `enable_thinking` dans le template natif Qwen3.5 ; la pensée
interne n'est ni affichée ni persistée. Les deux voix locales, la dictée,
l'historique, la mémoire explicite et le diagramme de ressources utilisent les
mêmes chemins génériques que les autres profils.

## Architecture indépendante des modèles

Léa reste l’application et l’orchestrateur. Les conversations, la mémoire,
les permissions et les checkpoints n’appartiennent jamais au modèle.

| Élément | Responsabilité | Source |
| --- | --- | --- |
| Profil | Comportement, prompts, outils, permissions, budgets | `profiles` |
| Modèle | Poids, capacités déclarées, contexte, template, paramètres moteur | `models` |
| Association | Référence `profiles[].model_id` vers `models[].id` | `config/models.json`, schéma 3 |
| Moteur | Arguments, endpoints, protocole d’inférence et readiness | `backend/app/inference.py` |
| Cycle de vie | Processus identifiés, arrêt sûr, commutation et retour après échec | Contrôleurs et lanceurs existants |

Les associations livrées sont `general` → `qwen-general`
(`Huihui-Qwen3-4B-abliterated-v2 Q4_K_M`, 8 192 tokens), `development` →
`qwen-coder` (`Qwen2.5-Coder-7B-Instruct Q6_K`, 22 000 tokens) et `veterinary` →
`qwen-veterinary` (`Qwen3.5-9B Q4_K_M`, 16 384 tokens). Le seul moteur de
modèle implémenté est `llama.cpp`, avec l’installation b10516 existante ;
OpenHands orchestre uniquement le profil Programmation.

Le chargeur `backend/app/model_registry.py` valide la même configuration pour
FastAPI, OpenHands et les lanceurs. `tools/model_config.py` transmet aux scripts
PowerShell une projection temporaire du registre et les arguments calculés par
l’adaptateur : ce n’est pas une seconde configuration. Le modèle possède ses
options `append_no_think`, `reasoning_control`, `stop_sequences` et son éventuel template ; les
contrats de profil et le filtrage des réponses restent indépendants de lui.

### Remplacer un modèle par configuration

1. Terminer ou annuler le run actif, puis accepter ou restaurer ses changements.
   Exécuter `.\lea.ps1 stop` avant de modifier le registre et conserver une copie
   de `config/models.json` pour revenir à la configuration validée.
2. Placer un GGUF déjà disponible et compatible sous `models/`. Son `model_path`
   est relatif à la racine, par exemple `models/general/mon-modele.gguf` : aucun
   chemin absolu, UNC, parent `..` ou échappement par lien n’est autorisé.
3. Ajouter ou modifier une entrée `models` : identifiant unique, nom, moteur
   `llama.cpp`, type `chat`, chemin, taille exacte et SHA-256. Obtenir ces deux
   derniers avec `Get-Item -LiteralPath <fichier>` et
   `Get-FileHash -Algorithm SHA256 -LiteralPath <fichier>` ; écrire le hash en
   minuscules. Ces valeurs ne prouvent pas la qualité du modèle, seulement son
   identité au démarrage.
4. Adapter le contexte et les paramètres `runtime` à ce GGUF : alias unique,
   GPU, caches KV, threads, batches, Jinja, mmap, fit et priorité. Les seuils de
   ressources restent imposés par le profil. Un seul slot est autorisé et
   `fit_context_min_tokens` doit égaler le contexte lorsque `fit` est actif.
   Définir `append_no_think` et les séquences d’arrêt selon le modèle. Laisser
   `reasoning_control` à `none` (défaut) sauf preuve réelle de compatibilité avec
   `think_directives` ou `chat_template_kwargs`. Cette capacité autorise un
   réglage déclaré du profil, pas une permission.
   Un template
   personnalisé doit rester sous `tools/openhands/templates/`, avec son hash ;
   sans template explicite, le moteur utilise celui du GGUF.
5. Modifier uniquement le `model_id` du profil concerné. Général et Vétérinaire
   exigent `chat`; Programmation exige aussi `tool_calling` natif, Jinja et le
   parsing des outils activé.
   L’association doit respecter les budgets du profil et le plancher du
   condenser SDK 1.43.1 (16 384 tokens d’entrée, plus la réponse réservée).
   Ne pas changer les permissions ou les contrats pour rendre un modèle compatible.
6. Vérifier la configuration, puis redémarrer :

   ```powershell
   .\backend\.venv\Scripts\python.exe -B tools/model_config.py
   .\lea.ps1 start
   ```

   La première commande valide le registre, les fichiers requis et les templates,
   mais ne charge pas les poids. Taille et hash complets du GGUF sont contrôlés
   avant son activation. Une erreur n’entraîne aucun fallback silencieux.
7. Tester une conversation, la mémoire et le réglage de raisonnement de chaque
   profil direct concerné ; pour Programmation,
   démarrer Docker manuellement, activer le profil et vérifier un petit run réel,
   son test vert et Accept/Rollback sur un projet de test autorisé. Une capacité
   déclarée dans le JSON n’est pas une preuve de tool calling opérationnel.

Plusieurs profils peuvent référencer une même définition compatible sans partager
leurs permissions. Cela n’autorise ni deux modèles simultanés ni la suppression
des barrières de commutation. La substitution de configuration et le partage
ont été testés avec des fixtures ; aucune inférence avec un troisième GGUF
n’est revendiquée.

Ajouter ultérieurement un autre moteur demandera son adaptateur, sa validation
de configuration, son intégration aux propriétaires de processus et des tests
de lancement/readiness/arrêt. Les contrats de profils, SQLite et les outils
n’ont pas à être reconstruits. Aucun autre moteur, système de plugins, API
d’édition du registre des modèles n’est implémenté. Les préférences de l’étape 12
ne modifient jamais ce registre.

### Vérifications de l’étape 11

Les tests backend couvrent le registre, l’adaptateur, les profils, la mémoire,
les conversations, les sécurités workspace, OpenHands et les checkpoints.
Les transports HTTP et certaines pannes de cycle de vie y sont simulés ; les
tests réels ont utilisé les deux Qwen, llama.cpp et l’Agent Server Docker.
Sur un projet temporaire distinct du dépôt, deux runs ont lu les fichiers,
corrigé une source et passé `python -B -m unittest -v`, avant respectivement un
rollback exact et une acceptation. La persistance a été vérifiée après
redémarrage avec une base isolée ; le SHA-256 de la base utilisateur est resté
identique. Le benchmark difficile n’a pas été relancé.

Commandes de non-régression :

```powershell
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -p 'test_*.py'
npm run test:frontend
npm run build
git diff --check
```

## Paramètres de Léa — étape 12

Le bouton **Paramètres**, à côté du titre Léa, ouvre une page dédiée. Choisir
Low ou High puis **Valider** ; la confirmation apparaît après commit et relecture
de la valeur enregistrée. **Retour aux conversations** préserve le brouillon,
l’historique, le profil et le run courant. Un brouillon de préférence non validé
demande confirmation avant d’être abandonné ; une sauvegarde en cours bloque ce retour.

- Général commence en **Low** : directive interne `/no_think`.
- **High** utilise `/think`, avec le même budget de génération. Les essais réels
  sur le Qwen3 installé montrent une réflexion non vide en High, vide en Low,
  puis une réponse correcte dans les deux cas. Ce sont des directives du modèle,
  pas un paramètre API `reasoning_effort` supporté par le template actuel.
- Le choix s’applique à la **prochaine requête Général**, y compris retry,
  modification et régénération. Aucun redémarrage, changement de modèle ou arrêt
  d’un run en cours. High peut être plus lent et épuiser le budget ; une réponse
  inutilisable reste un échec explicite, sans fallback dissimulé.
- Aucun bloc ni marqueur de réflexion généré n’est affiché ou persisté. Les
  textes saisis par l’utilisateur ne sont pas réécrits en fonction de ce choix.
- Programmation n’affiche **aucun faux contrôle Low/High** : le template
  Qwen2.5-Coder, le moteur servi et le chemin OpenHands actuel ne fournissent pas
  de mécanisme de raisonnement réglable validé. Les outils, tests et checkpoints
  restent identiques ; une stratégie d’agent serait un autre réglage, non implémenté.
- Vétérinaire commence en **High** et utilise le booléen natif
  `chat_template_kwargs.enable_thinking` du template Qwen3.5. Low et High ont été
  distingués sur le vrai moteur ; ce choix est indépendant de Général.

### Persistance et fonctionnement IA arrêtée

`user_preferences`, ajoutée par la migration SQLite 8 dans `data/lea.sqlite3`,
conserve les choix et une révision. La migration 12 ajoute
`veterinary_reasoning` sans modifier `general_reasoning`. Le registre `config/models.json`
reste exclusivement technique : modèles, capacités et profils. Les préférences
n’appartiennent ni à Qwen, ni au navigateur, ni à un fichier JSON concurrent.
La migration 9 ajoute `show_resource_chart`, booléen strict à `false` par défaut.
Une sauvegarde partielle conserve les autres choix et vérifie la même révision.

`npm run dev` suffit pour ouvrir, modifier et relire les paramètres lorsque
FastAPI et les modèles sont arrêtés. Il faut néanmoins Vite, l’environnement
Python **déjà installé** dans `backend/.venv` et l’accès à SQLite. Le contrôleur
Vite lance brièvement `tools/preferences.py` avec l’action fixe `read` ou `save`,
puis le processus se ferme. Aucun nouveau serveur Python, modèle ou Docker ne
démarre. Une page statique `dist/` seule ne fournit pas ce contrôleur local.
`LEA_DB_PATH` doit être défini identiquement avant de lancer Vite et le backend
pour les essais isolés ; le navigateur ne peut pas choisir ce chemin.

Une révision périmée, une valeur inconnue, un JSON invalide, une base illisible
ou une sauvegarde refusée produisent une erreur sans confirmation mensongère.
**Recharger les paramètres** retrouve l’état persistant après un conflit ou une
réponse perdue. Un stockage réellement absent est initialisé en Low ; une valeur
corrompue n’est jamais réinitialisée silencieusement. Si le modèle de remplacement
ne déclare pas la capacité, le contrôle devient indisponible sans supprimer le choix.
Modifier le registre reste une opération administrative exigeant l’arrêt/reprise
documenté plus haut ; aucun réglage utilisateur actuel n’exige de redémarrage.

### Ajouter ultérieurement un paramètre

Ajouter une migration additive et son champ typé/validé dans
`backend/app/preferences.py`, écrire uniquement la colonne concernée, étendre le
contrat de `src/preferences.ts` et ajouter son contrôle dans `src/Settings.tsx`.
Brancher sa consommation au point métier pertinent et documenter son moment
d’application. Les révisions et transactions existantes restent réutilisées.
Tester défaut, aller-retour, refus, concurrence et préservation des autres champs.
Un test de colonne fictive isolée démontre cette préservation ; aucun réglage
futur n’est livré dans l’interface et aucun framework générique n’est ajouté.

### Vérifications de l’étape 12

213 tests backend, 21 tests frontend, build et vérification du diff réussis.
Les tests unitaires/integration utilisent SQLite temporaire, gateways simulés,
processus CLI réels et doubles de transport selon le cas. Edge a réellement
exercé la page IA arrêtée, Low/High, les brouillons, erreurs et conflits,
l’historique et la mémoire après arrêt/reprise des trois services.

Le petit projet autorisé `L:\IA_WORKSPACE\Lea_Stage12_20261016` a produit un run
OpenHands validé, avec test vert, diff source unique et rollback exact depuis
Edge. Une préférence a été sauvegardée pendant ce run sans interrompre ni changer
son modèle. Accept reste couvert par la non-régression automatisée ; il n’a pas
été recliqué dans cet essai. Aucun benchmark long, nouveau modèle ni moteur testé.

Les scénarios réels sont dans `tests/e2e/edge-stage12.mjs` : phases `settings`,
`general`, `errors`, `programming`, `persistence`, `native`, `security`, `visual`.
Ils exigent des services **isolés** et un Edge de test avec CDP loopback 9232
(`LEA_EDGE_CDP_PORT` modifiable). Ne pas les lancer sur la base utilisateur :
ils changent des préférences et créent des conversations de test. `settings`
part de Low et fonctionne sans cœur ; `general` crée la conversation ;
`errors` part de High ; `programming` exige le projet jetable et Programmation
déjà actif ; `persistence` suit un arrêt/reprise complet sur la même base.
`native` exige Général ; `visual` part de la conversation et sauvegarde une
capture dans le répertoire de test existant. Une panne réseau Edge est simulée ;
les conflits HTTP, l’inférence et le run sont réels.

## Programmation avancée — étape 13

Le backend borne aussi le processus SDK (budget du registre + 60 secondes).
Un résultat n’est accepté que pour le bon run, avec fin du processus réussie et
preuves de validation existantes. Les erreurs publiques viennent d’une liste
de diagnostics relus ; les textes bruts d’échec du modèle restent privés.

Après crash, le backend retrouve le run persistant, vérifie puis arrête son
conteneur exact avant de publier `failed` et de figer le diff. Il ne relance
aucun outil. Si Docker est indisponible ou l’identité incertaine, le run reste
non terminal et bloque une nouvelle activité modèle : rétablir Docker, puis
redémarrer Léa. Une annulation explicite peut réessayer l’arrêt d’un run encore
détenu par cette instance, jamais ses mutations. Rollback conserve ses contrôles
de conflit ; Accept exige une validation réussie.

Dans **Paramètres**, cocher **Afficher le diagramme des ressources** puis
**Valider** affiche trois petites barres en bas de la page principale. Le défaut
est masqué, la préférence persiste dans SQLite et fonctionne même IA arrêtée.
Les alertes restent visibles sans diagramme, y compris dans les paramètres.

- Une seule tâche dans FastAPI pour tout profil IA actif, dès le démarrage en
  Général et pendant les commutations, sans base de télémétrie ni service
  supplémentaire. Elle se ferme avec le backend ; l’interface ne sonde plus
  les ressources lorsque Léa est arrêtée. L’API `/api/resources` ne lit qu’un cache.
- RAM disponible Windows (cache récupérable inclus) et CPU entre deux relevés,
  environ toutes les 10 s, via compteurs natifs sans PowerShell/WMI.
- VRAM via `nvidia-smi` installé, environ toutes les 30 s. Modèle actif confirmé
  par son adaptateur, endpoint et alias du registre, sans dépendance à son nom.
  Docker n’est sondé que pour un profil OpenHands (ou son run en récupération),
  avec cache de 30 s ; Agent Server seulement requis pendant un run.
  Un endpoint muet est incertain, pas un PID déclaré mort.
- RAM : WARNING sous 8 Gio, CRITICAL sous 6 Gio, deux relevés et marge de
  remontée de 1 Gio, issus de la politique du profil actif sur ce PC de 32 Go.
  Les politiques actuelles Général/Programmation partagent ces seuils ; un
  autre profil utilise sa propre politique déclarée, sans modifier la collecte.
- CPU : WARNING à partir de 90 % pendant trois intervalles ; retour sous 80 %
  pendant deux. VRAM : WARNING sous 1 Gio sur deux nouveaux relevés, retour
  à partir de 1,25 Gio. Un service indispensable indisponible pendant un run
  produit CRITICAL. Aucun seuil n’arrête un run, un modèle ou Docker.
- Une mesure absente/périmée est indiquée comme indisponible, jamais zéro.
  NVIDIA absent ou multi-GPU : VRAM inconnue ; pas de fausse somme de mémoires.

Lors d’une commutation, un ancien relevé ne peut pas réafficher les alertes de
l’autre profil. Le cache GPU et les compteurs système restent partagés : pas
de boucle supplémentaire. « Votre question » réutilise l’encadré de conversation
existant, avec le même fond, bordure et espacement ; saisie et envoi inchangés.

Lors de la validation initiale en Programmation, sans polling UI : 0,922 s CPU backend sur 35 s
(environ 0,13 % des 20 processeurs logiques), mémoire résidente 61 → 59 Mio.
Cela inclut les sondes de disponibilité ; ce n’est pas le coût total de Docker
ou du modèle. Avec l’interface ouverte : 5,406 s CPU sur 35 s (0,77 % machine),
environ 60 Mio. Les valeurs sont des mesures ponctuelles, pas une garantie.

Le conteneur arrêté d’un run validé est supprimé sans `--force`, sans volume,
après vérification complète d’identité. Les échecs conservent leurs conteneurs
arrêtés et journaux. Aucun prune ni nettoyage global. Les données OpenHands,
checkpoints et historiques sont conservés. Un PID recyclé du lanceur n’est
jamais adopté ni tué ; un port occupé ou une identité illisible reste bloquant.

L’automatisation Edge par l’agent est **reportée avec accord utilisateur** :
les outils actuels ne démontrent pas le blocage de toutes les redirections,
sous-ressources et destinations externes. Edge sert seulement aux tests locaux
pilotés par le développeur, avec profil jetable ; ce n’est pas une isolation
réseau garantie ni une nouvelle permission de l’agent. Aucun pont shell Windows
n’a été ajouté. Docker Desktop reste manuel.

Voir [le rapport de validation](docs/ETAPE_13_VALIDATION.md) pour les commandes,
preuves réelles, simulations, limites et ménage. Le benchmark difficile est conservé.

## Roadmap

Les étapes 11 à 14 sont terminées. L’étape 15 est techniquement prête et attend
la validation manuelle ; elle n'ajoute ni Web ni vision.

- Étape 11 — Architecture indépendante des modèles.
- Étape 12 — Centre de paramètres de Léa.
- Étape 13 — Programmation avancée.
- Étape 14 — Microphone et conversation vocale (terminée et validée manuellement).
- Étape 15 — Vétérinaire et optimisation des contrats (validation manuelle requise).
- Étape 16 — Accès Web (non commencée).
- Étape 17 — Génération d’images.
- Étape 19 — Speech-to-Speech.
- Étape 20 — Refonte visuelle.
- Étape 21 — Mémoire avancée.
- Étape 22 — Fine-tuning optionnel.
- Étape 23 — Sécurité finale.
- Étape 24 — Tests finaux.
- Étape 25 — Logiciel desktop final.

La vision en entrée est suspendue et reportée. Le profil Auxiliaire est supprimé
définitivement de la roadmap.

## Stockage actuel

Projet :
`L:\Projet_Lea`

Workspace des projets de programmation :
`L:\IA_WORKSPACE`

Après la maintenance finale de l’étape 14, ce dossier existe et est vide. Le
profil Programmation affiche alors un catalogue sans projet et attend une
création/sélection explicite ; il ne crée aucun conteneur OpenHands au repos.

Jeux :
`L:\SteamLibrary`

Le dossier SteamLibrary est totalement indépendant du Projet Léa.
