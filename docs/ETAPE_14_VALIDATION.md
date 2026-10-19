# Étape 14 — Microphone et conversation vocale

Date des essais : 17 octobre 2026. Base Git : `24fb63b` (étape 13).
Vérification finale des données, ménage et rétablissement : 18 octobre 2026.
Périmètre : voix locale uniquement. Aucune étape 15, vision, VAD ou mains libres.

## Verdict

`ETAPE_14_VALIDEE`

L’implémentation et les essais techniques sont complétés par la validation
manuelle de l’utilisateur du 18 octobre 2026 : les deux voix fonctionnent dans
Léa, les paramètres sont corrects et la voix naturelle retenue lui convient.
Les essais navigateur synthétiques ci-dessous restent identifiés comme tels ;
ils ne sont pas réécrits rétroactivement comme des essais physiques.

## Tableau 14A à 14L

| Sous-étape | Statut | Modifications et tests | Limites |
| --- | --- | --- | --- |
| 14A — Audit/choix | Réalisée | D-030/D-031, accord 10 Go, moteurs CPU installés et mesurés | Comparaison documentaire des alternatives, pas de benchmark de moteurs non installés |
| 14B — Capture | Validée | MediaRecorder, deux clics, pistes arrêtées avant décodage, annulation, limite 120 s ; vrais appels Edge sur périphérique synthétique et validation manuelle finale | Les mesures automatisées n’utilisent toujours pas l’audio privé |
| 14C — Dictée | Validée techniquement | Whisper réel, brouillon et édition pendant STT préservés, envoi manuel, aucune lecture TTS ; cœur arrêté testé | Transcription imparfaite : relecture nécessaire |
| 14D — Vue vocale | Validée techniquement | Vue séparée, états seulement, aucun message/transcription/champ affiché | Pas de refonte visuelle |
| 14E — Tours vocaux | Validée techniquement | Second clic → STT → endpoint existant → réponse → TTS avec Général et Programmation ; aucune reprise automatique du micro | Le dernier run vocal rend un échec, pas un faux succès ; un run autorisé continue si l’audio est fermé |
| 14F — Synthèse/lecture | Validée | Pocket TTS et Piper réels, français, Web Audio, interruption et nouveau tour ; les deux voix et la qualité de Léa confirmées manuellement | Pocket TTS conserve sa vitesse native fixe à 1× |
| 14G — Historique | Validée techniquement | SQLite existant, migration 10, paire agentique atomique/idempotente, rechargement et redémarrage | Pas de conservation audio |
| 14H — Profils/sécurité | Validée techniquement | Général Low/High, chaîne vocale OpenHands avec échec explicite/Rollback ; run écrit corrigé/testé/validated puis Accept | Aucun run vocal de correction déclaré validated ; forme de commande choisie par Qwen non reconnue |
| 14I — Paramètres | Validée | Valeurs bornées, voix installées, conflit visible, sauvegarde explicite, volume/High persistés après arrêt complet et paramètres confirmés manuellement | Le périphérique choisi reste une préférence locale du navigateur |
| 14J — Ressources | Mesurée | STT/TTS avec les deux profils, RAM/CPU/VRAM, chargement et latences ; moteurs libérés entre opérations | Variations RAM/CPU système, pas attribution exclusive au worker |
| 14K — Qualité/tests | Suites techniques passées | Suites finales backend/frontend, build, PowerShell, scénarios Edge et documentation | Avertissement Starlette/httpx préexistant |
| 14L — Arrêt/bilan | Terminée | Relecture, ménage ciblé, données préservées, services de test arrêtés, Git contrôlé et validation manuelle confirmée | Aucun commit/push |

## Moteurs, installation et licences

L’autorisation explicite « télécharge tout ce dont tu as besoin jusqu’à 10 Go »
succède à l’audit sans installation D-030. Environ 325 Mo téléchargés ; ensemble
installé mesuré à 458 544 250 octets (~437,3 Mio), archive comprise. Aucune
modification des GGUF, du contexte ou du runtime conversationnel.

| Ressource | Version/taille | Emplacement | Provenance/licence |
| --- | --- | --- | --- |
| whisper.cpp CPU | b5130, archive 8 573 270 octets | `runtime/voice/whisper.cpp/Release/whisper-cli.exe` | [Release officielle](https://github.com/ggml-org/whisper.cpp/releases/tag/b5130), MIT |
| Whisper Small Q5_1 multilingue | 190 085 487 octets | `models/voice/ggml-small-q5_1.bin` | [Poids](https://huggingface.co/ggerganov/whisper.cpp/tree/main), révision `5359861c739e955e79d9a303bcbc70fb988958b1`, MIT |
| Piper CPU | 1.8.0, wheel Windows 34 119 688 octets | `runtime/voice/.venv/` | [Piper](https://github.com/OHF-Voice/piper1-gpl), [distribution](https://pypi.org/project/piper-tts/1.8.0/), GPL-3.0-or-later |
| SIWIS medium français | ONNX 63 201 294 octets, JSON 4 875, carte 284 | `models/voice/fr_FR-siwis-medium.onnx`, `.onnx.json`, `MODEL_CARD` | [Carte de voix et attribution](https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD), révision `c10ece1aade47bb51c153c893d14e5bf8e5b7117` ; dépôt MIT, corpus CC-BY 4.0 |

Le corpus SIWIS est attribué conformément à sa carte conservée localement ; la
licence MIT du dépôt ne remplace pas la licence CC-BY 4.0 indiquée pour le corpus.
Le moteur eSpeak embarqué par Piper relève également de la famille GPL.

Dépendances exactes dans `tools/voice/requirements.txt` : pydantic 2.13.4,
pydantic-core 2.46.4, annotated-types 0.8.0, flatbuffers 25.12.19, numpy 2.5.4,
onnxruntime 1.31.0, packaging 26.3, pathvalidate 3.3.1, protobuf 7.36.2,
typing-extensions 4.16.0, typing-inspection 0.4.4. Métadonnées installées :
MIT pour Pydantic/core, annotated-types, ONNX Runtime, pathvalidate et
typing-inspection ; Apache-2.0 pour flatbuffers ; Apache-2.0 OU BSD-2-Clause
pour packaging ; BSD-3-Clause pour protobuf ; PSF-2.0 pour typing-extensions ;
NumPy déclare BSD-3-Clause, 0BSD, MIT, Zlib et CC0. Environnement Python 3.12.10.

Installation administrative explicite : `./tools/voice/install.ps1`.
Versions figées, archives/poids vérifiés, environnement séparé du backend,
pas de PyTorch/CUDA ajouté. Les empreintes et fichiers techniques sont dans
l’unique `config/models.json`. Aucun téléchargement pendant l’utilisation normale.

Choix : Small quantifié reste modeste en RAM, Piper ajoute une seule voix CPU.
Les mesures ne justifient pas un second moteur résident ou les candidats plus
lourds. La qualité de reconnaissance est imparfaite, et le naturel de SIWIS
ne peut pas être certifié sans écoute physique. Pas de correction inventée de STT.

## Utilisation et conservation

Sous la zone de question, **Dicter au microphone** démarre la capture ;
**Terminer la dictée** libère les pistes puis transcrit. Le texte s’ajoute au
brouillon courant en préservant les éditions. Relire et envoyer soi-même.
Annuler ne modifie ni brouillon ni projet. La dictée fonctionne avec Vite seul.

**Conversation vocale** ouvre la vue sans messages. **Parler à Léa** capture ;
**Terminer et envoyer** transcrit et transmet au profil figé. États : autorisation,
écoute, transcription, traitement, synthèse, lecture, prêt ; erreurs explicites.
Le microphone reste éteint pendant traitement/lecture et après la réponse.
**Arrêter la lecture** ou fermer la vue libère l’audio, sans supprimer la réponse.
Le dépassement de 120 secondes annule ; il ne déclenche jamais un envoi.

Général utilise les endpoints, révisions, mémoire et historique existants.
Programmation utilise exclusivement OpenHands : contexte figé au serveur,
checkpoint et validation inchangés. Une paire de messages liée au run reste
dans le même historique ; la réponse terminale est actualisée sans duplication.
Ces messages ne peuvent pas être rejoués par les actions ordinaires du chat.
Le bouton **Examiner le run et le diff** ramène à la validation visuelle ; aucune
acceptation/restauration automatique. Fermer l’audio ne signifie pas arrêter
le run : consulter son état et son bouton d’annulation dans l’interface classique.

La lecture des blocs de code ou textes dépassant 6 000 caractères/60 lignes
est annoncée comme partielle ; le texte complet reste dans l’historique.
Les enregistrements et WAV générés restent en RAM, jamais dans SQLite ou un
fichier audio applicatif. Les WAV synthétiques des tests sont des fixtures
explicitement créées, pas des enregistrements privés.

## Préférences

SQLite `user_preferences`, migration additive 10, sauvegarde explicite **Valider** :

| Réglage | Défaut | Effet réel |
| --- | --- | --- |
| Microphone | Périphérique système | deviceId exact si choisi ; absence signalée |
| Langue | Français | STT français ou anglais |
| Lecture vocale | Activée | TTS seulement en conversation vocale |
| Voix | Première installée | SIWIS française ; aucun choix fictif |
| Volume | 100 % | Gain Web Audio 0–1 |
| Vitesse | 1× | Synthèse 0,75–1,5× |

Les labels de périphériques nécessitent une autorisation explicite ; le flux de
recensement est immédiatement fermé. Aucun réglage artificiel de sensibilité.
Low/High et diagramme facultatif restent indépendants, même IA arrêtée.

## Mesures réelles

i7-13700H, 20 processeurs logiques, RAM 31,66 Gio, RTX A1000 Laptop 6 Gio.
CPU vocal : quatre threads, ONNX CPU uniquement ; Qwen inchangé.
Les deltas RAM sont obtenus via les compteurs système de l’étape 13 à 0,5 s
pendant l’essai seulement. Les autres applications, Docker et caches peuvent
les faire varier : **ce ne sont pas des mesures de mémoire privée des workers**.

| Profil/audio synthétique | STT total / chargement | Pic delta RAM STT / CPU système | TTS total / chargement | Pic delta RAM TTS / CPU système |
| --- | --- | --- | --- | --- |
| Général 3,40 s | 3,266 s / 173 ms | 486,9 Mio / 22,6 % | 2,562 s / 2 157 ms | 132,6 Mio / 6,8 % |
| Général 8,42 s | 3,828 s / 172 ms | 498,5 Mio / 27,1 % | 2,984 s / 2 422 ms | 144,1 Mio / 18,9 % |
| Général 31,50 s | 7,828 s / 171 ms | 510,6 Mio / 26,0 % | 3,297 s / 2 156 ms | 228,0 Mio / 28,5 % |
| Programmation 3,32 s | 4,094 s / 188 ms | 1 001,8 Mio / 44,7 % | 4,391 s / 2 672 ms | 244,6 Mio / 27,7 % |
| Programmation 8,50 s | 5,203 s / 238 ms | 706,5 Mio / 51,4 % | 4,125 s / 3 422 ms | 2 143,8 Mio / 50,7 % |
| Programmation 31,68 s | 10,562 s / 226 ms | 615,8 Mio / 46,7 % | 4,672 s / 2 844 ms | 392,1 Mio / 41,1 % |

VRAM avant/après chaque opération : 3 780 Mio Général et 4 268 Mio Programmation,
soit **0 Mio supplémentaire observé** ; échantillonnage aux bornes, pas garantie
d’un pic transitoire nul. Au repos, aucun worker/Whisper résident. L’ouverture
de la vue ajoute 38 880 octets de heap JS après GC (3 203 000 → 3 241 880),
pas une mesure exhaustive du surcoût natif du navigateur par rapport à l’étape 13.

Tour Général Edge : STT 4 895 ms, réponse modèle 1 532 ms, TTS HTTP 2 786 ms,
début de lecture ~2 790 ms après demande TTS. Du second clic/demande STT au
début audio : ~9,48 s, plus ~4 s de capture. La durée de lecture dépend du texte.
Tour Programmation `962f850e-6e08-492f-bcc5-e38cc72e5607` : STT 4 736 ms,
TTS HTTP 4 014 ms, début de lecture ~4 097 ms après demande TTS. Du second clic
au début audio : **91,66 s**, plus ~6,3 s de capture. C’est le retour vocal réel
d’un run **failed**, pas une mesure d’une résolution agentique réussie. Le délai
OpenHands domine ; aucune réduction du contexte modèle pour accélérer ce test.

Qualité observée : phrases françaises comprises, mais confusions « deux »/« de »,
« Python » et répétition finale sur un enregistrement long. Les petits exemples
ne constituent pas un taux d’erreur représentatif d’une vraie voix utilisateur.
Ne pas présenter la transcription comme parfaite ; la dictée reste corrigeable.

## Essais et commandes

Suites automatisées :

```powershell
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -q
npm run test:frontend
npm run build
.\tests\launcher-process-record.ps1
.\tests\launcher-idle-inspection.ps1
git diff --check
git status --short
```

250 backend et 34 frontend passent ; build réussi. PowerShell : six cas
d’identité de processus et deux cas Docker absent/préférence ErrorAction restaurée ;
AST des 12 scripts valide. Avertissement Starlette/httpx préexistant uniquement.

Essais réels sur base isolée `.test-runtime/stage14-20261017/lea.sqlite3` :

- `tests/e2e/voice-stage14.py` via le Python vocal : vrais Piper/Whisper avec
  trois durées par profil, compteurs OS réutilisés, aucun micro physique.
- `tests/e2e/edge-stage14.mjs`, puis `--stopped` : vraie capture MediaRecorder
  synthétique, STT, brouillon modifiable/envoi manuel, deux tours Général, TTS
  local et Web Audio, interruption, rechargement sans doublon, cœur arrêté.
- `tests/e2e/voice-lifecycle.mjs` : vrais refus HTTP (origine/type/méthode/route),
  annulation STT réelle, slot libéré et absence de worker/Whisper orphelin.
- `tests/e2e/edge-stage14-health.mjs` : réponses de sonde **simulées**, vraie UI ;
  une erreur isolée conserve l’audio, trois erreurs l’annulent, reprise visible.
- `tests/e2e/edge-stage12.mjs general/errors/security/persistence` : vrais
  Low/High, mémoire explicite, brouillon, conflit de sauvegarde, historique et
  souvenir après `lea.ps1 stop` puis `start`. Panne réseau du scénario errors
  simulée. Sélecteur de confirmation rendu précis pour ne pas lire une notice vocale.
- `tests/e2e/edge-stage14-programming.mjs` : essai vocal sur le seul projet
  `L:\IA_WORKSPACE\Lea_Stage14_20261017`, jamais un projet utilisateur.
  Son attente de résolution `completed/validated` a échoué : cette assertion
  n’est pas présentée comme réussie. La chaîne audio complète et son retour
  `failed` sont consignés dans `browser-programming-feedback.json`.
- `tests/e2e/edge-stage14-accept.mjs` : retour visuel depuis le run vocal échoué,
  Accept absent, Rollback réel ; nouveau run **écrit** avec commande explicite,
  source seule modifiée, test vert reconnu, validation et Accept réussis.
- `tests/e2e/edge-stage14-failure-notice.mjs` : résultat de run **simulé** à partir
  d’un échec réel conservé, sans nouveau run ; failed reste visible si TTS est
  désactivé ou si la synthèse échoue. Le transport audio/STT reste réel.
- Diagramme réel et absence de débordement à 390 px confirmés en Programmation
  puis Général ; sondes Docker adaptées. `edge-stage13.mjs stoppedResources`
  vérifie également l’absence de lectures et de valeurs inventées cœur arrêté.

Bilan des cinq runs réels : quatre runs vocaux `failed`, checkpoints
`rolled_back` ; run écrit `dfc18246-08d1-41dc-b8d2-91a5d6dc54eb`
`completed/validated`, checkpoint `accepted`. Test source `test_app.py` inchangé
(SHA-256 `ee5441804f2ea6d727ec32e7b1c9eb598cc1c4c020c9ecfb1d073e49856d02ce`).
Rollback vérifié contre le SHA initial de `app.py`
`1ca19db9b478e3f5fce2c32651cbbc45430ab11b39f89935c1a4279c18af6f82`.
Les 13 entrées des cinq checkpoints sont uniquement sources/README : aucun
`__pycache__`, `.pyc`, `.pyo` ou `.pytest_cache`.

Prérequis Edge : navigateur de test headless séparé, CDP loopback via
`LEA_EDGE_CDP_PORT`, `--use-fake-device-for-media-stream`,
`--use-fake-ui-for-media-stream`, `--use-file-for-fake-audio-capture=...`,
`--mute-audio`. Ce contournement de permission est **uniquement un paramètre du
navigateur de test**, jamais du lancement normal de Léa. Les fichiers E2E
documentent les assertions et les fixtures requises ; ne pas les lancer sur la
base habituelle. Docker Desktop doit être ouvert manuellement pour Programmation.

## Problèmes constatés et corrections ciblées

- Whisper Windows `-of -` écrit dans CON, pas dans le stdout redirigé. Utilisation
  des segments stdout sans drapeau d’écriture de fichier ; entrée par pipe.
- Lecture stdin bloquante en concurrence avec les bibliothèques natives :
  gardien propriétaire via PeekNamedPipe limité à la durée du worker ; job
  Windows tue ses enfants en cas de fermeture/annulation.
- Sonde de santé ponctuellement en erreur sous charge Programmation : réutilise
  la tolérance existante aux échecs consécutifs ; arrêts explicites immédiats,
  panne persistante visible et audio annulé. Aucun garde-fou Docker assoupli.
- Quatre premiers runs vocaux : mutation source, mais aucune preuve de validation
  reconnue par la règle stricte ; états `failed`/validation `failed`, non acceptables,
  restaurations exactes. Le troisième a effectivement exécuté
  `python3 /workspace/test_app.py` avec un test OK/code 0 : cette forme directe
  n’est pas reconnue comme commande de validation par Léa. Ne pas confondre
  « test réellement passé » et « preuve acceptée par le validateur ». Aucun
  élargissement du validateur ni mécanisme pour corriger les décisions de Qwen.
  Le projet jetable possède maintenant un README donnant sa commande de test
  conventionnelle ; aucun comportement métier conditionné au nom du test.
- Après tolérance aux sondes isolées, un essai encore trop chargé a subi trois
  échecs consécutifs et l’audio a été annulé conformément au garde-fou. Le dernier
  essai isolé, sans autres suites ni second navigateur de test, a terminé STT,
  OpenHands, historique et TTS ; retour visuel explicite, Accept absent et Rollback
  confirmés. Les états failed/validation restent visibles même lecture désactivée
  ou TTS indisponible, sans afficher les messages dans la vue vocale.

Limitation antérieure conservée : Qwen2.5-Coder-7B peut échouer sur des tâches
agentiques multi-fichiers longues lorsque file_editor exige des remplacements
textuels exacts. Léa détecte ces boucles, refuse les mutations invalides, valide
les changements par des tests et peut restaurer le checkpoint.

## Validation physique à effectuer

1. Démarrer avec `./lea.ps1 start`, copier `http://127.0.0.1:5173` dans une fenêtre
   **Edge externe**, pas le navigateur intégré VS Code (voir diagnostic ci-dessous). Dans Paramètres,
   autoriser/lister les microphones, choisir le vrai périphérique, volume audible,
   français et « Léa — Voix naturelle française », puis Valider. Vérifier aussi
   que « SIWIS — Voix classique » reste sélectionnable. Aucun voyant de capture
   ne doit rester allumé.
2. Dicter une phrase française technique au milieu d’un brouillon. Arrêter au
   second clic : vérifier le voyant éteint, la transcription et la conservation
   du brouillon ; corriger puis Envoyer. Aucun son ni envoi automatique en dictée.
3. Général : ouvrir Conversation vocale ; vérifier l’absence de texte des échanges.
   Parler/terminer avec la voix Léa, écouter la réponse réelle contenant notamment
   « Stan », juger français/ponctuation/naturel,
   interrompre, refaire un tour, fermer. Aucun rallumage automatique du microphone.
4. Refuser l’autorisation puis la rétablir, tester un microphone débranché, annuler
   pendant capture/STT, tester silence et limite 120 s. Vérifier erreurs lisibles,
   aucune transcription inventée, aucun son/piste restant après fermeture.
5. Docker ouvert manuellement, sélectionner Programmation et un projet jetable
   sous `L:\IA_WORKSPACE`. Faire une petite demande vocale ; écouter le résultat,
   revenir explicitement au diff, puis décider Accept ou Rollback. Ne pas employer
   un projet sensible pour cet essai de transcription.
6. Revenir aux conversations, recharger puis redémarrer Léa : texte, préférences
   et souvenirs conservés. Vérifier diagramme facultatif dans les deux profils,
   Low/High et absence de lecture automatique. Cœur arrêté, tester la dictée seule.

## Fichiers, données, nettoyage et état final

Créés : `backend/app/voice.py`, `backend/tests/test_voice.py`,
`src/voice.ts`, `src/VoiceControls.tsx`, `src/VoiceSettings.tsx`,
`tools/voice-controller.ts`, `tools/voice/{worker.py,install.ps1,requirements.txt}`,
tests vocaux frontend/E2E, fixture source sous `tests/fixtures/voice-project`,
test PowerShell d’inspection idle et ce rapport. Le prompt 14 fourni par
l’utilisateur est conservé intact.

Modifiés : `config/models.json`, `vite.config.ts`, `lea.ps1`,
`backend/app/{database,main,migrations,model_registry,openhands_runs,preferences}.py`,
tests backend associés, `tools/preferences.py`, `src/{App,Settings}.tsx`,
`src/{conversations,preferences}.ts`, `src/index.css`, tests préférences et
sélecteurs E2E existants, `.gitignore`, AGENTS/README/TODO/CHANGELOG/DECISIONS
et README backend. Commentaires/docstrings de cycle de vie, opérations sensibles
et fonctions significatives ; retrait des seuls blocs de test dupliqués et
mise en forme ciblée du SQL ajouté, sans refonte de l’architecture.

Les sources sont conservées ; aucun fichier utilisateur ni checkpoint supprimé.
Sauvegarde de reprise avant essais : `.test-runtime/stage14-backup-reprise-20261017/`.
La base habituelle comptait alors 0 conversation, 0 message, **1 souvenir**,
158 runs et 158 checkpoints : ne pas la remplacer par la sauvegarde initiale
plus ancienne sans ce souvenir. Les essais utilisent une base distincte.

### Données et rétablissement vérifiés le 18 octobre

Avant rétablissement, la base habituelle et sa sauvegarde de reprise ont le même
SHA-256 : `f2caa1ada8047b3be49f318291c906eedd741780683d0e5cc8966ac81fe127d5`.
Après redémarrage habituel, comparaison SQLite en lecture seule : conversations
(0), messages (0), souvenirs (1), sources de souvenirs (0), runs (158),
checkpoints (158), fichiers de checkpoint (2 684) et préférences (1 ligne)
strictement identiques à la sauvegarde. Aucune restauration d’une ancienne base.

Les services exclusivement lancés pour les essais sont arrêtés. La session
habituelle a été rétablie avec `./lea.ps1 start`, sans `LEA_DB_PATH` de test :

| Composant | État final constaté |
| --- | --- |
| Frontend Vite | Actif sur 127.0.0.1:5173, PID 19704 |
| Backend FastAPI | Actif sur 127.0.0.1:8000, PID 27412 ; `/health` = ok |
| Général | Actif/prêt sur 127.0.0.1:8080, PID 26560 ; aucune génération |
| Programmation | Inactif ; aucun run ni récupération en attente |
| STT/TTS | Installation disponible, aucun worker ni Whisper résident |
| Microphone/lecture de test | Fermés avec les navigateurs isolés ; aucune capture restante dans ces sessions |
| OpenHands | Aucun runner ni conteneur actif ; port 18010 fermé |
| Docker Desktop | Laissé ouvert, conformément à son ouverture manuelle ; aucun conteneur en cours d’exécution |
| Navigateurs de test | Fermés, ports CDP 9234/9235 libérés ; navigateur personnel non manipulé |
| Surveillance | Général actif, RAM/CPU/VRAM disponibles, niveau NORMAL au relevé final |

Les quatre conteneurs de runs échoués restent arrêtés avec leurs diagnostics,
selon la politique existante ; aucun prune. Le conteneur du run validé a été
supprimé par son cycle de vie normal. Projet de test accepté, checkpoints,
base isolée, preuves JSON et sauvegardes conservés.

### Ménage ciblé et Git

Suppression après vérification des chemins et fermeture des propriétaires :

- `dist/`, trois fichiers régénérables par le build ;
- `backend/tests/tmpdnd6iak4/`, uniquement deux bases SQLite temporaires de tests ;
- les profils Edge `edge-general/` et `edge-programming/` sous
  `.test-runtime/stage14-20261017/`, environ 1 Go de données de navigateur jetable ;
- les deux fixtures `synthetic-question.wav` et `synthetic-programming.wav`
  du même dossier, produites par les essais, sans enregistrement utilisateur.

Ces artefacts sont supprimés directement, mais peuvent être recréés par les
tests/build ; aucun fichier source, modèle, historique ou checkpoint supprimé.
Les répertoires et WAV de test doivent être recréés avant de rejouer les E2E.
Les environnements vocaux et poids restent installés pour l’utilisation locale.

Le registre hors section `voice` est identique au commit de référence.
`git status --short` ne contient que les sources, tests et documents attendus,
dont le prompt utilisateur initial non suivi. Aucun cache, fichier audio,
base SQLite, poids, binaire ou fichier sensible détecté dans les fichiers
suivis/non ignorés qui pourraient être ajoutés ; le plus gros fait moins de
91 Ko. Les poids, environnements, preuves et sauvegardes restent ignorés.
`git diff --check` passe ; seuls les avertissements de normalisation LF/CRLF
habituels apparaissent. Aucun commit, aucun push. À cette passe, la validation
physique restait attendue ; elle est désormais confirmée dans le verdict final
du présent rapport. Aucune autre étape n’est commencée.

## Complément du 18 octobre — erreur de décodage avec le microphone utilisateur

L’utilisateur a signalé `Unable to decode audio data`, puis le diagnostic
WebM/Opus, 30 165 octets, 2 092 ms, conteneur EBML. Il a ensuite précisé utiliser
le **navigateur intégré de VS Code**, et non Edge externe. Aucun enregistrement
privé n’a été recueilli ou sauvegardé pour le diagnostic.

### Cause reproduite, distincte de la finalisation

Une même séquence WebM/Opus synthétique complète, produite par MediaRecorder,
a été décodée successivement dans Edge 155.0.4283.45 puis dans un renderer d’une
instance VS Code **jetable**, 1.140.0 / Electron 43.7.3 / Chromium 150.0.7871.250 :

| Vérification | Edge externe | VS Code isolé |
| --- | --- | --- |
| WebM/Opus identique, 11 888 octets | Décodage réussi, 0,72 s | `EncodingError: Unable to decode audio data` |
| WAV PCM synthétique | Format de transport testé jusqu’à Whisper | Décodage réussi, 1 s |
| Prise en charge annoncée d’Opus | Enregistrement/décodage testés | `isTypeSupported=true`, `canPlayType=probably` malgré l’échec |

Ce n’est donc pas une preuve d’audio WAV reçu par Whisper : le refus survient
dans `AudioContext.decodeAudioData`, **avant conversion en WAV et avant la
requête HTTP**. La capture Opus est disponible dans VS Code, son décodeur ne
l’est pas dans cette installation. Les annonces de capacité ne suffisent pas.
Le [plan de test Microsoft](https://github.com/microsoft/vscode/issues/180780)
classe Opus parmi les formats non pris en charge ; la
[documentation Webview](https://code.visualstudio.com/api/extension-guides/webview#supported-media-formats)
documente un ensemble limité de codecs. Le navigateur intégré n’est pas Edge.

L’hypothèse initiale d’un arrêt trop rapide ne correspond pas au relevé utilisateur.
L’attente de finalisation a été durcie, mais son nouvel essai a confirmé que
cela ne corrigeait pas l’erreur du navigateur intégré. Ne pas présenter ce
durcissement comme la cause prouvée de son incident.

### Correctif et vérification de la chaîne

- Message de décodage expliquant d’ouvrir Léa dans une **fenêtre Edge externe**,
  sans dissimuler l’échec, changer de codec en secret, renommer un WebM en WAV
  ou ajouter une bibliothèque de décodage à VS Code/Léa.
- Préférence WebM/Opus seulement si MediaRecorder l’annonce disponible ; MIME
  réellement produit, tailles des morceaux, taille totale, durée écoulée,
  signature du conteneur et fin du recorder observés. La signature n’est pas
  prétendue suffisante pour valider l’intégralité du fichier.
- Assemblage de tous les morceaux jusqu’au dernier `dataavailable`, puis
  événement `stop` ; libération des pistes avant décodage. Délai de finalisation
  borné à 3 s, sans transmission d’un fichier partiel ; annulation immédiate.
- Décodage du conteneur dans Edge, rendu mono 16 kHz puis encodage WAV PCM16.
  Transport JSON/base64 vers le contrôleur Vite existant, validation Python et
  Whisper CPU par pipe. Aucun changement du contrat backend ni nouveau serveur.
- Console locale `[Lea microphone]` : métadonnées seulement, aucun audio,
  transcript, label ou identifiant de périphérique ; aucune journalisation
  durable ou transmission de ces diagnostics. Un échec ne crée aucune transcription.

### Non-régression

251 tests backend et 40 frontend réussis, build et `git diff --check` réussis.
Les nouveaux tests contrôlés vérifient les derniers morceaux retardés, l’arrêt,
l’annulation pendant finalisation, son délai, les captures vides/courtes,
les erreurs de décodage et le nettoyage. Les tests backend confirment qu’un
conteneur compressé ou un WAV incomplet ne lance jamais Whisper.

`tests/e2e/edge-stage14-recorder.mjs` génère un signal parlé **synthétique** via
Piper, capturé par le vrai MediaRecorder d’Edge, en WebM/Opus puis MP4/AAC.
Le même helper de capture accepte le format réel, même différent du format
demandé lors du test. Exemples mesurés : WebM 59 135 octets / 3,66 s devient
117 164 octets de WAV ; MP4 62 786 octets / 3,754 s devient 120 184 octets de WAV.
Whisper transcrit réellement les deux. Les conteneurs non convertis et WAV
tronqués sont refusés en HTTP 422 ; un en-tête tronqué reproduit `EncodingError`.
Tous les morceaux arrivent avant `stop`, et toutes les pistes sont ensuite fermées.

Les deux modes du composant **de production** sont exercés : dictée sans envoi
automatique, puis conversation avec STT/TTS réels, lecture interrompue et réponse
conversationnelle **simulée**. Aucun modèle conversationnel, projet ni historique
utilisateur n’est modifié. Le test tourne sur une base Vite isolée.
`tests/e2e/voice-codec-host.mjs` permet de rejouer la comparaison Edge/hôte intégré
via deux ports CDP de test ; ses fixtures synthétiques restent en RAM.

Fichiers de ce correctif : `src/voice.ts`, `tests/frontend/voice.test.ts`,
`backend/tests/test_voice.py`, les deux scripts E2E ci-dessus, README, CHANGELOG
et ce rapport. Aucune dépendance ajoutée, aucun moteur/modèle/poids modifié.
La compatibilité avec le navigateur intégré VS Code **n’est pas implémentée**.
La validation physique doit être refaite dans Edge ; elle n’est pas déclarée
réussie par ces tests synthétiques. Aucun commit/push.

Fin de ce complément : Léa était arrêtée au début du diagnostic (aucun listener
5173/8000/8080). Seul Vite a été lancé pour les essais, avec
`.test-runtime/voice-decode-20261018/lea.sqlite3`, puis arrêté. Aucun modèle
conversationnel ni Docker lancé. Les deux Edge et le VS Code jetables sont
fermés, leurs profils supprimés ainsi que le build régénérable ; le VS Code
habituel n’a pas été arrêté ni modifié. Ports 5173/8000/8080 et CDP 9236–9238
libérés ; aucun worker vocal/Whisper restant. Base de test conservée, aucun
fichier audio créé. Pour le prochain essai manuel : démarrage habituel par
`./lea.ps1 start`, puis adresse copiée dans **Edge externe**.

## Complément du 18 octobre — voix Pocket TTS française retenue

Après écoute comparative par l’utilisateur dans le dossier expérimental isolé,
la variante CPU légère `french` de Pocket TTS 3.3.0 et son état vocal officiel
ont été retenus. Le fichier WAV choisi n’est pas une dépendance de production :
il a uniquement servi à départager les essais. Aucun son, cache, jeton ou chemin
temporaire n’a été copié dans Léa ; le dossier expérimental a été supprimé après
la validation manuelle et une dernière vérification de cette indépendance.

### Intégration et provenance

L’interface expose exactement deux choix : **Léa — Voix naturelle française**,
choix par défaut servi par Pocket TTS, et **SIWIS — Voix classique**, servi par
Piper. Le nom technique de l’état vocal n’est pas présenté à l’utilisateur.
Chaque moteur est déclaré dans l’unique registre `config/models.json`; le worker
vocal sélectionne strictement le moteur demandé et n’effectue aucun repli
silencieux vers l’autre voix.

Les ressources permanentes sont confinées à
`models/voice/pocket-tts/french/`. L’installation administrative explicite
épingle les révisions et vérifie taille et SHA-256 avant usage :

| Ressource | Révision | Taille | SHA-256 |
| --- | --- | ---: | --- |
| modèle `kyutai/pocket-tts` | `d0ebc5deb50bc6b225f686782f124dd37e2dca0a` | 219 029 196 | `dd5fe98f5577ecfd56db9af8057cd05fe20cbc91560042aec8a56cfb01c34995` |
| tokenizer `kyutai/pocket-tts-without-voice-cloning` | `8843db76457a91db32077edf8dfcd1c0e3e755fd` | 246 403 | `6211acffe9cb95172f71f0051f18e26ea305b2b32ea00b331ee976551c70887f` |
| état vocal officiel | `4e1e0a3e611c51c0b4ed8174fc10f32a54644303` | 8 259 384 | `f763800c6865a7c13e3368db7c24345d7ab22abd06c2ca40a3428d14c5357248` |
| configuration locale revue | dépôt Léa | 1 300 | `a6b3976608d7339532b2ee0098a42b49fd07bec36c9a4e704ad27071a0effa0a` |

Le code Pocket TTS est annoncé MIT, les poids Pocket TTS CC-BY 4.0 et les
conditions de la carte Kyutai restent applicables ; la source de l’état vocal
officiel est indiquée CC0 par le fournisseur. Piper/SIWIS conserve ses licences
propres documentées dans le README. Aucun téléchargement n’a lieu au démarrage
normal : `install.ps1` est la seule entrée explicite et le moteur est forcé hors
ligne pendant la synthèse. La configuration locale ne contient aucune URL.

La migration SQLite 11 choisit `lea_voice` pour les installations existantes
sans modifier les autres préférences. Le choix de la voix persiste après
redémarrage. Le volume navigateur reste commun. Piper conserve le réglage réel
0,75–1,5× ; Pocket TTS ne fournit pas ce contrôle, donc sa vitesse est réellement
fixée à 1× et l’interface le dit au lieu de simuler un curseur efficace.

Pocket TTS émet des fragments progressivement en interne. Ils sont assemblés en
mémoire en WAV PCM 24 kHz avant la réponse, comme le contrat ponctuel existant.
Une lecture progressive n’a pas été retenue : elle exigerait un nouveau protocole
et un cycle d’annulation plus complexe sans bénéfice prouvé pour cette étape.

### Mesures et essais automatiques

Les essais réels ci-dessous ont utilisé le worker de production, le modèle CPU
permanent, Whisper réel pour la boucle TTS → STT et le profil Général. La VRAM
est restée inchangée ; aucun chemin CUDA n’est utilisé. Les temps muraux incluent
le démarrage isolé du worker et la vérification d’intégrité des ressources :

| Voix | Texte | Audio | Temps mural | Δ RAM système observé | CPU système max. | Traitement moteur |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Léa / Pocket | court | 3,60 s | 4,86 s | 801 Mio | 8,4 % | 1,23 s |
| Léa / Pocket | moyen | 7,68 s | 5,70 s | 839 Mio | 14,8 % | 2,05 s |
| Léa / Pocket | long | 27,04 s | 9,72 s | 896 Mio | 22,0 % | 6,13 s |
| SIWIS / Piper | court | 3,34 s | 2,69 s | 140 Mio | 17,7 % | 2,39 s |
| SIWIS / Piper | moyen | 8,12 s | 2,73 s | 148 Mio | 8,3 % | 2,44 s |
| SIWIS / Piper | long | 31,65 s | 3,31 s | 211 Mio | 17,4 % | 2,99 s |

La première émission interne Pocket mesurée après chargement arrive en 94 ms ;
le chargement mis en cache dans ce processus prend 453 ms. Ces deux valeurs ne
sont pas présentées comme une latence réseau ou une lecture audio progressive.
La chaîne permanente a également synthétisé sans erreur la phrase française de
présentation contenant « Stan ». La qualité de sa prononciation repose sur
l’écoute du banc d’essai validée par l’utilisateur et doit encore être confirmée
sur l’installation permanente avec ses haut-parleurs.
Le processus vocal reste ponctuel et disparaît après succès, erreur ou
annulation. L’essai d’annulation d’une synthèse Pocket longue libère le slot et
ne laisse aucun worker. Une vitesse autre que 1× est refusée pour Pocket en HTTP
422 ; avec Piper, 1,2× produit effectivement un audio plus court que 0,8×.

Les vérifications finales comprennent **254 tests backend**, **41 tests
frontend**, le build de production et `git diff --check`. Les essais réels
supplémentaires couvrent : synthèses courtes/moyennes/longues avec les deux
moteurs, transcription Whisper, erreurs et absence de repli, annulation,
libération des ressources, contrôles de taille/intégrité, mode hors ligne,
sélection des deux libellés dans Edge, migration et persistance SQLite après
rechargement. Dictée et conversation utilisent le même choix vocal.

Ces essais automatisés ne constituaient pas une validation du microphone
physique ni de la sortie ressentie par l’utilisateur. Cette validation a depuis
été réalisée et acceptée explicitement avec les deux voix et leurs paramètres.
L’étape 14 est terminée ; aucune étape suivante n’est commencée ici.

## Clôture manuelle et suppression du banc d’essai — 18 octobre 2026

L’utilisateur confirme que la validation manuelle de l’étape 14 est réussie :
les deux voix fonctionnent dans Léa, leurs paramètres sont corrects et la voix
naturelle choisie lui convient.

Avant suppression, `L:\Lea_TTS_Estelle_Test_Temp` a été résolu vers ce chemin
exact et contrôlé comme dossier ordinaire. Son inventaire — 28 233 fichiers,
3 180 sous-dossiers et 2 042 109 405 octets — contenait uniquement le banc
d’essai annoncé : `.venv`, caches pip/Hugging Face, scripts, rapports, page
d’écoute, huit WAV expérimentaux, journaux et espace temporaire. Ses dix liens
symboliques Hugging Face étaient relatifs et restaient dans son propre cache.
Le jeton OAuth signalé par le README expérimental faisait partie de ce cache ;
il a été supprimé avec lui. Aucun contenu étranger n’a été détecté.

Les quatre ressources permanentes Pocket TTS ont de nouveau passé leurs tailles
et SHA-256 épinglés. `pip check` ne signale aucune dépendance cassée. Ni les
sources, ni la documentation, ni l’environnement vocal actif, ni une ligne de
commande en cours ne référençaient le chemin expérimental. Une synthèse CPU hors
ligne issue de `runtime/voice/.venv` et `models/voice/` a réussi avant la
suppression. Une seconde synthèse après suppression a produit un WAV de 153 644
octets avec le moteur `pocket-tts`, prouvant l’indépendance de l’installation.

La suppression a visé uniquement `L:\Lea_TTS_Estelle_Test_Temp`. Les modèles
permanents, Piper/SIWIS, SQLite, conversations, mémoire et checkpoints n’ont pas
été touchés. La passe finale obtient 254 tests backend et 41 tests frontend
réussis, ainsi qu’un build Vite réussi et `git diff --check` propre hors
avertissements LF/CRLF habituels. Un cycle `lea.ps1 start`/`stop` a confirmé le
profil Général, STT, TTS et les deux identifiants `lea_voice,fr-siwis`, puis a
libéré les ports 5173/8000/8080. Le build et le cache Python régénérables ont été
retirés après vérification. Aucun commit ni push.

## Maintenance finale avant commit — 19 octobre 2026

La phase B a été effectuée directement par l’utilisateur. La passe Codex n’a
donc supprimé ni recréé aucun élément dans `L:\IA_WORKSPACE` : le chemin canonique
a seulement été contrôlé comme répertoire normal, accessible et vide. Le backend
accepte un catalogue de projets vide et l’interface n’exige aucun projet tant
qu’aucun run n’est demandé. Aucun essai OpenHands réel n’a été relancé dans ce
workspace vide ; Accept/Rollback et la validation réelle restent couverts par
les preuves précédentes, tandis que les suites actuelles couvrent leurs contrats.

L’audit de la base active `data/lea.sqlite3` a trouvé 1 conversation active,
2 messages et 1 mémoire de test, sans message ni provenance orpheline, sans FTS,
archive ou suppression logique. La route du frontend effectuait déjà un vrai
`DELETE`, atomique, avec cascade vers `messages` et `memory_sources`. Les
`agent_runs` mettent seulement leur référence conversation à `NULL` afin de
préserver l’audit et les checkpoints indépendants. La cause des fragments encore
visibles dans un fichier SQLite était physique : `secure_delete=0`, sans défaut
logique des cascades. `secure_delete=ON` est maintenant appliqué sur chaque
connexion et exposé par le diagnostic des pragmas.

Avant mutation, Léa était entièrement arrêtée et une sauvegarde officielle
cohérente avec WAL a été créée hors dépôt et workspace :
`L:\Lea_Backups\lea-before-final-cleanup-20261019.sqlite3`. Sa taille est
1 683 456 octets, `integrity_check=ok` et zéro violation étrangère. Elle contient
encore l’état antérieur et reste une sauvegarde privée temporaire, jamais destinée
à Git. Dans la base active, seule la mémoire expressément autorisée a été
supprimée. Conversation, messages, préférences, 13 projets, 159 runs,
159 checkpoints et 2 687 entrées de checkpoint ont d’abord été comparés. Le
rafraîchissement normal du catalogue a ensuite retiré les 13 projets désormais
absents du workspace ; runs, checkpoints et leurs inventaires restent identiques.

Après `wal_checkpoint(TRUNCATE)` et `VACUUM`, la base mesure 1 581 056 octets
contre 1 683 456, compte 386 pages contre 411, zéro page libre, aucun WAL/SHM
résiduel, `integrity_check=ok` et zéro violation étrangère. Le texte de la mémoire
supprimée n’est plus présent dans la base active. Cette opération ne promet pas
un effacement forensique des blocs SSD, des sauvegardes ou caches extérieurs.

Deux nouveaux tests ciblés utilisent une base isolée : la route HTTP employée
par le frontend supprime deux conversations successives, leurs messages et liens,
conserve une troisième et ne les fait pas réapparaître au redémarrage ; le test
SQLite vérifie `secure_delete`, checkpoint WAL, absence des marqueurs dans les
pages courantes et intégrité des relations. Résultats finaux : 256 tests backend,
41 frontend, build Vite, 8 cas PowerShell et analyse syntaxique des 12 scripts.

Un cycle réel sur base isolée a validé Général, réponse modèle, retenir/oublier,
suppression, Low/High puis retour Low, persistance après redémarrage, ressources
RAM/CPU et catalogue Programmation vide. Pocket TTS, Piper et Whisper permanents
ont traité trois durées synthétiques par voix, vitesse Piper et refus Pocket
incompatible compris. Le microphone physique n’a pas été rejoué : sa validation
manuelle antérieure reste la seule revendication. Un premier démarrage complet
a subi un état transitoire, a rollbacké proprement les trois processus, puis
`start-core`, deux démarrages complets et deux arrêts ont réussi sans processus
résiduel. Un audit Docker pré-commit ultérieur a supprimé sans force ni volume
155 conteneurs liés à des runs terminaux et l’ancien idle. Les neuf runs isolés
absents de la base active et les trois serveurs SDK encore référencés ont été
conservés par prudence ; ils sont tous arrêtés. Images, volumes, preuves de run
et checkpoints restent intacts. L’espace des couches de conteneurs est passé de
576,5 à 1,18 Mo, soit environ 575,3 Mo récupérés.

Un dernier cycle du runtime de production a créé un Agent Server réel sur un
dossier temporaire vide confiné à `L:\IA_WORKSPACE`, confirmé sa disponibilité,
puis produit les événements Docker `stop`, `die` et `destroy`. Son conteneur et
le seul point de montage `.git` vide ont été retirés ; le workspace est redevenu
vide et le nombre de conteneurs conservés est resté à 12.

L’audit a inventorié 151 fichiers du dépôt et analysé statiquement 54 fichiers
Python. Deux imports inutilisés de tests ont été retirés ; aucune fonction,
dépendance ou source de production n’était démontrée obsolète. Les scripts E2E,
fixtures historiques, environnements OpenHands/voix, modèles et protections sont
conservés. Les builds, bases isolées, sorties vocales synthétiques et anciens
artefacts `.test-runtime` sont régénérables et retirés lors du ménage final.
L’étape 14 reste terminée ; aucun commit/push et aucune étape 15.
