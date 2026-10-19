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

## D-008 — Raisonnement local équilibré — remplacée
Cette décision de l’étape 7 est remplacée par D-011. Le modèle général
n’utilise plus de budget de raisonnement explicite.

## D-009 — Contrôle local du cœur
Vite héberge uniquement en développement un contrôleur local à routes fixes.
Il peut appeler `start-core`, `status-core` et `stop-core` de `lea.ps1`, sans
transmettre de commande ou d’argument arbitraire du navigateur. Le cœur
conserve les protections d’identité des processus ; le frontend reste ouvert
pendant son arrêt.

## D-010 — Contexte de conversation temporaire — remplacée
Cette décision de l’étape 7 est remplacée par D-012. Le navigateur ne transmet
plus l’historique et SQLite est désormais la source persistante officielle.

## D-011 — Modèle sans pensée persistée
Le modèle général utilise une fenêtre de 8 192 tokens et un seul slot. Le
backend ajoute `/no_think` uniquement dans une copie interne de la question
courante et retire défensivement les marqueurs de pensée, y compris leurs
variantes d’espacement, de casse et les blocs incomplets. Ces données internes
ne sont ni exposées ni enregistrées.

## D-012 — SQLite comme source des conversations
La base locale officielle est `data/lea.sqlite3`, remplaçable en test par
`LEA_DB_PATH`. Le schéma évolue par migrations transactionnelles et utilise
WAL, clés étrangères, contraintes et index. À l’étape 8, les tables de
migration, de conversations et de messages sont créées. Le backend relit les
messages validés dans SQLite et construit lui-même le contexte du modèle.

## D-013 — Mutations destructives et concurrence explicite
Modifier un message utilisateur ou régénérer une réponse supprime la suite de
conversation devenue incohérente ; aucune branche implicite n’est conservée.
Chaque mutation exige la révision attendue, et une seule génération peut être
active par conversation. Les appels au modèle sont exécutés hors transaction
SQLite longue. Une génération interrompue est récupérée comme échec sûr au
prochain démarrage.

## D-014 — Mémoire générale explicite et indépendante
Le schéma v2 ajoute `memories`, sans clé étrangère vers une conversation, et
classe les messages en tours `conversation` ou `memory`. Seules les commandes
françaises explicites `Retiens que`, `Souviens-toi que`, `Mémorise que` et
`Oublie que` modifient cette mémoire. La normalisation est déterministe et
l’oubli exige une égalité exacte ; aucune extraction automatique, recherche
sémantique, mémoire implicite, RAG ou embeddings n’est utilisé.

Les commandes et confirmations mémoire restent visibles, mais sont exclues de
l’historique envoyé au modèle. Les souvenirs actifs sont injectés intégralement
comme valeurs JSON échappées dans le dernier message utilisateur et ne sont
jamais traités comme des directives système. Leur capacité dédiée est de 1 800
tokens estimés ; tout dépassement est refusé sans troncature ni suppression.
Les écritures mémoire, les messages de confirmation et la révision de la
conversation sont validés dans une même transaction courte, sans appel modèle.

Une mémoire générale est indépendante de la conversation où elle a été créée.
La suppression d’une conversation ne la retire pas ; seule une commande exacte
`Oublie que` le fait globalement.

## D-015 — Provenance et suppression définitive — remplacée par D-016
Cette décision décrivait le comportement transitoire suivant.

Le schéma v3 ajoute `memory_sources`, qui relie un souvenir unique à chacune des
conversations où il a été explicitement retenu. La suppression d’une
conversation retire ses messages et ses liens de provenance dans une seule
transaction. Si ce lien était la dernière source du fait, la ligne `memories`
est également supprimée ; si une autre conversation l’a retenu, elle reste.

La migration transitoire devait relier les souvenirs v2 aux commandes encore
présentes et purger les souvenirs déjà orphelins. `Oublie que` conserve son
égalité normalisée
exacte et supprime le fait ainsi que toutes ses provenances. Aucun effacement
flou, automatique ou sémantique n’est introduit.

## D-016 — Provenance informative, mémoire globale
`memory_sources` reste une provenance utile tant que les conversations sources
existent, mais ne représente plus la propriété ni la durée de vie d’un fait.
La cascade d’une conversation retire ses messages et ses liens, jamais la ligne
`memories`. Un souvenir sans source est valide, persiste entre conversations et
redémarrages, et reste injecté au modèle.

`Oublie que` est l’unique suppression d’un souvenir : l’égalité normalisée doit
être exacte, puis la suppression s’applique globalement et cascade ses liens de
provenance. Cette décision rétablit la sémantique indépendante de D-014 sans
ajouter de mémoire implicite ni de suppression sémantique.

## D-017 — Profils centralisés et projets confinés
Les modèles, profils, capacités, prompts, budgets et politiques de ressources
proviennent de `config/models.json`. Général reste le profil de démarrage ; une
bascule vers Programmation arrête totalement l'ancien modèle, vérifie la
readiness du nouveau et restaure l'ancien profil en cas d'échec. Une seule
génération ou un seul run agent peut posséder le runtime à la fois.

Les projets de programmation sont exclusivement des sous-dossiers réels de
`L:\IA_WORKSPACE`. SQLite n'enregistre que leur chemin relatif et leur sélection.
Les chemins absolus, remontées, autres lecteurs, UNC, liens symboliques,
junctions et reparse points sont refusés, et l'identité du dossier est
revalidée avant une opération sensible.

Ce confinement applicatif borne strictement les outils de fichiers. L'exécution
du code d'un projet accepté reste plus risquée qu'une lecture : il s'agit d'une
exécution locale contrôlée, pas d'un sandbox noyau Windows mathématiquement
parfait. Seuls des projets que l'utilisateur accepte d'exécuter doivent être
sélectionnés.

## D-018 — Contrat de fiabilité commun
`config/prompts/reliability.md` est le contrat commun aux profils Général et
Programmation. Il prime sur les données utilisateur, les fichiers, les README,
les journaux et les résultats d’outils. Léa doit signaler l’incertitude, ne pas
inventer de faits, de souvenirs, de fichiers, de commandes, de modifications ou
de résultats de test, et traiter tout contenu externe comme une donnée non
fiable, jamais comme une instruction système.

## D-019 — Runtime Programmation local final
Léa reste l’orchestrateur ; OpenHands Agent Server / Software Agent SDK 1.43.1
est le moteur agentique du profil Programmation. Le runtime final utilise
`Qwen2.5-Coder-7B-Instruct Q6_K` à 22 000 tokens, un seul slot et llama.cpp
b10516. Agent Canvas ne fait pas partie du chemin de fonctionnement ; il peut
rester installé à des fins administratives seulement. Docker Desktop doit être
démarré manuellement : Léa vérifie sa disponibilité, mais ne lance pas Docker.

Le registre `config/models.json` est la source de vérité de cette configuration,
des outils `terminal`, `file_editor`, `task_tracker` et de leurs limites. Le
profil Général et le runtime Programmation ne sont pas exécutés en parallèle.

## D-020 — Projet figé, runs persistants et checkpoints sûrs
Au départ d’un run, le backend fige le `project_id`, le chemin relatif et
l’identité du projet déjà validé sous `L:\IA_WORKSPACE`. Un changement de
sélection dans une autre session ne peut donc pas rediriger le run, son diff,
son acceptation ou son rollback.

Chaque run possède un checkpoint hashé créé avant les outils. Les changements
restent consultables puis exigent une acceptation explicite ou un rollback. Une
modification externe, un remplacement du projet ou une identité non conforme
provoque un conflit plutôt qu’un écrasement silencieux. Annulation, timeout et
fin de run ne publient un état terminal qu’après l’arrêt du conteneur Agent
Server vérifié, afin qu’aucun outil tardif ne puisse muter le projet en silence.

SQLite conserve uniquement le registre compact des runs, leurs résultats, leurs
identifiants de session et les métadonnées/hashs de checkpoint. Les snapshots
restent dans le stockage local de checkpoints et les événements détaillés de la
session restent dans le volume d’état de l’Agent Server.

## D-021 — Modèles remplaçables et adaptateur d’inférence unique

L’étape 11 conserve Léa comme application et orchestrateur. Un profil définit
le comportement, les prompts, les outils, les budgets et les permissions ; un
modèle définit les poids interchangeables, les capacités déclarées et les
paramètres d’inférence. Le registre `config/models.json`, schéma 3, les associe
par `model_id`. Les identités Qwen ne sont plus des conditions de validation
du code métier. La configuration actuelle conserve exactement les deux GGUF.

`model_registry.py` valide les références, les capacités nécessaires aux deux
profils actuels, les budgets, les limites de ressources et les fichiers confinés.
La déclaration d’une capacité ne remplace jamais un essai réel : Programmation
exige du tool calling natif fonctionnel. Deux profils peuvent référencer la même
définition compatible, sans fusion des contrats ni des permissions.

`inference.py` contient le seul adaptateur implémenté, llama.cpp : commande,
endpoints, protocole de génération et readiness par alias. Les lanceurs existants
gardent la propriété et l’identité des processus, l’arrêt sûr et le contrôle de
ressources. `tools/model_config.py` fournit aux scripts PowerShell une projection
éphémère du même registre, pas un second fichier de configuration.

Le runner OpenHands lit le même registre que le contrôleur. Le template et les
séquences d’arrêt sont propres au modèle ; les hooks, preuves d’outils, limites
agentiques et checkpoints restent indépendants. Le champ public historique
`qwen_available` est conservé pour la compatibilité du frontend, sans couplage
interne à cette famille. L’option Python `-B` ne change pas le résultat des tests :
elle est reconnue dans les preuves terminal uniquement avec un vrai succès.

Aucun framework de plugins, moteur additionnel ou mécanisme de secours n’est
créé. Un futur moteur nécessitera son adaptateur, sa validation de configuration,
son intégration aux propriétaires de processus et ses tests ; les données et
contrats de Léa ne doivent pas être reconstruits. L’étape 12 pourra s’appuyer sur
ce validateur central, mais aucune interface ou API d’édition n’est ajoutée ici.

## D-022 — Roadmap après séparation des modèles

La roadmap autorisée est celle des étapes 11 à 25 indiquée dans le README et le
TODO : 11 Architecture indépendante des modèles, 12 Centre de paramètres de
Léa, 13 Programmation avancée, 14 Entrées multimodales, 15 Veterinary,
16 Auxiliaire, 17 Génération d’images, 18 Web Gateway, 19 Speech-to-Speech,
20 Refonte visuelle, 21 Mémoire avancée, 22 Fine-tuning optionnel,
23 Sécurité finale, 24 Tests finaux, 25 Logiciel desktop final.
Le contenu précis de l’étape 13 sera rediscuté ultérieurement. Aucun travail
d’étape suivante n’est autorisé avant validation manuelle et demande explicite.

## D-023 — Préférences de Léa disponibles sans cœur chargé

L’audit 12A a confirmé que Vite possède déjà un contrôleur local de cycle de
vie et reste disponible après `stop-core`. Le conserver évite un nouveau serveur
et un modèle démarré pour ouvrir des paramètres. `tools/preferences-controller.ts`
ajoute uniquement `/api/preferences` ; un CLI Python ponctuel partage les modèles
Pydantic et le stockage existants. Dépendances inchangées : Vite, Python installé,
SQLite et registre local valides restent nécessaires, pas FastAPI actif ou Docker.

La migration 8 ajoute une table à ligne unique : choix `general_reasoning`
(`low`/`high`, défaut `low`) et révision. Les transactions atomiques et la révision
attendue empêchent une écriture périmée ; les colonnes étrangères au réglage ne
sont pas remplacées. Un stockage absent est créé ; une corruption est signalée,
jamais réinitialisée silencieusement. Le helper ne récupère pas les générations
interrompues : seul le propriétaire backend effectue cette opération au démarrage.
La vérification des versions de migration est répétée sous verrou transactionnel
pour les ouvertures concurrentes de Vite et FastAPI.

La page dédiée conserve le panneau conversation monté mais masqué, donc ses
brouillons et son suivi de run. La valeur provisoire reste distincte du dernier
commit confirmé. Relecture après conflit, timeout ou réponse perdue ; aucun faux
succès. Origine et Host loopback imposés, payload borné, JSON strict, commande
Python et actions fixes, sans shell ni chemin fourni par le navigateur. Aucun
réglage ne peut démarrer un service ou modifier le registre.

## D-024 — Raisonnement disponible uniquement après preuve de compatibilité

Le choix fonctionnel appartient à SQLite. Sa traduction dépend uniquement de
la capacité `models[].reasoning_control` : `none` par défaut ou `think_directives`
après essai réel. Pas de condition métier sur le nom Qwen, pas de parseur de
modèles concurrent. Sans capacité, le contrôle Général devient indisponible,
le choix reste conservé et une sauvegarde est refusée explicitement.

Avec le Qwen3 actuel et llama.cpp b10516, `/no_think` produit un bloc de pensée
vide et `/think` un bloc non vide avant la réponse. Le moteur servi n’annonce
pas `supports_reasoning_effort` : aucune fausse option API n’est envoyée. Le
backend fige la directive pour la prochaine génération (envoi, retry, édition,
régénération), sans redémarrage et sans modification d’une requête en cours.
Le filtrage privé existant est conservé et inclut le refus d’un `/think` résiduel.
Le budget reste 1 024 tokens, réflexion comprise : High n’est pas une garantie
de qualité, de délai ou de réponse exploitable sur toute question.

L’audit Programmation a couvert le template hashé `function_call`, le prompt
de profil, le runner SDK 1.43.1 et le serveur réel : outils natifs disponibles,
pas de capacité `reasoning_effort`, aucun commutateur de réflexion validé dans
ce chemin. LLM reste à température 0, appels sériels et budgets inchangés.
Des consignes « plus approfondies » ou un budget accru ne prouveraient pas un
raisonnement natif et pourraient perturber les appels d’outils. Aucun Low/High
ni faux High par défaut n’est donc livré pour Programmation, conformément au
cas autorisé en 12E. Une future stratégie d’agent devra être nommée, autorisée
et testée séparément ; aucun choix supplémentaire n’est requis pour clôturer 12.

Qwen2.5-Coder-7B peut échouer sur des tâches agentiques multi-fichiers longues lorsque file_editor exige des remplacements textuels exacts. Léa détecte ces boucles, refuse les mutations invalides, valide les changements par des tests et peut restaurer le checkpoint.

Le benchmark `Lea_FinalValidation_Test` reste conservé pour une comparaison
future avec GLM-5.3-Flash ; il n’a pas été relancé ni compensé dans cette étape.

## D-025 — Extension localisée et clôture de l’étape 12

Un futur paramètre exige sa migration additive, son contrat strict, un contrôle
dans `Settings.tsx`, son consommateur métier et ses tests. La préservation des
autres colonnes est démontrée par un test isolé ; aucun réglage factice ne reste
dans l’interface. Pas de routeur global, framework de paramètres ou refonte du
cycle de vie. Le périmètre de l’étape 13 reste à rediscuter.

Revue KEEP / ADAPT / REMOVE : conserver les propriétaires de processus, contrats,
gardes de sécurité, outils, mémoire, données, checkpoints, volumes et laboratoires ;
adapter la construction du message Général et la navigation minimale ; retirer
uniquement un doublon de test, les caches de navigateur/build générés pour
cette étape et le bytecode Python régénérable. Aucun fichier source historique
n’est déclaré inutile sans preuve.

La validation réelle utilise une base isolée et un projet jetable sous
`L:\IA_WORKSPACE`, jamais le dépôt principal comme cible OpenHands. Le hash de la
base utilisateur reste identique. Les détails et limites des essais sont inscrits
dans le changelog ; la validation manuelle finale de l’étape 12 reste attendue.

## D-026 — Périmètre confirmé de l’étape 13 et audit

L’autorisation explicite de l’étape 13 confirme la validation manuelle de 12.
L’utilisateur précise : Docker Desktop et l’interface OpenHands s’ouvrent
manuellement ; seul « Lancer le run » peut créer le conteneur Agent Server.
La création du serveur idle à l’activation et après finalisation est retirée.
Le support de l’identification/arrêt des anciens idle reste utile à la migration.

Audit KEEP : registre/adaptateur uniques, propriétaires de processus, SDK natif,
politique hashée des outils, evidence gates, checkpoints, mémoire et SQLite.
IMPROVE/ADAPT : attente parent bornée, arrêt confirmé, blocage des reprises
incertaines, diagnostics publics filtrés, cadence frontend, PID recyclés.
ADD : unique échantillonneur en RAM, route de lecture cachée, petite vue
facultative et préférence dans le stockage existant. REMOVE : allocations idle
automatiques et seuls caches de test prouvés régénérables. Aucune heuristique
de raisonnement, dépendance supplémentaire ou grande refonte.

## D-027 — Interruption : incertain n’est ni absent ni réussi

Un échec d’inspection Docker exige une liste exacte réussie pour conclure à
l’absence. L’arrêt et la suppression revérifient ID, labels, image, mounts et
restrictions. Un état Running illisible reste incertain. Le parent borne le
processus SDK au budget + 60 s et refuse un succès sans code de sortie nul
ou avec mauvais run_id. Un échec conserve le checkpoint et exige Rollback
explicite ; aucune mutation n’est rejouée au redémarrage.

Les diagnostics affichables viennent d’une liste exacte de textes backend.
Un run persistant non maîtrisé interdit toute nouvelle activité modèle jusqu’à
son arrêt vérifié. Le lanceur peut oublier un ancien PID uniquement si sa date
de création prouve sa réutilisation ; le nouveau processus n’est jamais retourné
aux fonctions d’arrêt et les contrôles de port continuent de refuser un occupant.

Le conteneur arrêté d’un run réussi, dont preuves et checkpoint sont persistés,
est temporaire : suppression ciblée sans `--force` et sans volume. Les conteneurs
échoués et les données de session restent conservés pour diagnostic. Pas de
maintenance globale ou périodique, de prune ou de suppression concurrente.

## D-028 — Surveillance légère, sans autorité sur les charges

Une seule tâche asyncio FastAPI, commune à tous les profils IA actifs : RAM disponible
Windows et CPU par intervalle à 10 s, NVIDIA et Docker à 30 s. Aucun PowerShell
périodique ni base de télémétrie. Le navigateur lit uniquement un snapshot et
ne peut fournir d’arguments de sonde. Le modèle est vérifié par readiness et
alias, Agent Server seulement pendant un run. Un endpoint muet reste incertain.

Complément demandé avant clôture : la tâche démarre dès Général et reste la même
pendant les commutations. Les seuils suivent la politique du profil courant ;
les données système ne dépendent d’aucun nom de modèle ou de profil. Seules les
sondes Docker/OpenHands restent conditionnées au moteur agentique (ou à un run
interrompu en récupération). L’arrêt du cœur ferme la tâche ; aucune nouvelle
boucle ni nouvelle préférence. Un snapshot est corrélé au profil pour refuser
les diagnostics tardifs d’une ancienne sélection. « Votre question » reprend
la classe CSS `conversation`, sans nouveau composant ni refonte visuelle.

Seuils RAM 8/6 Gio issus du registre pour ce PC de 32 Go, deux relevés et marge
de récupération 1 Gio. CPU 90 % sur trois relevés, retour sous 80 % sur deux.
VRAM sous 1 Gio sur deux relevés frais, retour à 1,25 Gio. Une sonde absente
reste inconnue ; une anomalie indispensable pendant un run devient CRITICAL.
Aucun niveau ne déclenche d’arrêt automatique. Le diagramme n’a pas d’autorité
sur les alertes : préférence additive SQLite 9, false par défaut, sauvegarde
partielle avec révision, indépendante de la capacité de raisonnement Général.

## D-029 — Barrières Edge et Windows

L’automatisation Edge agentique est reportée avec accord explicite : le CDP
local et une liste d’URL ne prouvent pas le blocage des redirections, WebSocket,
workers et sous-ressources externes. Ne pas annoncer une isolation fictive.
Les scénarios Edge de validation restent des outils développeur locaux, à profil
jetable, non accessibles au modèle. Aucun navigateur agentique livré.

L’audit Windows ne justifie pas un nouveau pont : les propriétaires de PID et
les compteurs natifs couvrent le besoin. Aucun terminal PowerShell arbitraire,
endpoint de commandes, droit administrateur ou accès hôte supplémentaire à l’agent.
Les protections existantes sont conservées ; aucune isolation noyau/réseau
Docker absolue n’est revendiquée. Étape 14 inchangée, consacrée au multimodal,
non commencée sans validation manuelle de 13 et nouvelle demande.

## D-030 — Audit initial étape 14 : voix seule ; accord alors en attente

Le prompt 14 fourni le 17 octobre 2026 confirme la validation manuelle et la
finalisation de 13. Il remplace le périmètre initial « Entrées multimodales » par
microphone, dictée et conversation vocale locale tour par tour. Vision, VAD de
fin de tour, mains libres, écoute permanente et étape 15 restent hors périmètre.
La numérotation des prochaines étapes ne change pas.

### Audit initial effectué, sans installation

Départ Git : `24fb63b`, étape 13 ; seul le prompt 14 utilisateur est non suivi.
Le PC possède 33 995 571 200 octets de RAM (31,66 Gio), un i7-13700H à 20 threads
logiques et une RTX A1000 Laptop de 6 Gio. Général, FastAPI et Vite sont déjà
actifs ; aucun run ni génération en cours lors de la vérification. Python du
backend : 3.12.10. Aucun moteur Whisper/Piper trouvé dans les runtimes du projet,
les paquets du backend ou le PATH inspectés.

SAPI expose David/Zira anglais ; OneCore comporte aussi Caroline, Claude et
Nathalie en français canadien. Leur présence ne démontre pas encore leur
disponibilité dans Edge ni leur qualité sur les réponses techniques de Léa.
Aucun microphone n’a été activé et aucun haut-parleur n’a été testé.

KEEP : React/Vite, contrôleur local, FastAPI unique, SQLite et ses révisions,
registre central/adaptateurs, mémoire, propriétaire des processus, surveillance,
OpenHands et checkpoints. Le refus backend du chat direct en Programmation reste
obligatoire : une entrée vocale n’est jamais une autorisation de le contourner.

Deux contraintes identifiées avant développement :

- La dictée doit rester disponible lorsque le cœur est arrêté. Le contrôleur
  Vite existant peut accueillir des opérations vocales fixes et bornées, avec
  workers locaux à la demande, sans nouveau serveur ni chargement implicite de Qwen.
- Les runs Programmation sont actuellement persistés séparément des messages.
  L’intégration vocale devra les relier à l’historique existant avec corrélation
  et absence de doublon, sans nouvelle base ni faux appel conversationnel.
  Les contrôles du profil et du projet devront être revérifiés au serveur après
  transcription ; Accept/Rollback resteront des décisions visuelles explicites.

### Comparaison documentaire, pas un benchmark de ce PC

| Option | Intérêt et coût à vérifier | Proposition |
| --- | --- | --- |
| whisper.cpp, Whisper Small Q5_1 multilingue | Windows/CPU, poids de 190,1 Mo, quantification, pas de pile PyTorch ; qualité française et latence locales à mesurer | Premier candidat STT |
| whisper.cpp, Base Q5_1 multilingue | 59,7 Mo, candidat plus léger ; précision technique potentiellement moindre, à mesurer | Comparaison si Small est trop lent/lourd |
| faster-whisper CPU int8 | CTranslate2/PyAV et dépendances supplémentaires ; performances publiées intéressantes mais obtenues sur un autre PC | Alternative non installée |
| Piper, SIWIS medium | Voix française mono-locutrice de 63,2 Mo, ONNX CPU, package Windows disponible ; naturel et ponctuation à écouter | Premier candidat TTS, sous réserve des essais |
| Kokoro-82M, ff_siwis | Voix française disponible ; chaîne Python officielle avec PyTorch/espeak et poids supplémentaires | Non prioritaire pour cette première intégration sobre |
| Voix Windows OneCore françaises déjà présentes | Aucun poids à ajouter ; intégration réellement locale et qualité à vérifier | Alternative légère à évaluer, pas un fallback distant |

Sources primaires consultées : [whisper.cpp](https://github.com/ggml-org/whisper.cpp),
[faster-whisper et ses mesures CPU](https://github.com/SYSTRAN/faster-whisper),
[Piper](https://github.com/OHF-Voice/piper1-gpl),
[distribution Windows Piper](https://pypi.org/project/piper-tts/1.8.0/),
[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) et
[ses voix](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).
Les chiffres publiés par ces projets ne sont pas présentés comme des mesures Léa.
La sélection définitive exige des essais STT français, TTS, qualité et ressources.

### Fichiers proposés, aucun encore téléchargé

| Ressource officielle | Taille de téléchargement | Licence déclarée |
| --- | --- | --- |
| whisper.cpp `b5130/whisper-bin-x64.zip` (build indiqué par la release 1.9.4) | 8 573 270 octets | MIT |
| `ggerganov/whisper.cpp/ggml-small-q5_1.bin` | 190 085 487 octets | MIT |
| `ggerganov/whisper.cpp/ggml-base-q5_1.bin`, seulement pour comparaison si nécessaire | 59 707 625 octets | MIT |
| `piper_tts-1.8.0-cp39-abi3-win_amd64.whl` | 34 119 688 octets, plus dépendances CPU | GPL-3.0-or-later |
| `rhasspy/piper-voices/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx` | 63 201 294 octets | Dépôt MIT ; carte de la voix : corpus CC-BY 4.0 |
| Même chemin, `fr_FR-siwis-medium.onnx.json` et `MODEL_CARD` | 4 875 et 284 octets | Métadonnées et attribution conservées |

Provenances : [archive CPU officielle](https://github.com/ggml-org/whisper.cpp/releases/tag/b5130),
[poids Whisper](https://huggingface.co/ggerganov/whisper.cpp/tree/main),
[voix SIWIS](https://huggingface.co/rhasspy/piper-voices/tree/main/fr/fr_FR/siwis/medium)
et [sa carte](https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD).
Les seules lectures réseau de cet audit portent sur documentation et métadonnées,
jamais sur des données utilisateur. Aucun accès réseau ajouté à Léa.

Révisions HF relevées : Whisper `5359861c739e955e79d9a303bcbc70fb988958b1`,
voix `c10ece1aade47bb51c153c893d14e5bf8e5b7117`. Empreintes SHA-256 publiées :

- Archive CPU : `f9ec6c52a2e949b62ab51fa21d0d497958f9e41c3010c157c4e42932d5316f3c`.
- Whisper Small : `ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb`.
- Whisper Base : `422f1ae452ade6f30a004d7e5c6a43195e4433bc370bf23fac9cc591f01a8898`.
- Piper Windows : `5da9bfdb05dfe15da3536859d422e605483ffa6d2b3ec2c5b9593bae6b5aa6a4`.
- Voix SIWIS : `641d1ab097da2b81128c076810edb052b385decc8be3381814802a64a73baf99`.

Enveloppe proposée : au plus **450 Mo de téléchargements** pour ces candidats
et les dépendances CPU requises (notamment ONNX Runtime, NumPy, pathvalidate et
leurs dépendances résolues). Aucun extra entraînement, PyTorch, CUDA ou serveur
Piper. Arrêt et nouvel accord si cette enveloppe ou la sélection doit changer.
Prévoir environ 1 Gio de disque pour l’installation, à confirmer après résolution.
Les licences des dépendances seront également consignées avant installation.

Emplacements envisagés : `runtime/voice/whisper.cpp/`, environnement Python
vocal isolé sous `runtime/voice/`, poids dans `models/voice/`. Les binaires et
poids seront exclus de Git ; les préférences resteront dans SQLite et le
registre technique unique sera étendu sans modifier les paramètres Qwen.
Aucun téléchargement automatique au lancement, aucune réduction du contexte
Programmation, aucun chargement GPU vocal prévu.

### Suite après accord et validations encore nécessaires

Fichiers à adapter : `src/App.tsx`, `src/Settings.tsx`, `src/preferences.ts`,
capture/lecture et vue vocale dédiées ; `vite.config.ts` et contrôleur vocal
local borné ; `backend/app/{model_registry,preferences,migrations,main,database}.py`,
intégration des résultats OpenHands à l’historique, helpers STT/TTS, tests
backend/frontend/Edge et documentation. Pas de framework de plugins ni refonte.

Les mesures 14J (RAM au repos/pics STT/TTS, VRAM, CPU, chargement, transcription
sur plusieurs durées, synthèse, début de lecture, échange complet avec les deux
profils) restent **non réalisées**, faute de moteurs installés. Les tests de
microphone physique, refus/déconnexion et haut-parleurs ne sont pas revendiqués.
Une procédure manuelle complétera les essais automatisables, conformément au prompt.

L’étape 14 n’est pas déclarée réussie. Le prochain point obligatoire est l’accord
utilisateur pour cette installation ; aucun modèle vocal ne doit être téléchargé
avant cet accord, malgré la demande générale d’exécution autonome.

Base de non-régression vérifiée avant installation : 237 tests backend,
25 frontend, build, 6 cas d’identité du lanceur et analyse AST des 11 scripts
PowerShell réussis ; `git diff --check` passe. Commandes :

```powershell
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -q
npm run test:frontend
npm run build
.\tests\launcher-process-record.ps1
git diff --check
git status --short
```

Ces tests portent sur l’existant, pas sur une implémentation vocale. Le démarrage
complet n’est pas rejoué : la session utilisateur est déjà active et l’API confirme
Général `ready`. Aucun processus de test persistant ajouté. Les trois fichiers
de build régénérables de cet audit sont nettoyés ; les données et checkpoints
ne sont pas modifiés. Seuls AGENTS, README, TODO, CHANGELOG et cette décision
sont modifiés ; le prompt utilisateur non suivi est conservé intact.

## D-031 — Voix locale CPU autorisée et intégrée, sans nouveau serveur

L’utilisateur a ensuite autorisé les téléchargements nécessaires jusqu’à 10 Go.
L’état « en attente » de D-030 est historique : Whisper Small Q5_1 et
Piper/SIWIS sont maintenant installés dans les emplacements annoncés, avec
versions figées, empreintes vérifiées et dépendances vocales isolées. Aucun
changement des modèles conversationnels, du contexte Programmation ou du
runtime llama.cpp. Base/Kokoro/faster-whisper ne sont pas installés : les mesures
du premier choix ne justifient pas ces dépendances supplémentaires.

Les opérations fixes status/transcribe/speak réutilisent le serveur Vite local.
Un worker ponctuel sous job Windows lit une seule requête stdio, puis se termine ;
la fermeture du canal propriétaire annule ses enfants. Aucun moteur vocal ne
réside au repos. Capture, WAV et synthèse restent en mémoire. Les versions CPU
limitent la concurrence à quatre threads et n’ajoutent pas de charge GPU voulue.
La surveillance générale de l’étape 13 reste unique et inchangée.

La dictée ajoute au brouillon sans envoyer. La vue vocale masque les messages
et déclenche le traitement au second clic, jamais par silence. Général emploie
la conversation existante ; les profils agentiques passent par le gestionnaire
OpenHands existant. La migration 10 relie une paire de messages au run dans la
même transaction, puis actualise la réponse terminale sans doublon. Ces tours
ne peuvent pas être rejoués par les actions du chat. Le serveur revérifie
profil, projet et révision ; le résultat exige une transition vers le diff,
sans Accept ni Rollback implicite. Une fermeture audio n’annule pas en secret
un run déjà autorisé.

Les préférences restent révisionnées dans SQLite : périphérique, français/anglais,
lecture activée, voix réellement installée, volume et vitesse. Aucun gain fictif,
API vocale distante, accès Web agentique, VAD ou écoute automatique ajouté.
Les lectures privées ne sont pas journalisées. Les WAV synthétiques sont des
fixtures de test explicitement produites, pas des enregistrements utilisateur.

Mesures, licences, preuves réelles/simulées, limites de transcription et procédure
microphone/haut-parleurs sont détaillées dans `ETAPE_14_VALIDATION.md`. La validation
physique et l’accord final de l’utilisateur restent nécessaires avant toute suite.

## D-032 — Pocket TTS français devient la voix de Léa, Piper reste indépendant

Après essai isolé et écoute humaine du texte de présentation contenant « Stan »,
l’utilisateur a retenu Pocket TTS 3.3.0, variante légère `french`, avec l’état
vocal officiel techniquement nommé `estelle`. L’interface n’expose que
« Léa — Voix naturelle française ». Le nom technique original reste uniquement
dans le fichier requis par le moteur et dans les attributions ; il n’est ni
renommé ni dissimulé dans les métadonnées de provenance.

Les poids, le tokenizer et l’état vocal sont copiés comme fichiers réguliers sous
`models/voice/pocket-tts/french/`, avec SHA-256 épinglés. Le YAML de production
ne contient aucune URL ni chemin expérimental. L’environnement ponctuel existant
`runtime/voice/.venv` reçoit les dépendances CPU ; aucun service, API distante,
CUDA ou worker résident n’est ajouté. L’exécution force le mode Hugging Face
hors ligne et conserve audio et fragments en mémoire jusqu’à la réponse WAV.

Le registre décrit désormais chaque voix par son propre moteur. Piper/SIWIS
reste disponible sous « SIWIS — Voix classique » et continue d’appliquer la
vitesse 0,75–1,5×. Pocket TTS ne fournit pas ce contrôle : sa vitesse reste à
1×, le curseur est désactivé et une requête directe incompatible est refusée.
Le volume Web Audio s’applique aux deux. Aucun moteur ne sert de repli silencieux
à l’autre. La migration SQLite 11 choisit `lea_voice` une fois sur les bases
existantes sans changer le microphone, la langue, le volume, la vitesse, Low/High
ou le diagramme ; un choix ultérieur de SIWIS persiste normalement.

Pocket TTS produit des fragments progressivement en interne, mais le protocole
Vite/stdio et Web Audio conserve un WAV complet. Diffuser ces fragments jusqu’au
navigateur imposerait un nouveau protocole et un cycle d’annulation plus complexe ;
le chargement et la synthèse mesurés étant déjà courts, cette complexité n’est
pas retenue. Fermer ou interrompre continue de tuer le worker ponctuel via le job
Windows et de libérer le modèle. Les protections de dictée, historique, mémoire,
profils et OpenHands restent inchangées.

Provenance : code Pocket TTS sous MIT ; poids `kyutai/pocket-tts` sous CC-BY 4.0
et conditions d’utilisation acceptées par l’utilisateur ; état vocal officiel
issu des ressources Kyutai, dont la source Estelle est indiquée CC0 dans leur
catalogue. Les révisions, empreintes et validations sont consignées dans
`ETAPE_14_VALIDATION.md`. Après validation physique par l’utilisateur, l’absence
de dépendance a été revérifiée et le dossier expérimental a été supprimé ; les
ressources permanentes et leurs attributions restent inchangées.

## D-033 — Suppression réelle des conversations et nettoyage SQLite borné

La suppression frontend reste la route `DELETE` existante avec révision
optimiste. Le backend exécute le `DELETE FROM conversations` dans une transaction
`BEGIN IMMEDIATE`; `messages` et `memory_sources` suivent par leurs clés
étrangères `ON DELETE CASCADE`, activées sur chaque connexion. Les souvenirs
explicitement créés par `Retiens que` restent globaux et ne sont effacés que par
`Oublie que` ou par une maintenance expressément autorisée. Il n’existe ni FTS,
résumé dérivé, pièce jointe ni table de suppression logique. Les runs techniques
restent indépendants : leur lien conversation devient `NULL`, leurs tâches,
preuves et checkpoints ne sont pas purgés avec l’historique utilisateur.

Le contenu observé après une ancienne suppression ne provenait d’aucune ligne
orpheline : l’audit de la base active comptait zéro violation logique et zéro
violation de clé étrangère. La cause sous contrôle était la politique physique
SQLite : `secure_delete` valait 0, donc une ligne supprimée pouvait rester dans
une page libérée jusqu’à réécriture ou compaction. Chaque connexion fixe désormais
`PRAGMA secure_delete=ON`. Un test HTTP supprime deux conversations successives,
conserve une troisième et vérifie l’absence après redémarrage ; un test SQLite
contrôle les tables, les relations et les marqueurs bruts après checkpoint WAL.

Avant la maintenance active, le mécanisme officiel `sqlite3_backup` a produit
`L:\Lea_Backups\lea-before-final-cleanup-20261019.sqlite3`, vérifié lisible et
intègre. Léa étant arrêtée, l’unique mémoire de test autorisée a été effacée,
le WAL checkpointé, puis la base reconstruite par `VACUUM`. L’unique conversation
active et ses deux messages, les préférences, 159 runs, 159 checkpoints et leurs
2 687 entrées sont inchangés. Le catalogue courant a supprimé ses 13 entrées de
projets désormais absents du workspace, sans modifier leurs audits historiques.
La base passe de 1 683 456 à 1 581 056 octets,
`integrity_check=ok`, zéro violation étrangère et aucun WAL/SHM restant après
fermeture. Cela nettoie la base active, pas les blocs SSD ni la sauvegarde externe,
qui peut encore contenir les données antérieures et doit rester hors Git.

`L:\IA_WORKSPACE` avait déjà été vidé par l’utilisateur pendant la phase B. La
maintenance l’a seulement vérifié présent, ordinaire et vide, sans recréer de
fixture. Le catalogue Programmation vide est accepté par les tests et le cycle
réel Général. Un audit Docker pré-commit distinct a ensuite relié 155 conteneurs
arrêtés à des runs terminaux de la base active et à leurs checkpoints présents ;
ils ont été supprimés avec l’ancien serveur idle, sans force, volume, image ni
prune. Neuf conteneurs de runs isolés absents de la base active et trois anciens
serveurs SDK encore référencés par leurs états de bootstrap restent arrêtés, car
leur utilité est ambiguë. Aucun conteneur Léa actif, serveur OpenHands, worker
vocal ou processus modèle ne subsiste à la fin.
