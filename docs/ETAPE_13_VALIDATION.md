# Étape 13 — Rapport de validation du 17 octobre 2026

Verdict technique : `ETAPE_13_REUSSIE`. Validation manuelle finale attendue.
Les intégrations facultatives reportées ne sont pas présentées comme livrées.
HEAD de départ et de clôture : `a49af48` (étape 12). Aucun commit ni push.

Le complément demandé avant clôture est documenté en fin de rapport : la
surveillance est désormais commune à tous les profils actifs et « Votre question »
réutilise l'encadré existant. Les résultats initiaux ci-dessous restent datés de
leur essai ; le complément remplace notamment l'ancien arrêt de surveillance
en Général et précise l'état final de la session après les nouveaux tests.

## Périmètre et audit 13A → 13L

| Sous-étape | Statut | Modifications | Preuves | Limites |
| --- | --- | --- | --- | --- |
| 13A | Validée | Audit des propriétaires, preuves, checkpoints, paramètres | Code, Git, suites initiales 213/21 | Aucun chantier suivant |
| 13B | Validée | Timeout parent, résultat corrélé, diagnostic filtré, arrêt confirmé | Tests manager/runtime/API | Aucun correcteur des décisions Qwen |
| 13C | Validée | Reprise incertaine bloquante, PID recyclé sûr | Panne backend réelle après mutation, reprise et Rollback UI | Pas de reprise automatique de tâche |
| 13D | Validée | Compteurs natifs, tâche unique dormante | Mesures et coût réels ; cycle de vie unitaire | NVIDIA unique, état muet incertain |
| 13E | Validée | Seuils persistants, 3 barres, préférence SQLite 9 | Edge réel, seuils/alertes simulés | Pas d’arrêt automatique |
| 13F | Choix manuel appliqué | Conteneur seulement au lancement du run | Aucun conteneur à l’activation/après succès | Applications non ouvertes par Léa |
| 13G | Report approuvé | Aucun navigateur agentique | Barrière réseau examinée | Isolation de toutes les destinations non démontrée |
| 13H | Audit terminé | Propriétaires et compteurs existants réutilisés | Tests de sécurité et identité | Aucun pont Windows supplémentaire |
| 13I | Validée | Suppression ciblée du conteneur arrêté/validé | Vrai succès supprimé, échec conservé ; tests refus/idempotence | Aucun prune ni purge historique |
| 13J | Validée | Parcours réel isolé et non-régression | Général, OpenHands, Edge, interruption et persistance | Pannes GPU/timeout non provoquées matériellement |
| 13K | Terminée | Revue, commentaires, formatage localisé, documentation | Relecture et suites relancées | Code historique utile conservé |
| 13L | Terminée | Arrêt des services de test, ménage vérifié | Processus, ports, Docker, SQLite, Git | Docker Desktop utilisateur laissé ouvert |

KEEP : registre/adaptateur, processus propriétaires, politique native hashée,
preuves structurées, conflits de checkpoint, contrats, mémoire et données.
IMPROVE/ADAPT : fiabilité des fins, reprise, diagnostics, polling, PID recyclés.
ADD : surveillance légère en RAM et petit panneau facultatif, sans dépendance.
REMOVE : allocations idle automatiques, caches Edge/build de cet essai uniquement.
Les chemins d’arrêt des anciens idle restent utiles ; ni laboratoires GLM/Colibrì,
ni anciennes configurations, checkpoints, logs ou volumes ne sont purgés.

## Fiabilité, récupération et protections

Le parent attend le SDK au plus 1 860 s avec le registre actuel (1 800 + 60).
Le résultat doit correspondre au run et un succès exige un processus sorti à 0,
les preuves réelles existantes et l’arrêt vérifié du conteneur avant publication.
Le modèle n’obtient aucune nouvelle tentative de mutation automatique.
Une indisponibilité Docker ne signifie pas « absent » ; une identité ou un arrêt
incertain laisse le run non terminal et interdit une nouvelle activité modèle.
L’interface donne un diagnostic backend relu, pas les détails bruts d’une exception.
Rétablir Docker puis redémarrer Léa permet de retenter la récupération.

La reprise arrête l’Agent Server exact, fige le diff puis publie `failed`, sans
rejouer le task. Accept reste réservé aux changements validés. Rollback compare
les identités et empreintes ; un conflit n’est jamais écrasé silencieusement.
Les suites conservent confinement workspace, liens/reparse points, tests immuables,
permissions, origine/Host, marqueurs privés et commandes interdites.
Le code métier ne dépend d’aucun nom de projet benchmark ni d’un nom de modèle.

Le PID 27312 de l’ancien backend avait été repris par `backgroundTaskHost` avec
une autre date de création. Le lanceur reconnaît désormais l’ancien processus
disparu sans toucher au nouveau. Date illisible/identité divergente reste ambiguë
et le contrôle indépendant d’un port occupé n’est pas supprimé.

## Essais réels, données isolées et preuves durables

Base : `.test-runtime/stage13-20261017/lea.sqlite3`, définie par `LEA_DB_PATH`
avant lancement de Vite et FastAPI. Projet : `L:\IA_WORKSPACE\Lea_Stage13_20261017`,
copie jetable des trois fichiers de `tools/openhands/fixtures/stage10-python/`.
Jamais le dépôt Léa ni un projet utilisateur comme cible d’OpenHands.

1. Général réel : réponses Low/High correctes (remise de 25 % sur 80 → 60),
   aucun marqueur privé affiché ; brouillon conservé au retour des paramètres.
   Mémoire explicite `AZUR12`, historique et préférence High retrouvés après
   arrêt/reprise de la pile, puis rappel réel du souvenir par le modèle.
2. Préférences : diagramme false par défaut, activation, Valider, rechargement,
   désactivation/réactivation avec cœur arrêté, conservation après redémarrage.
   Refus HTTP réels de payloads/origines/commandes/chemins interdits.
3. Programmation : Docker ouvert manuellement ; activation sans Agent Server.
   Run `81b43212-fd63-4572-a4d5-322aa18dda47`, session
   `509e6872-0bb9-4c6f-8be5-922f7e65c29b` : lectures des trois fichiers,
   correction de `calculator.py`, test `python -B -m unittest -v` vert et finish.
   État durable `completed`/`validated`. Checkpoint
   `58db7f3a-1f01-45c2-a4ca-5300b5bacb30` accepté dans Edge après consultation du diff.
   Le conteneur arrêté est ensuite absent, sans serveur idle recréé.
4. Panne réelle : run `c0bb8bc2-be9f-48cb-b47b-aafa8dd120e1`, session
   `7eba121a-0e09-44bb-98c2-2542eba73c3f`. Backend identifié interrompu après
   mutation effective. Stop/start du cœur sur la base isolée ; récupération
   `failed`/validation `failed`, affichage explicite, Accept HTTP 409.
   Checkpoint `93d1ec81-70fb-487d-86cc-b983ebbb7930` restauré par bouton Edge :
   trois fichiers identiques octet pour octet à la fixture initiale, état
   `rolled_back`. Exactement deux runs en base : aucune double exécution.
   Son conteneur est arrêté et conservé pour diagnostic ; SDK client terminé.
5. Surveillance : vraies RAM, CPU, VRAM et disponibilités dans le backend/UI.
   Alerte CRITICAL injectée dans la réponse lue par le navigateur, visible
   diagramme masqué ; aucune pression mémoire destructive produite, aucun arrêt.
   Capture relue : `.test-runtime/stage13-20261017/alert-hidden-chart.png`.
6. Cadence frontend : état `running` simulé en lecture dans Edge, sans nouveau
   run ; 9 requêtes en 12 s, conforme au polling 1,5 s. Le test détecte la
   précédente boucle déclenchée par chaque nouvel objet `agentRun`.
7. Version initiale, avant le complément : le retour réel à Général rend
   `/api/resources` égal à `{active:false, stale:true}`.
   Arrêt final du cœur, frontend et navigateur de test vérifié.

SQLite : intégrité `ok`, aucune violation de clé étrangère ; 1 conversation,
8 messages, 1 souvenir et préférences `(revision=11, high, diagramme=false)`.
Aucun marqueur privé dans les messages. Base utilisateur inchangée avant/après :
`E8FC0A8C542D2540730DBE0E4F0B1620128843E70663A3003027BA43B2F1D5D6`.
Les checkpoints ne contiennent ni `__pycache__`, ni `.pyc`, ni `.pytest_cache`.
Après crash, le point de montage `.git` vide apparaît comme répertoire créé
dans le diff récupéré ; faute d’empreinte en mémoire survivante, il n’est pas
supprimé implicitement. Rollback le retire, sans fichier généré laissé au projet.

## Surveillance : sources, coût et limites

PC mesuré : i7-13700H, 20 processeurs logiques, RAM physique 33 995 571 200 octets
(31,66 Gio), RTX A1000 Laptop 6 Gio. Pas de modèle ou configuration remplacés.

- `GlobalMemoryStatusEx` : mémoire disponible, cache récupérable inclus.
  `GetSystemTimes` : CPU moyen entre deux relevés, premier relevé inconnu.
- Collecte ~10 s ; NVIDIA fixe installé (timeout 5 s) et Docker ~30 s.
  Sonde Docker de mutation toujours fraîche ; lectures de statut partagent le cache.
- Modèle par endpoint/alias, Agent Server par santé/outils pendant un run,
  backend par sa réponse. Un silence ne prouve pas la mort du PID : pas de
  surveillance parallèle remplaçant les propriétaires de processus existants.
- RAM : 8/6 Gio, deux relevés, marge +1 Gio ; CPU : ≥90 % trois intervalles,
  retour <80 % deux ; VRAM : <1 Gio deux nouveaux relevés, retour ≥1,25 Gio.
  Critique aussi si un service requis ne répond plus pendant un run.
- Pas de notifications répétées, d’action d’arrêt, de SQLite de mesures ou
  d’état prétendument sain quand une mesure manque. GPU absent/multiple : inconnu.
- Préférence false, trois barres bas de page, alertes indépendantes. La restriction
  initiale à Programmation est levée par le complément en fin de rapport.

Mesures ponctuelles, pas un benchmark de performance universel :

| Mesure | Résultat |
| --- | --- |
| 1 000 lectures compteurs Windows | 6,53 ms murales ; compteur CPU Windows 15,625 ms (granularité grossière) |
| Une commande NVIDIA | ~35,76 ms murales |
| Collecte complète avec readiness | ~265–562 ms murales selon activité |
| Backend sans polling UI, sur 35 s | 921,875 ms CPU, ~2,63 % d’un cœur / ~0,13 % machine ; working set 63 959 040 → 61 886 464 octets |
| Backend avec polling UI, sur 35,017 s | 5 406,25 ms CPU, ~15,44 % d’un cœur / ~0,77 % machine ; working set 62 881 792 → 63 139 840 octets |

Ces mesures incluent les sondes HTTP ; le CPU des enfants NVIDIA/Docker et le
modèle ne sont pas comptabilisés comme CPU du backend. Aucun ralentissement
disproportionné observé ; pas d’étude de latence statistique ni endurance longue.

## Docker, Edge et Windows

Docker Desktop et l’application OpenHands restent manuels, décision utilisateur.
Pas de paramètre d’auto-démarrage/arrêt ni d’ouverture automatique. Le clic run
crée le conteneur local strictement configuré. Un succès supprime son seul
conteneur arrêté et vérifié, sans force ni volume ; les échecs sont conservés.
Tests simulés : actif, inconnu, état absent, panne Docker, répétition/idempotence.
Le vrai volume `lea_openhands_lea_v1` et ses labels sont préservés.

Edge agentique reporté avec accord : blocage complet des redirections,
sous-ressources, workers et WebSocket externes non démontré par l’outillage
actuel. Un profil CDP isolé n’est pas une isolation réseau. Les tests développeur
sur localhost ne livrent aucune capacité Edge à OpenHands. Aucun Web public,
pont PowerShell arbitraire ni permission Windows supplémentaire à l’agent.

## Commandes et suites finales

```powershell
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -q
npm run test:frontend
npm run build
.\tests\launcher-process-record.ps1
.\backend\.venv\Scripts\python.exe -B tools/model_config.py
git diff --check
```

Résultats : 232 tests backend, 24 frontend, build et diff réussis ; 6 cas
d’identité du lanceur ; analyse AST sans erreur des 10 scripts PowerShell.
Les suites utilisent SQLite/fichiers temporaires réels, transports/modèles et
Docker simulés, CLI et contrôles Windows réels selon les tests. Elles couvrent
migrations, paramètres, mémoire, historique, registre, profils, outils, evidence,
sécurité, checkpoint/conflits, Accept/Rollback, timeout et récupération.

Scénarios réels reproductibles dans `tests/e2e/edge-stage13.mjs` : `settings`,
`chart`, `general`, `offline`, `persistence`, `security`, `programming`, `finish`,
`alerts`, `polling`, `recovered`. Préconditions : base isolée partagée, fixture
nommée ci-dessus, profil requis prêt et Edge de test CDP loopback 9232.
`chart` commence diagramme false ; `alerts` commence true et termine false.
`persistence` suit le redémarrage après `general`, `offline` exige le cœur arrêté.
`programming` inclut `finish`/Accept, `recovered` exige le second run échoué.
Ne pas exécuter ces phases aveuglément sur un autre état ou une base utilisateur.

`tests/e2e/stage13-fault.ps1` est volontairement destructif sur le seul backend
de validation : exige le chemin exact de base, compare le catalogue SQLite à
l’API, vérifie PID/commande/date et coupe après mutation observée. Ne jamais
lancer sur un projet réel. Redémarrage via `lea.ps1 stop-core` puis `start-core`,
base toujours isolée ; réactiver Programmation pour le contrôle UI `recovered`.

Non exécutés matériellement : épuisement RAM/GPU, panne GPU, kill modèle/Agent
Server séparés, attente réelle de 31 minutes pour timeout. Ces branches sont
simulées dans les suites ; seule la panne backend après mutation est réelle.
Pas de nouveau GGUF, benchmark difficile, smoke SDK historique ou suite Edge
historique complète de l’étape 8. Parcours concernés exercés avec Edge réel.

## Problèmes rencontrés et limites

- Ancien polling React immédiat en boucle, PID Windows recyclé et diagnostics
  trop silencieux corrigés sans nouveau mécanisme agentique.
- Pilote Edge stabilisé : attente du chargement de la nouvelle page, viewport
  explicite, attente du focus React, assertions sur les libellés réels.
- Avertissement préexistant Starlette/TestClient concernant `httpx` : tests verts,
  pas de mise à jour de dépendance opportuniste.
- Une reprise après crash ne restaure pas une exécution agentique en mémoire.
  Une indisponibilité Docker nécessite intervention puis redémarrage explicite.
- Aucun blocage restant connu des critères obligatoires ; validation manuelle
  finale attendue. Aucune question d’architecture encore ouverte pour cette étape.

Qwen2.5-Coder-7B peut échouer sur des tâches agentiques multi-fichiers longues lorsque file_editor exige des remplacements textuels exacts. Léa détecte ces boucles, refuse les mutations invalides, valide les changements par des tests et peut restaurer le checkpoint.

`Lea_FinalValidation_Test` demeure le benchmark difficile du futur comparatif
GLM-5.3-Flash/Qwen, sans nouveau mécanisme compensatoire.

## Git, qualité et ménage final

Modifiés : `AGENTS.md`, `README.md`, `TODO.md`, `CHANGELOG.md`, `docs/DECISIONS.md`,
`backend/README.md`, `tools/openhands/README.md`, `lea.ps1`, `tools/preferences.py` ;
backend `database`, `main`, `migrations`, `model_controller`, `openhands_evidence`,
`openhands_runs`, `openhands_runtime`, `preferences` et tests associés ;
frontend `App`, `Settings`, `agentRuns`, `index.css`, `preferences`, tests de
préférences et pilote `tests/e2e/edge-stage12.mjs`.

Créés : ce rapport, `backend/app/resources.py`, `backend/tests/test_resources.py`,
`src/ResourcePanel.tsx`, `src/resources.ts`, `tests/frontend/resources.test.ts`,
`tests/launcher-process-record.ps1`, `tests/e2e/edge-stage13.mjs`,
`tests/e2e/stage13-fault.ps1`. Le prompt 13 fourni par l’utilisateur reste non suivi.
Docstrings/commentaires sur fonctions nouvelles, transitions, seuils et sécurité ;
mise en forme localisée, aucun fichier source suivi supprimé.

Après arrêt : 380 fichiers du profil Edge jetable (22 740 079 octets) et 3 fichiers
de build (237 620 octets) supprimés après vérification des chemins et absence
de liens/reparse points. Régénérables, pas de restauration de données nécessaire.
Pas de purge des archives historiques faute de preuve d’inutilité. Captures,
base test, projet restauré, journaux, checkpoints, modèles et volumes conservés.
Les artefacts de validation sont ignorés par Git, aucun généré non ignoré ajouté.

État final de la validation initiale : backend, frontend, Qwen, SDK/Agent Server et Edge de test arrêtés ;
aucun processus de supervision restant, aucun écouteur 5173/8000/8080/8081/18010/9232,
aucun conteneur actif. Docker Desktop utilisateur reste ouvert. Données utilisateur
inchangées, checkpoints conservés. Aucun commit/push et étape 14 non commencée.

## Complément avant clôture — tous profils et encadré de saisie

Demande ciblée du même jour, sans nouvelle architecture ni dépendance :

- La tâche de surveillance existante démarre avec le profil par défaut, suit
  le profil sélectionné et ses seuils via le registre, puis ferme avec FastAPI.
  Même tâche, cadence de 10 s, cache NVIDIA de 30 s et alertes indépendantes
  du diagramme ; aucune action automatique sur le modèle ou les runs.
- Les disponibilités modèle suivent l'adaptateur du profil. Docker/OpenHands
  ne sont sondés que pour un profil agentique ou un run en récupération.
  Les relevés système et le cache GPU sont conservés lors d'une commutation ;
  un résultat tardif ne peut réintroduire les alertes de l'ancien profil.
- Le navigateur abandonne sa lecture à l'arrêt et lors d'une commutation,
  vérifie le profil du snapshot et conserve « Indisponible » pour une mesure
  réellement absente. La préférence SQLite false par défaut est inchangée.
- Le formulaire complet « Votre question » réutilise la classe `conversation` :
  titre, textarea et bouton partagent fond, bordure et espacement des sections
  voisines. Aucun nouveau CSS ; cinq lignes de saisie et comportement conservés.

### Non-régression et essais réels du complément

Les commandes backend/frontend/build et `git diff --check` ci-dessus sont
relancées pour ce complément. Résultat : **237 tests backend, 25 frontend et
build réussis**. Les 13 tests de ressources backend incluent désormais Général,
Programmation, un profil futur fictif, absence de Docker hors agent, seuils
du profil, cache GPU partagé, rejet d'une collecte tardive, échec de commutation
et fermeture de la tâche unique. Le contrat frontend refuse également un
snapshot associé à un autre profil. Avertissement Starlette/httpx préexistant,
aucun échec ni dépendance modifiée.

Essais avec les modèles installés et Edge local, sur la nouvelle base isolée
`.test-runtime/stage13-all-profiles-20261017/lea.sqlite3` :

1. Diagramme masqué par défaut, activation dans Paramètres, Valider, puis
   conservation après rechargement. Aucun changement des préférences utilisateur.
2. Encadrés comparés par leurs styles calculés à **1280 et 390 px** : fond,
   bordure, rayon et padding identiques ; label, textarea et bouton contenus
   dans le formulaire, hauteur confortable et aucun débordement horizontal.
   Captures `question-1280.png` et `question-390.png` conservées dans ce dossier
   et inspectées visuellement. Question réelle « 2 + 2 » : réponse correcte.
3. Commutations réelles **Général → Programmation → Général** : RAM, CPU et
   VRAM connues et affichées ; modèle prêt à chaque profil. Docker requis et
   disponible en Programmation, non sondé en Général (`null`, pas de faux zéro).
   Aucun run ni conteneur OpenHands créé par ce complément.
4. Arrêt du cœur, interface conservée : état arrêté explicite, aucune barre
   périmée et **zéro requête `/api/resources` en 12 s**. La fermeture de la
   tâche backend est également couverte par le test de cycle de vie.
5. Base de test : intégrité `ok`, zéro violation de clé étrangère, 1 conversation,
   2 messages, aucun souvenir ni run ; préférence `(revision=1, low, diagramme=true)`.

Phases supplémentaires reproductibles :

```powershell
node tests/e2e/edge-stage13.mjs allProfiles
# Après lea.ps1 stop-core, avec la même base isolée et Vite encore actif :
node tests/e2e/edge-stage13.mjs stoppedResources
```

Préconditions : base de test neuve (diagramme false), Général prêt, Docker
préalablement ouvert manuellement, Edge isolé sur CDP loopback 9232 et dossier
de captures existant. Ces phases ne doivent pas être lancées sur la base habituelle.
La persistance après redémarrage complet, les vrais runs, Accept et Rollback
restent attestés par la validation initiale ; ils ne sont pas rejoués pour ce
complément. Le benchmark difficile et les protections agentiques sont inchangés.

Fichiers concernés par ce seul complément : `backend/app/{main,resources}.py`,
`backend/tests/test_resources.py`, `src/{App,Settings,ResourcePanel}.tsx`,
`src/resources.ts`, `tests/frontend/resources.test.ts`, `tests/e2e/edge-stage13.mjs`
et documentation (`AGENTS.md`, `README.md`, `TODO.md`, `CHANGELOG.md`,
`backend/README.md`, `docs/DECISIONS.md`, ce rapport).

L'utilisateur a autorisé l'arrêt temporaire de sa session puis son rétablissement.
Entre cet arrêt et la fin des essais isolés, la base habituelle est inchangée,
SHA-256 `4C7CFE079E5471225DF23985A352CD9270E33C7E9B749F969BCCC387331872AD`.
Cette nouvelle empreinte est celle de la session utilisée depuis la validation
initiale, pas une modification des données par les tests.

État final du complément : session habituelle rétablie, Général `ready`,
backend/frontend/modèle actifs sur 8000/5173/8080 ; ressources fraîches, niveau
NORMAL, et empreinte SQLite toujours identique après ce redémarrage. Aucun
SDK, Agent Server, conteneur actif ou navigateur Edge de test restant ; ports
8081/18010/9232 libres. Docker Desktop utilisateur laissé ouvert.

Ménage ciblé après fermeture : 336 fichiers du nouveau profil Edge jetable
(18 541 856 octets) et 3 fichiers `dist/` (237 847 octets) supprimés après contrôle
des chemins et absence de liens/reparse points. Tous régénérables ; captures,
base isolée, données utilisateur et preuves initiales conservées. Aucun commit,
push, nouveau mécanisme agentique ni début de l'étape 14. Validation manuelle
finale de l'étape 13 toujours attendue.
