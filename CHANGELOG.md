# Changelog — Projet Léa

## Étape 15 — Profil Vétérinaire et contrats — 22 octobre 2026

- Troisième profil local `veterinary` sur Qwen3.5-9B Q4_K_M : empreinte et
  taille contrôlées, contexte 16 384, un slot, KV Q8_0, budgets et politique de
  ressources dédiés, sans outil, workspace, Web, vision ou RAG.
- Cycle de vie généralisé aux profils directs : commutation atomique
  Général/Vétérinaire, transitions OpenHands et restauration du profil précédent
  vérifié. Docker et l'interface OpenHands restent manuels ; aucun serveur idle.
- Migration SQLite 12 et Paramètres : Low/High Vétérinaire indépendant de
  Général, High initial, effet à la requête suivante par le mécanisme natif
  `chat_template_kwargs.enable_thinking`. Programmation reste sans faux réglage.
- Historique, suppression de conversations, mémoire explicite, surveillance et
  voix partagés avec les chemins existants ; aucun audio privé ni mémoire de
  benchmark persisté dans la base personnelle.
- Contrat commun audité puis restauré intégralement lorsque sa simplification a
  supprimé des formulations de sécurité protégées ; Général, mémoire et
  Vétérinaire clarifiés. Scénarios reproductibles et corrigé vétérinaire
  indépendant consignés dans `docs/ETAPE_15_VALIDATION.md`.
- Tentative de simplification du contrat Programmation annulée : deux régressions
  `file_editor` réelles contre une réussite de référence. Détection de boucle,
  validation, checkpoint et rollback fonctionnent sans heuristique spécifique.
- Qwen2.5-Coder-14B ignoré et non référencé supprimé sur demande, soit
  10 508 873 152 octets ; Qwen2.5-Coder-7B et tous les modèles permanents utiles
  conservés hors Git.
- Clôture : 261 tests backend et 41 tests frontend réussis, build Vite vert,
  registre complet et 15 scripts PowerShell validés. Les caches, le build et le
  workspace isolé ont été retirés ; les runs et checkpoints restent conservés.
- Étape 16 Web non commencée, vision suspendue, Auxiliaire supprimé de la roadmap.
- Aucun commit ni push ; validation manuelle de l'étape 15 encore requise.

## Étape 14 — Maintenance finale avant commit — 19 octobre 2026

- Audit de 151 fichiers : aucun module de production obsolète démontré ; deux
  imports inutilisés retirés des tests, scripts historiques et barrières conservés.
- Suppression de conversation confirmée de bout en bout : route HTTP réelle,
  transaction SQLite, cascades `messages`/`memory_sources`, conservation des
  souvenirs explicitement globaux et des historiques techniques indépendants.
- `PRAGMA secure_delete=ON` appliqué à chaque connexion. Base active sauvegardée
  hors dépôt avant maintenance, mémoire de test autorisée supprimée, WAL
  checkpointé, `VACUUM`, intégrité et clés étrangères vérifiés sans toucher à
  l’unique conversation active, aux préférences, runs ou checkpoints.
- `L:\IA_WORKSPACE`, déjà vidé par l’utilisateur pendant la phase B, contrôlé
  présent, normal et vide ; aucun projet de test n’y a été recréé. Le catalogue
  courant passe de 13 chemins absents à 0 sans purger runs ni checkpoints.
- Audit Docker pré-commit : 156 conteneurs Léa arrêtés et démontrés jetables
  supprimés sans force ni volume (155 runs terminaux liés à leurs checkpoints
  présents, plus l’ancien idle). Neuf runs isolés absents de la base active et
  trois serveurs SDK encore référencés sont conservés par prudence. Images,
  volumes, historiques et checkpoints inchangés ; environ 575,3 Mo récupérés.
- Validation : 256 tests backend, 41 frontend, build, 12 scripts PowerShell
  analysés et 8 cas ciblés. Cycle Général réel sur base isolée, Low/High,
  mémoire, suppression, redémarrage, ressources, Pocket TTS, Piper et Whisper
  réels sur audio synthétique. Microphone physique non rejoué. Un Agent Server
  OpenHands réel a démarré, répondu, été arrêté puis supprimé sur un dossier
  temporaire vide ; aucun run agentique n’a été relancé faute de projet utilisateur.
- Aucun commit/push, aucune étape 15 et aucun mécanisme de compensation de Qwen.

## Étape 14 — Clôture manuelle et nettoyage — 18 octobre 2026

- Validation manuelle confirmée : microphone, deux voix locales et paramètres
  fonctionnels ; qualité de « Léa — Voix naturelle française » acceptée.
- Installation permanente Pocket TTS revérifiée hors ligne par empreintes,
  environnement actif et synthèse réelle avant suppression du banc d’essai.
- Suppression strictement limitée à `L:\Lea_TTS_Estelle_Test_Temp`, après
  inventaire de ses caches, scripts, rapports et WAV expérimentaux. Modèles
  permanents, SIWIS, conversations, mémoire et checkpoints inchangés.
- Étape 14 déclarée terminée après les suites finales, le build et les contrôles
  Git ; aucun commit/push et aucune étape suivante commencée.

## Étape 14 — Voix naturelle française — 18 octobre 2026

- Pocket TTS 3.3.0, variante CPU `french`, intégré comme voix par défaut sous
  le nom utilisateur « Léa — Voix naturelle française ». Modèle, tokenizer,
  configuration hors ligne et état vocal officiel épinglés dans les dossiers
  vocaux permanents ; aucune dépendance au banc d’essai temporaire.
- Piper/SIWIS conservé comme « SIWIS — Voix classique ». Le registre décrit le
  moteur par voix, sans repli silencieux. Volume commun ; vitesse réelle Piper
  conservée, vitesse Pocket TTS fixe à 1× et limite explicitement affichée.
- Migration SQLite 11 : `lea_voice` devient le choix des installations nouvelles
  et existantes sans réinitialiser les autres préférences. Les changements de
  voix restent validés, révisionnés et persistants après redémarrage.
- Même worker ponctuel stdio et même job Windows : CPU uniquement, aucun serveur,
  fichier audio temporaire, téléchargement au fonctionnement normal ou modèle
  vocal résident. Les fragments internes ne sont pas diffusés au navigateur :
  le gain mesuré ne justifie pas un nouveau protocole de streaming.
- Pocket TTS reste techniquement associé à l’état officiel `estelle` pour la
  compatibilité et l’attribution Kyutai ; ce nom n’est jamais présenté comme le
  nom de la voix dans l’interface.

## Étape 14 — Diagnostic du décodage microphone — 18 octobre 2026

- Cause reproduite : le décodeur de VS Code 1.140.0 refuse le même WebM/Opus
  synthétique qu’Edge décode ; WAV PCM fonctionne dans les deux. L’annonce de
  prise en charge par MediaRecorder/canPlayType ne garantit pas ce décodage.
- Message partagé dictée/conversation orientant vers Edge externe, diagnostics
  limités aux métadonnées en console ; aucun audio privé conservé ni envoyé en
  cas d’échec du décodage. Documentation du navigateur requis pour la voix.
- Finalisation bornée : dernier dataavailable puis stop avant libération des
  pistes et conversion ; annulation immédiate conservée. Ce durcissement ne
  résout pas à lui seul l’absence du décodeur Opus dans VS Code.
- Tests : 251 backend, 40 frontend, build ; vrais MediaRecorder WebM/Opus et
  MP4/AAC, conversion PCM, Whisper, refus de données tronquées et deux modes UI.
  Réponse conversationnelle simulée dans ce test ciblé ; microphone physique
  toujours à valider manuellement dans Edge. Aucun nouveau moteur ou dépendance.

## Étape 14 — Implémentation et validation — 17 octobre 2026

- Autorisation et périmètre du prompt consignés : microphone, dictée locale et
  conversation vocale tour par tour ; étape 13 confirmée validée manuellement.
  Aucun changement de numérotation ultérieure, vision et mains libres exclus.
- Audit initial de l’existant et des ressources ; comparaison documentaire
  whisper.cpp/faster-whisper et Piper/Kokoro/voix Windows. Fichiers candidats,
  tailles, licences, empreintes et enveloppe de 450 Mo décrits dans D-030.
- Accord utilisateur obtenu ensuite pour les téléchargements nécessaires jusqu’à
  10 Go. Installation CPU isolée : Whisper Small Q5_1, whisper.cpp b5130 et
  Piper 1.8.0/SIWIS, environ 459 Mo sur disque ; Qwen et ses contextes inchangés.
- Dictée deux clics dans le brouillon, sans écrasement ni envoi automatique,
  utilisable cœur arrêté ; vue vocale séparée sans texte des échanges, traitement
  tour par tour, lecture locale interruptible et libération des pistes audio.
- Contrôleur borné dans Vite, workers temporaires stdio sous job Windows, aucun
  nouveau serveur, audio en RAM uniquement, aucun téléchargement à l’utilisation.
- Migration SQLite 10 : préférences vocales et lien des messages aux runs.
  Historique atomique/idempotent, exclusion des tours agentiques du chat direct,
  profil/projet figés, validation et décisions OpenHands inchangées.
- Correction ciblée du lanceur : Docker fermé ne fait plus échouer l’inspection
  du seul ancien conteneur idle par conversion de stderr en exception PowerShell.
  Aucun assouplissement de l’arrêt vérifié des runs actifs.
- Les erreurs de sonde de santé utilisent la tolérance consécutive existante :
  incident isolé sans annulation intempestive, panne persistante visible.
- Vérifications : 250 tests backend, 34 frontend, build, PowerShell 6+2,
  dictée cœur arrêté, Général vocal, persistance/mémoire, ressources deux profils.
  Programmation vocal : retour failed et Rollback ; un run écrit avec commande
  explicite est validated puis accepté. Aucune règle de preuve élargie pour Qwen.
- Rapport et limites de validation : `docs/ETAPE_14_VALIDATION.md`. Les essais
  navigateur utilisent une voix synthétique, pas un microphone physique ;
  l’écoute des haut-parleurs et la qualité subjective restent à valider manuellement.
- Vérification finale du 18 octobre : navigateurs et services de test arrêtés,
  caches/fixtures régénérables nettoyés, session habituelle Général rétablie ;
  historique, souvenir, préférences et checkpoints inchangés après redémarrage.
- Aucun commit/push, aucune étape suivante, aucune suppression de données ou checkpoints.

## [0.0.13] — Programmation avancée — 17 octobre 2026

### Complément demandé avant clôture

- Surveillance système RAM/CPU/VRAM disponible dès Général et pour chaque profil
  actif via le registre/adaptateur existants. Même boucle, fréquences et alertes ;
  politique du profil sélectionné, cache GPU partagé et rejet des snapshots tardifs.
- Sondes Docker/OpenHands limitées aux profils qui les utilisent ou à un run
  OpenHands en récupération. Aucune dépendance Docker pour les mesures Général.
- Arrêt de la collecte avec FastAPI et des lectures UI lorsque Léa est arrêtée.
  Préférence persistante false par défaut inchangée ; libellés harmonisés.
- Formulaire complet « Votre question » dans l’encadré CSS `conversation`
  existant, dimensions de saisie et comportement inchangés, sans nouveau style.
- Complément validé : 237 tests backend, 25 frontend, build et diff ; Edge réel
  à 1280/390 px, envoi Général et commutations Général/Programmation, aucune
  lecture de ressources cœur arrêté. Session habituelle rétablie après accord,
  base utilisateur inchangée, cache Edge et build de test nettoyés. Preuves et
  commandes à la fin du rapport étape 13.

### Fiabilité et reprise

- Attente SDK bornée côté parent (budget + 60 s), refus d’un succès avec mauvais
  run_id ou code de sortie non nul, diagnostics publics exacts sans texte privé.
- Une erreur Docker n’est plus assimilée à une absence. Arrêt revérifié avant
  état terminal ; reprise incertaine non terminale, nouvelle activité modèle
  bloquée. Annulation explicitement renouvelée possible, aucun replay d’outils.
- PID recyclé reconnu par sa date de création dans le lanceur, sans adopter
  ni tuer le nouveau processus. Le cas réel était un `backgroundTaskHost` Windows.
- Boucle de polling React corrigée : nouvel objet d’un même run ne redémarre
  plus l’effet immédiat. Edge confirme 9 lectures en 12 s, état actif simulé.

### Surveillance et paramètres

- Version initiale : tâche FastAPI unique en lecture seule, dormante hors Programmation ;
  étendue ensuite à tous les profils actifs par le complément ci-dessus. RAM
  disponible/CPU Windows à 10 s, NVIDIA/Docker à 30 s ; aucun service supplémentaire.
- États NORMAL/WARNING/CRITICAL avec persistance et marges de récupération,
  aucune action d’arrêt automatique ; mesures inconnues explicitement indisponibles.
- Migration SQLite additive 9 : `show_resource_chart`, false par défaut,
  édition partielle révisionnée ; sauvegarde hors IA, Low/High préservé.
- Trois barres RAM/CPU/VRAM en bas de page, alertes indépendantes du diagramme.
  Coût réel sans UI : 0,922 s CPU backend / 35 s (~0,13 % des 20 processeurs
  logiques), mémoire résidente 61 → 59 Mio ; avec UI 5,406 s / 35 s (~0,77 %).

### Choix et maintenance

- Docker Desktop et interface OpenHands manuels, selon décision utilisateur.
  Agent Server créé seulement au lancement explicite du run ; plus d’idle
  automatique à l’activation ou à la finalisation.
- Suppression du conteneur arrêté/validé exact, sans force ni volume ; échecs
  conservés pour diagnostic. Aucun prune, nettoyage global ou pont shell Windows.
- Edge agentique reporté avec accord : isolation réseau complète non démontrée.
  Les tests Edge développeur ne constituent pas cette capacité. Modèles, registre,
  prompts, hooks et heuristiques du runner inchangés ; benchmark difficile non relancé.

### Validation et clôture initiales (avant le complément)

- 232 tests backend, 24 frontend, build React/TypeScript et diff propres ;
  10 scripts PowerShell analysés, 6 cas d’identité du lanceur réussis.
- Général réel Low/High, mémoire, historique après arrêt/reprise ; Paramètres
  hors IA et persistance. Edge réel : diagramme, valeurs natives et alerte
  critique simulée diagramme masqué, capture relue.
- Run `81b43212-fd63-4572-a4d5-322aa18dda47` : lecture, correction source,
  `python -B -m unittest -v` vert, `completed`/`validated`, diff et Accept UI.
- Run `c0bb8bc2-be9f-48cb-b47b-aafa8dd120e1` : backend réellement interrompu
  après mutation, redémarrage, `failed`/validation échouée visibles, Accept
  refusé, Rollback UI exact des trois fichiers ; aucun double run.
- SQLite test intègre, aucune violation de clé étrangère ni marqueur privé.
  Base utilisateur inchangée : SHA-256
  `E8FC0A8C542D2540730DBE0E4F0B1620128843E70663A3003027BA43B2F1D5D6`.
- Checkpoints sans bytecode/cache Python. Le répertoire `.git` vide laissé par
  le montage après crash figure honnêtement dans le diff récupéré, puis est
  retiré par Rollback ; aucun effacement implicite d’un dossier non identifié.
- Ménage : 380 fichiers du seul profil Edge de test et 3 fichiers `dist/`
  régénérables retirés. Captures, base test, journaux, checkpoint accepté et
  checkpoint restauré conservés. Aucun fichier source suivi supprimé.
- Services Léa et Edge de test arrêtés ; Docker Desktop manuel et volumes
  préservés. Aucun commit/push. Rapport détaillé : `docs/ETAPE_13_VALIDATION.md`.
  Étape 13 techniquement complète ; validation manuelle attendue, étape 14 non commencée.

## [0.0.12] — Centre de paramètres de Léa

### Ajouté et adapté

- Page Paramètres accessible depuis l’en-tête, Low/High Général, validation
  explicite, état enregistré distinct du brouillon, erreurs/relecture et retour
  sans perte de conversation, brouillon ou run. Aucun contrôle futur factice.
- Table SQLite `user_preferences`, migration additive 8, défaut Low, révision
  optimiste et transactions. Pas de fichier de préférences concurrent ni cache navigateur.
- Route locale Vite `/api/preferences` et CLI Python ponctuel : fonctionnement
  sans FastAPI actif ni modèle chargé, sans nouveau serveur ni dépendance.
- Capacité déclarative `reasoning_control` dans le registre ; choix utilisateur
  dans SQLite. Général applique `/no_think` ou `/think` à la prochaine requête,
  sans interrompre une génération/run ni redémarrer de modèle.
- Programmation : audit documenté, pas de Low/High trompeur. Runner, outils,
  contrats, budgets, tests, Accept et Rollback inchangés.
- Prompt d’étape disponible sous `prompts/PROMPT_ETAPE_12_CODEX.md` avec son
  extension correcte ; documentation d’utilisation et d’extension localisée.

### Sécurité et stabilisation

- Le helper SQLite ne marque jamais une génération en cours comme interrompue.
  La récupération reste réservée au démarrage du backend ; migrations concurrentes
  revérifiées sous verrou. Aucune modification de données utilisateur réelles.
- JSON strict et borné, origine/Host loopback, aucune commande/chemin utilisateur,
  subprocess sans shell, délais bornés, conflit entre onglets explicite, refus
  des préférences corrompues et absence de confirmation sur erreur.
- Filtrage existant de la pensée conservé, refus d’un `/think` résiduel ajouté.
  La préférence n’écrit ni l’historique, ni les souvenirs, ni le registre des modèles.
- Fonctions nouvelles documentées, migration rangée avec les précédentes,
  doublon de test retiré ; ménage limité aux artefacts de test identifiés.

### Validation du 16 octobre 2026

- 213 tests backend et 21 frontend, build React/TypeScript et `git diff --check`
  réussis. SQLite temporaire réel ; modèles et certains transports/processus
  simulés dans les suites automatisées, distinction conservée dans les tests.
- Edge réel : Paramètres avec seulement Vite, lecture/écriture Low/High,
  confirmation, rechargement, brouillon conservé, navigation, focus et capture
  relue. Conflit HTTP réel et panne de transport simulée dans Edge, sans faux succès.
- Général réel : réponses Low/High correctes et filtrées. Sonde native finale :
  15 tokens avec bloc privé vide en Low, 310 avec bloc non vide en High pour
  la même question et température 0 ; réponse correcte dans les deux cas.
  Aucun contenu de réflexion conservé dans les données applicatives.
- Arrêt/reprise de FastAPI, modèle et Vite : High, historique et souvenir
  `AZUR12` retrouvés, puis souvenir correctement utilisé par le modèle réel.
- Commutation Général → Programmation → Général réussie. Run réel
  `3ea6702a-2175-4810-b679-46205399f0e1` sur `Lea_Stage12_20261016` : lectures,
  seule source `calculator.py` modifiée, `python -B -m unittest -v` vert,
  `completed` / `validated`, diff affiché et rollback demandé dans Edge.
  Hash de source restauré exactement ; checkpoint limité aux trois fichiers
  du projet, sans `__pycache__`, `.pyc` ou `.pytest_cache`.
- Préférence sauvegardée pendant ce run, modèle figé inchangé ; sauvegarde
  pendant génération couverte par test API concurrent avec gateway bloqué simulé.
- Refus HTTP réels : origine distante/absente, mauvais format, payload trop gros,
  JSON invalide, valeur inconnue, champs de chemin/commande. SQLite test : écriture
  refusée, base absente/corrompue, ligne absente/invalide, modèle sans capacité,
  concurrent writers et ajout fictif de colonne préservée.
- Base utilisateur : SHA-256 avant/après identique
  `B331FC986282808C19910D64FFF34DA0D530B466B12A061D0CC7E9415F289454`.
  Base de test : intégrité OK, aucune violation de clé étrangère ni marqueur privé
  dans les messages. Données et checkpoints conservés pour audit.

### Limites et clôture

- High reste dans le budget existant et peut échouer sur une question trop longue.
  Aucun mécanisme supplémentaire pour compenser les décisions de Qwen.
- Accept reste couvert automatiquement et validé réellement à l’étape 11 ; pas
  de nouvelle acceptation réelle dans cette étape. Pas de relance du benchmark
  difficile, de troisième modèle, de nouveau moteur ni du scénario Edge historique
  complet de l’étape 8 ; parcours concernés exercés par les scénarios étape 12.
- Avertissement préexistant Starlette/TestClient sur `httpx` : tests réussis,
  aucune installation ou mise à jour opportuniste pour le masquer.
- Un échec temporaire du service d’autorisation (crédits) n’a exécuté aucune
  action ; la reprise autorisée a ensuite permis le test réel. Aucun contournement.
- Ménage final : 363 fichiers du profil Edge de test, 3 fichiers `dist/` et
  13 `.pyc` retirés après contrôle des cibles, sans lien/reparse point. Ces
  artefacts sont régénérables ; aucun fichier source suivi supprimé. Base de
  validation, capture, projet test restauré, checkpoints et volumes conservés.
- Contrôle final : zéro processus Léa/OpenHands/navigateur de test, zéro port
  en écoute parmi 5173/8000/8080/8081/18010/9232, zéro conteneur actif.
  Services de test arrêtés ; Docker Desktop préexistant conservé.
  Aucun commit/push. Étape 12 techniquement terminée, validation manuelle finale
  attendue ; étape 13 non commencée.

## [0.0.11] — Architecture indépendante des modèles

### Modifié

- Registre `config/models.json` au schéma 3 : définitions de modèles séparées
  des profils, association par `model_id`, capacités requises et validation des
  références, budgets et chemins. Les deux Qwen et leurs paramètres sont conservés.
- Adaptateur llama.cpp unique pour les arguments, endpoints, réponses et readiness.
  Les lanceurs existants gardent la propriété des processus ; leur lecture de
  configuration passe par le même validateur Python, sans nouvelle dépendance.
- Template, arrêt de génération et directive `/no_think` rattachés au modèle,
  sans déplacer les contrats, permissions, conversations ou souvenirs.
- OpenHands reçoit l’alias, le contexte, le port et les séquences d’arrêt du
  registre. Le nom API historique `qwen_available` reste compatible avec le
  frontend, mais ne commande aucune logique spécifique à Qwen.
- Retrait des validateurs dupliqués, anciennes fonctions de résolution/hash,
  variables inutilisées et métadonnées de prompt sans consommateur.
- Documentation de remplacement des modèles et roadmap 11–25 actualisées.

### Corrigé

- La preuve de validation reconnaît maintenant `python -B -m unittest` et
  `python -B -m pytest`, uniquement avec une observation terminal authentique
  réussie. Le premier run réel a révélé ce faux négatif ; son checkpoint a été
  restauré, puis deux runs ont été réellement validés. Aucune récupération de
  décision du modèle ni heuristique spécifique à un benchmark n’a été ajoutée.
- Le plancher de contexte du condenser OpenHands est contrôlé dès le chargement
  du registre, et plus seulement au démarrage du runner.

### Validation et limites

- 194 tests backend, 14 tests frontend et build React/TypeScript réussis.
- Tests réels avec les deux modèles : conversations, mémoire après redémarrage,
  commutation, deux petits runs OpenHands, tests verts, Rollback et Accept.
- Substitution et partage de modèles vérifiés avec des configurations de test ;
  aucun troisième GGUF, autre moteur ou parcours visuel Edge complet testé.
- Un arrêt transitoire de llama.cpp Général a été signalé par Windows comme une
  erreur d’accès fichier (`0xc0000006`, information `0xC000026E`). Un redémarrage
  contrôlé, sans changer les paramètres, a permis tous les tests suivants.
  La cause matérielle/stockage n’est pas établie ni déclarée corrigée.
- Base utilisateur inchangée, sécurité/checkpoints préservés, aucune modification
  du laboratoire GLM/Colibrì ni installation supplémentaire. Les limites Qwen de
  l’étape 10 restent acceptées. Validation manuelle finale encore attendue.

## [0.0.10] — Profil Programmation et runs OpenHands

### Ajouté
- Un contrat de fiabilité commun aux profils Général et Programmation, avec des
  règles explicites contre l’invention de fichiers, d’outils, de tests, de
  sources et de résultats.
- Un registre versionné unique pour les profils, prompts, capacités, moteurs et
  limites. Le profil Programmation validé utilise
  `Qwen2.5-Coder-7B-Instruct Q6_K`, une fenêtre de 22 000 tokens, un slot et
  `llama.cpp` b10516 (`b95502ba9`).
- L’intégration locale d’OpenHands SDK / Agent Server 1.43.1 minimal pour les
  runs Programmation ; Agent Canvas n’est pas une dépendance de fonctionnement.
- Le registre SQLite des projets sous `L:\IA_WORKSPACE`, les runs agentiques et
  leurs checkpoints. Seul le résumé utile du run est conservé dans SQLite ; le
  journal détaillé reste dans l’état OpenHands.
- La consultation des changements, leur acceptation et le rollback complet des
  fichiers créés, modifiés ou supprimés par un run.

### Sécurisé
- Un run fige immuablement son `project_id` et son chemin canonique : une autre
  sélection de projet ne peut pas rediriger un run en cours.
- La racine autorisée est exactement `L:\IA_WORKSPACE` ; remontées, chemins
  absolus extérieurs, autres lecteurs, UNC, liens et reparse points sont refusés.
- Les changements externes détectés avant un rollback deviennent un conflit au
  lieu d’être écrasés silencieusement. L’annulation attend l’arrêt effectif du
  run avant d’être annoncée comme terminée.
- Aucun modèle cloud ni modèle local de secours n’est utilisé. Docker Desktop
  reste un prérequis manuel ; Léa ne le démarre pas automatiquement.
- Mise à niveau vers FastAPI 0.141.1 et Starlette 1.6.0 afin de retirer les avis
  de sécurité associés à l’ancienne Starlette 0.46.2.
- Les réponses locales ne sont plus mises en cache et refusent le framing, le
  MIME sniffing, le DNS rebinding et la transmission d’un referrer vers un tiers.
- La politique OpenHands refuse désormais les cibles `file_editor` hors du
  projet ainsi que les sorties terminal explicites de `/workspace`.
- Avant de réutiliser un conteneur OpenHands, Léa vérifie aussi son utilisateur,
  sa commande, son port loopback, ses limites de ressources et sa politique de
  redémarrage. Les processus OpenHands utilisent la table de coûts LiteLLM
  embarquée sans requête distante implicite ; les exécutables Windows système
  sont lancés par leur chemin absolu plutôt que depuis le dossier courant.

### Nettoyé
- Suppression de l'ancienne boucle agentique maison, de son tool calling et de
  ses exécuteurs fichiers/terminal devenus sans appel depuis l'intégration
  OpenHands, ainsi que de leurs tests exclusivement historiques.
- Ajout de commentaires et docstrings naturels aux fonctions applicatives, puis
  aération du frontend et du lanceur sans changement de comportement.
- Retrait de deux imports Python et de règles CSS sans usage ou sans effet.

### Validé
- Commutation réelle Général ↔ Programmation, disponibilité Qwen/OpenHands et
  absence de dépendance à Agent Canvas pour le fonctionnement normal.
- Runs OpenHands réels sur projets Python et React/TypeScript : lecture,
  outils, correction, retest vert, rapport final, checkpoint puis rollback.
- Persistance des conversations, souvenirs, runs et checkpoints après le
  redémarrage du backend, avec les garanties de l’étape 9 conservées.
- Tests de confinement, annulation, conflit externe, prompt injection et
  non-régressions backend, frontend et build.

### Limitation connue
- Qwen2.5-Coder-7B peut échouer sur des tâches agentiques multi-fichiers longues lorsque file_editor exige des remplacements textuels exacts. Léa détecte ces boucles, refuse les mutations invalides, valide les changements par des tests et peut restaurer le checkpoint.
- `Lea_FinalValidation_Test` reste un benchmark difficile destiné à la future
  comparaison de GLM-5.3-Flash avec Qwen ; il n'est plus une barrière de
  clôture de l'étape 10.

## [0.0.9.2] — Mémoire globale et reprise de saisie

### Corrigé
- Les souvenirs explicites restent globaux après la suppression de leur
  conversation d’origine ; seule une commande exacte `Oublie que` les retire.
- La provenance SQLite devient informative et accepte un souvenir sans source.
- Après la suppression d’une conversation, le focus revient automatiquement
  dans la zone de question afin que la saisie clavier reste immédiate.

### Validé
- Suppression de la dernière conversation, saisie Edge réelle, persistance au
  redémarrage et oubli global depuis une autre conversation.

## [0.0.9.1] — Provenance et suppression définitive — remplacée en 0.0.9.2

### Corrigé
- Ajout de la migration SQLite v3 et de `memory_sources` pour rattacher chaque
  souvenir explicite à sa ou ses conversations sources.
- Suppression atomique du souvenir quand sa dernière conversation source est
  supprimée depuis l’interface ; un fait ayant une autre source est conservé.
- Migration des sources v2 encore vérifiables et purge des souvenirs déjà
  orphelins qui continuaient auparavant à être injectés au modèle.

### Validé
- Suppression, redémarrage, oubli exact, doublons multi-conversations,
  transactions, concurrence, modèle réel et Microsoft Edge Stable.

## [0.0.9] — Mémoire générale explicite

### Ajouté
- Migration SQLite v2 avec table indépendante `memories`, clé normalisée unique
  et classification des tours de conversation ou de gestion mémoire.
- Commandes françaises explicites de mémorisation et d’oubli, confirmations
  déterministes et conservation de la mémoire après suppression de la source
  (ancien comportement, remplacé par la correction 0.0.9.1).
- Injection de tous les souvenirs actifs comme données JSON échappées, avec une
  capacité dédiée de 1 800 tokens estimés et sans troncature silencieuse.
- Tests du parser, des transactions, de la concurrence, de la capacité, du
  payload modèle, du modèle réel et de Microsoft Edge Stable.

### Sécurisé
- Mémorisation et oubli atomiques, sans appel au modèle et avec révision
  obligatoire pour une conversation existante.
- Oubli limité à l’égalité normalisée exacte, sans fuzzy matching ni suppression
  sémantique.
- Tours mémoire visibles et copiables, mais exclus du contexte modèle et non
  modifiables ou régénérables comme des tours normaux.
- Prévalidation mémoire + contexte avant une modification ou régénération
  destructive, afin de conserver l’ancienne réponse en cas de dépassement.

### Validé
- Mémoire disponible entre conversations et après redémarrage du cœur ; la
  conservation après suppression de la source décrite dans cette version est
  remplacée par la provenance de 0.0.9.1.
- Migration v1 vers v2 sans perte, WAL, intégrité et clés étrangères valides.
- Non-régression des conversations de l’étape 8, de la fenêtre 8 192, des
  protections PID/ports et de la libération de la VRAM.

## [0.0.8] — Conversations locales persistantes

### Ajouté
- Base SQLite locale avec migrations transactionnelles, WAL, clés étrangères,
  contraintes, index et chemin de test `LEA_DB_PATH`.
- API de conversations avec liste, recherche, lecture, renommage, suppression,
  réessai, modification destructive et régénération destructive.
- Interface persistante avec restauration par URL, gestion des échecs et
  protection des conflits entre onglets.
- Tests backend, frontend et scénario réel Microsoft Edge Stable.

### Modifié
- Fenêtre du modèle portée à 8 192 tokens avec un seul slot.
- Suppression des options de raisonnement ; `/no_think` est ajouté uniquement
  à la requête interne et les marqueurs de pensée sont filtrés défensivement.
- Le backend devient l’unique autorité de l’historique envoyé au modèle.

### Validé
- Persistance après actualisation et redémarrage du cœur.
- Reprise sûre après interruption, révisions concurrentes et cascades SQLite.
- Deux cycles complets de démarrage et d’arrêt, avec libération des ports et de
  la VRAM.

## [0.0.1] — Préparation

### Ajouté
- Dépôt Git créé.
- SSD préparé.
- Dossier `Projet_Lea` créé.
- Dossier `IA_WORKSPACE` créé.
- Stratégie de développement incrémentale définie.
- Instructions initiales pour Codex préparées.

### État
Aucun code applicatif n'a encore été développé.
