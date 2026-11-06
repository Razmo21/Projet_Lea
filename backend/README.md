# Backend de Léa

Backend FastAPI local de Léa, relié au serveur de modèle local `llama-server`.

## Prérequis

- Python 3.12.2

## Installation

Depuis le dossier `backend` :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`playwright` installe seulement son pilote Python. Ne lance pas
`playwright install` : la navigation 16.3 réutilise Microsoft Edge Stable déjà
présent et crée un profil éphémère distinct à chaque opération.

## Démarrage

Depuis la racine du projet, utilise le lanceur unique :

```powershell
.\lea.ps1 start-core
```

Le modèle, son port, son contexte, son alias et ses paramètres runtime sont
lus exclusivement depuis `config/models.json`. Ne démarre pas manuellement
`llama-server` avec une commande recopiée : elle deviendrait contradictoire
avec le registre central.

Pour le backend seul pendant un diagnostic local, utilise le même registre :

```powershell
$env:LEA_MODEL_REGISTRY = 'config/models.json'
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Routes

- `GET /health` retourne `{ "status": "ok" }`.
- `GET /api/resources` retourne le dernier snapshot en RAM, sans déclencher
  de sonde ni exposer de PID/chemin. `stale` signale l’absence de mesure récente.
- `GET /api/conversations?search=...` liste ou recherche les conversations.
- `POST /api/conversations/messages` crée la conversation au premier message
  ou ajoute un message à une conversation existante. Cette route intercepte
  aussi les commandes mémoire explicites et les demandes Web autorisées, sans
  route CRUD supplémentaire.
- `POST /api/web/operations/{id}/cancel` signale l’annulation d’une seule
  opération Web active ; il ne crée ni recherche ni autorisation.
- `GET /api/conversations/{id}` charge une conversation.
- `PATCH /api/conversations/{id}` renomme une conversation.
- `DELETE /api/conversations/{id}` la supprime définitivement avec ses messages,
  sans supprimer la mémoire générale.
- `POST /api/conversations/{id}/messages/{message_id}/retry` réessaie une
  question en échec.
- `PATCH /api/conversations/{id}/messages/{message_id}` modifie une question et
  supprime sa suite.
- `POST /api/conversations/{id}/messages/{message_id}/regenerate` régénère une
  réponse et supprime sa suite.
- `GET /api/models` et `GET /api/models/status` exposent les profils et leur
  état public ; `POST /api/models/{profile_id}/activate` les commute de façon
  contrôlée.
- `GET /api/projects`, `POST /api/projects/refresh` et
  `POST /api/projects/{project_id}/activate` gèrent les projets confinés à
  `L:\IA_WORKSPACE`.
- `GET /api/agent-runs` et `POST /api/agent-runs` consultent ou démarrent un
  run OpenHands ; les routes d’un run permettent de le lire, l’annuler,
  consulter ses changements, les accepter ou les restaurer.

Les requêtes sont strictes et refusent les champs inconnus, les contenus vides,
NUL, surdimensionnés ou contenant les marqueurs internes. Le navigateur envoie
uniquement le message courant, l’identifiant éventuel et la révision attendue :
il ne contrôle jamais l’historique, les souvenirs ou les rôles transmis au
modèle.

## Base SQLite

La base par défaut est `data/lea.sqlite3` à la racine du projet. Pour un test,
définis `LEA_DB_PATH` avant de démarrer le backend. Au démarrage, le backend
crée le dossier si nécessaire, applique les migrations dans une transaction,
active WAL et les clés étrangères, vérifie le schéma et récupère toute
génération interrompue comme message utilisateur en échec réessayable.

Les tables applicatives sont `conversations`, `messages`, `memories`,
`memory_sources` et `web_sources`. Les messages portent un type `conversation`
ou `memory`.
`memory_sources` relie chaque fait aux conversations qui l’ont explicitement
retenu tant qu’elles existent. Cette provenance est informative : un souvenir
global reste valide sans source. Les cascades retirent uniquement les messages
et les liens de la conversation. `Affiche tes souvenirs` relit uniquement les
faits actifs dans SQLite et produit une réponse déterministe, sans modèle ni Web.
`Oublie que` reste la suppression globale exacte. Les révisions empêchent les écritures périmées et
`generation_active` interdit deux générations simultanées dans une même
conversation. L’appel HTTP au modèle se fait hors transaction SQLite longue.

Les migrations de l’étape 10 ajoutent `projects`, `agent_runs`,
`project_checkpoints` et `checkpoint_files`. SQLite garde le registre compact
des runs, les résultats, les identifiants de session et les métadonnées/hashs
de checkpoint ; elle ne contient pas le détail des événements de l’Agent
Server. Les snapshots de fichiers résident dans le stockage local de
checkpoints et l’historique détaillé des sessions reste dans le volume d’état
de l’Agent Server.

## Préférences fonctionnelles — étapes 12, 15 et 16

La migration 8 ajoute `user_preferences` (une ligne, `revision`,
`general_reasoning` limité à `low`/`high`, défaut `low`). `PreferencesStore`
partage la base existante, sans cache global ni table de souvenirs supplémentaire.
Les sauvegardes transactionnelles vérifient `expected_revision`, modifient
uniquement la colonne concernée et relisent avant de confirmer le commit.
La migration 9 ajoute `show_resource_chart` (booléen strict, défaut false).
La migration 12 ajoute `veterinary_reasoning` (Low/High, défaut High) sans
modifier Général. La migration 13 ajoute `web_enabled` (défaut false) et les
métadonnées de sources attachées aux réponses, jamais les pages HTML. La
migration 14 ajoute seulement l’origine sûre d’un échec Web au message, afin que
l’interface ne le confonde pas avec une panne d’inférence. La migration 15
reconstruit uniquement `web_sources` afin d’accepter jusqu’à six preuves typées,
leurs dates distinctes et leurs limites d’extraction, en préservant les sources
16.1 existantes. La migration 16 ajoute seulement le type `dynamic_html` afin de
distinguer une page rendue par Edge d’un HTML statique. Le POST accepte une
mise à jour partielle ; champs omis
préservés, `null`, types coercibles et modifications vides refusés. Chaque
modification de raisonnement exige la capacité déclarée du profil concerné ; le
diagramme en est indépendant.

Une question clairement actuelle sans accord Web est finalisée par
l’orchestrateur avec une réponse honnête et un `model_id` nul. Ce chemin ne
contacte ni llama.cpp ni le Web Gateway. Les questions historiques datées et les
connaissances générales continuent de suivre l’inférence locale normale.
L’accord vient exclusivement du texte explicite ou d’une confirmation rattachée
à une attente en RAM : le contrat d’envoi ne contient plus de booléen
`web_authorized` que le frontend pourrait conserver par erreur. L’activation de
la préférence Web n’est donc jamais une permission permanente.

Une formulation explicite de vérification active dans le même `WebGateway` un
budget de trois recherches complémentaires, quatre sources par défaut et
45 secondes. Les résultats sont répartis entre les recherches, dédupliqués par
URL, origine éditoriale probable et empreinte textuelle, puis soumis à un
recouvrement lexical minimal. Ce filtre écarte seulement le hors-sujet évident ;
il ne fournit aucun score de crédibilité. Si moins de deux origines sont réellement
lues, FastAPI persiste une conclusion « impossible à vérifier » avec `model_id`
nul au lieu de demander au modèle de confirmer une preuve insuffisante.

`pypdf==6.21.2` lit les PDF en mémoire sous limites d’entrée, pages, texte et
flux décompressés. Les pages vidéo restent du HTML statique : seules leurs
métadonnées et transcriptions JSON-LD publiques sont utilisables. Les identifiants
`S1` à `S6` dérivent de la position persistée ; une référence hors de cette liste
est neutralisée après l’inférence. Le frontend distingue page lue, extrait du
moteur, PDF, métadonnées vidéo, transcription publique et page JavaScript rendue.

Une URL directe est traitée comme lecture documentaire, sauf demande explicite
de corroboration indépendante. Une seule source peut donc établir ce qu’elle
contient sans être présentée comme un consensus. Le message utilisateur conserve
la limite du profil ; la limite de 500 caractères s’applique uniquement aux
termes condensés envoyés à un fournisseur. Pour un HTML dépassant 768 Kio, le
transport s’arrête à cette borne et peut extraire un passage pertinent de la
partie reçue, avec une limite `lecture HTML partielle` visible. Les autres
ressources trop grandes restent refusées.

Une coquille HTML JavaScript réellement insuffisante peut déclencher le dernier
recours `EdgeDynamicPageReader`. Sa construction ne lance aucun processus.
Pendant l’opération seulement, Playwright ouvre Edge installé avec un profil
temporaire, une page, aucun service worker, permission ou téléchargement, puis
ferme le contexte et retire le profil. Le navigateur ne reçoit aucun historique,
souvenir, fichier ou instruction d’outil.

Un proxy HTTP local éphémère force les requêtes HTTP(S) vers l’hôte exact de la
page initiale. Il réutilise la validation publique et l’épinglage DNS de
`SafeHttpFetcher`; Playwright bloque en plus les méthodes autres que GET/HEAD,
les hôtes tiers et les types de ressources inutiles. Les pages sont limitées à
trois, les requêtes à 80, le trafic à 12 Mio et la session à 20 secondes. Aucun
clic n’est émis : la pagination utilise uniquement l’URL directe d’un lien
« suivant » validé et le texte des `<details>` fermés est lu sans mutation DOM.
Chaque page extraite conserve sa propre URL et devient une source distincte.

Ce proxy applicatif et l’interception du navigateur ne sont pas une isolation
réseau parfaite au niveau du système d’exploitation. Les API/CDN tiers, widgets,
authentifications, CAPTCHA, paywalls, boutons, formulaires et téléchargements
restent donc volontairement hors périmètre. Une incompatibilité arrête la lecture
sans contournement ; elle n’élargit jamais le permis Web.

`GET /api/preferences` et `POST /api/preferences` sont servis par **Vite sur
5173**, pas par FastAPI. Le pont ponctuel `tools/preferences.py read|save`
réutilise les modèles Pydantic et SQLite ; seule son entrée JSON va sur stdin,
jamais dans une commande shell. Il initialise avec `recover_generations=False` :
ouvrir les paramètres ne doit pas marquer une génération active comme interrompue.
Seul le démarrage normal de FastAPI conserve cette récupération.

Le POST exige l’origine locale, le bon Host et du JSON borné à 1 024 octets.
Champs supplémentaires, chemins, commandes, valeurs et types inconnus sont refusés.
Les réponses ne sont pas cachées ; conflits 409, entrées invalides 422,
indisponibilité 503. Le navigateur vérifie également le choix et la nouvelle révision.
`general_reasoning_available`, `veterinary_reasoning_available` et la liste
publique des modèles configurés sont dérivés du registre, non persistés. Aucun
modèle ni serveur n’est lancé par ces routes.

Avant chaque génération directe, FastAPI fige la préférence déclarée par le
profil. Général utilise `reasoning_control: think_directives`; Vétérinaire
utilise `chat_template_kwargs.enable_thinking` du template natif Qwen3.5.
`none` reste le défaut. Une préférence invalide refuse la génération avant
mutation de conversation ; aucun Low de secours caché. Le runner OpenHands ne
consulte aucun de ces réglages.

## Profil Vétérinaire direct

`veterinary` associe Qwen3.5-9B Q4_K_M à un contrat conversationnel sans outil,
vision ni workspace. Le Web Gateway commun peut lui fournir des extraits après
accord ponctuel. Le contexte est de 16 384 tokens, avec un slot, caches
KV Q8_0, sortie maximale 4 096 tokens et délai HTTP de 300 s pour les longues
réponses High. Le registre valide l'identité du GGUF et interdit à `--fit` de
réduire le contexte sous ce plancher.

Général et Vétérinaire partagent le propriétaire de processus direct, jamais le
modèle chargé simultanément. Leur commutation atomique confirme l'alias servi.
Depuis Programmation, le contrôleur arrête d'abord le runtime agentique vérifié ;
si le démarrage direct échoue, il tente de restaurer Programmation. Le chemin
inverse restaure exactement le profil direct précédent en cas d'échec.

## Profil Programmation et OpenHands

La source de vérité est `config/models.json`. Le profil Programmation utilise
`Qwen2.5-Coder-7B-Instruct Q6_K` avec une fenêtre de 22 000 tokens, un seul
slot et llama.cpp b10516. OpenHands Software Agent SDK / Agent Server 1.43.1
est le moteur agentique local ; Agent Canvas ne fait pas partie du chemin de
fonctionnement.

Docker Desktop doit être démarré manuellement. Le backend vérifie sa
disponibilité, mais ne démarre pas Docker. À l’activation, le profil direct actif
est arrêté avant Programmation ; en cas d’échec, le contrôleur restaure ce profil
précédent. Un seul run OpenHands peut posséder le runtime à la fois.
L’activation vérifie les prérequis locaux sans créer d’Agent Server. Son conteneur
n’est créé que par `POST /api/agent-runs` ; aucun serveur idle après finalisation.

Un run fige le `project_id`, le chemin relatif et l’identité du projet sous
`L:\IA_WORKSPACE` avant de lancer les outils `terminal`, `file_editor` et
`task_tracker`. Un changement de sélection dans une autre session ne peut pas
le rediriger. Le backend crée un checkpoint avant les mutations et attend
l’arrêt du conteneur Agent Server identifié avant de publier une annulation, un
timeout ou toute autre fin terminale. Les changements restent consultables ; ils
exigent une acceptation explicite ou un rollback, qui refuse toute modification
externe plutôt que de l’écraser.

Le parent borne le SDK au budget du registre + 60 s. Un résultat d’un autre run
ou un succès accompagné d’un exit code non nul échoue. Une erreur Docker ne
prouve jamais l’absence d’un conteneur : seule une inspection/liste réussie
l’établit. Au redémarrage, un arrêt invérifiable conserve le run non terminal
et bloque générations, commutations et nouveaux runs. Les diagnostics publics
`failure_detail` sont filtrés par liste exacte, pas issus d’une exception brute.

`resources.py` possède une seule tâche asyncio commune à tous les profils actifs,
fermée avec le lifespan même si l’arrêt d’un run échoue. Compteurs Windows
RAM disponible/CPU : 10 s ; NVIDIA et cache de disponibilité Docker : 30 s.
Elle démarre avec le profil par défaut et réutilise la même tâche lors des
commutations. Les seuils suivent la politique du profil sélectionné ; un
snapshot porte son `profile_id` et une sonde tardive de l’ancien profil est ignorée.
Docker/OpenHands ne sont consultés que pour un profil agentique OpenHands ou
un run OpenHands en récupération ; les profils directs n’en dépendent pas. La disponibilité
du modèle passe par l’adaptateur générique du profil, pas par celui de Programmation.
Les mutations Docker imposent une sonde fraîche. Les seuils RAM/VRAM viennent
du registre ; persistance des franchissements, marges et états NORMAL/WARNING/
CRITICAL sont détaillés dans le README racine. Aucune mesure en SQLite et aucune
autorité d’arrêt. Les sondes HTTP signalent une disponibilité, pas la mort
certaine d’un processus ; la propriété des PID reste aux lanceurs existants.

## Mémoire générale explicite

Les commandes reconnues au début d’un message sont :

```text
Retiens que ...
Souviens-toi que ...
Souviens toi que ...
Mémorise que ...
Memorise que ...
Oublie que ...
```

Les variantes raisonnables de casse, d’espaces et de ponctuation terminale
sont acceptées. Une commande sans fait est refusée. Une phrase ordinaire ne
crée aucune mémoire : il n’existe aucune extraction automatique.

La mémorisation, la ligne `memories`, son éventuelle provenance, le message
utilisateur, la confirmation assistant et la révision sont enregistrés dans
une même transaction SQLite courte. Le modèle n’est jamais appelé pour retenir,
dédupliquer ou oublier. Un doublon exact normalisé reçoit une confirmation sans
nouvelle ligne de mémoire ; une conversation différente devient toutefois une
source supplémentaire. L’oubli utilise uniquement `normalized_content` : aucun
fuzzy matching, sous-chaîne ou rapprochement sémantique.

Les tours `memory` restent visibles et copiables dans la conversation, mais le
backend refuse leur modification, régénération ou réessai. Ils sont filtrés de
l’historique modèle afin qu’un fait oublié ne réapparaisse pas par une ancienne
commande. La suppression complète de leur conversation retire sa provenance et
conserve le fait global jusqu’à une commande exacte `Oublie que`.

## Fenêtre de contexte et pensée interne

Pour le profil Général (`-c 8192`), le backend réserve 1 024 tokens pour la génération (réflexion comprise) et 1 024
pour les instructions et le template. Les autres budgets proviennent de `config/models.json`. Il estime prudemment un token par octet
UTF-8, garde toujours la question courante et sélectionne les paires complètes
les plus récentes dans la limite restante, sans supprimer les anciens messages
de la base.

Le backend ajoute `/no_think` en Low ou `/think` en High uniquement à une copie interne de la question
envoyée au modèle. Il retire ensuite les blocs de pensée complets, multiples ou
incomplets et refuse toute réponse finale vide ou encore marquée. Ni la
directive interne, ni un rôle `system`, ni la pensée ne sont persistés.

Avant une requête normale, le backend charge les souvenirs dans le même
instantané logique que l’historique, les sérialise dans une liste JSON échappée
et précise qu’il s’agit de données factuelles, jamais de directives. La mémoire
dispose d’une capacité de 1 800 tokens estimés avec la borne d’un octet UTF-8
par token. Un ajout dépassant cette capacité est refusé atomiquement : aucun
ancien souvenir n’est supprimé ou tronqué. Le bloc mémoire complet compte dans
le budget de contexte avant la sélection des paires historiques.

## Voix locale — étape 14

La voix ne crée aucune route audio FastAPI ni second serveur. Le contrôleur Vite
appelle `tools/voice/worker.py` à la demande ; ses adaptateurs dans `app/voice.py`
ne connaissent ni microphone, ni SQLite, ni Internet. L’environnement vocal
CPU sous `runtime/voice/.venv` est indépendant de celui du backend.

La migration 10 conserve les préférences vocales dans `user_preferences` et
ajoute `messages.agent_run_id` (unicité run/rôle). La migration 11 sélectionne
`lea_voice` sur les bases existantes sans modifier les autres réglages ; les
changements ultérieurs entre Pocket TTS et Piper restent révisionnés dans SQLite.
La création d’un run vocal et
de sa paire de messages est atomique ; son état terminal actualise cette même
réponse. La récupération d’une génération ne débloque pas une conversation
ayant un run non terminal. Les tours agentiques sont exclus du contexte chat
et des opérations réessayer/modifier/régénérer. `expected_profile_id`,
`expected_project_id` et la révision évitent un envoi après changement de contexte.

Chaque entrée du registre vocal déclare son moteur et ses actifs épinglés.
Pocket TTS utilise un YAML local sans URL, Piper conserve sa vitesse native et
aucun échec d’un moteur ne provoque un repli silencieux vers l’autre.

Aucun changement des permissions, preuves de validation, checkpoints ou décisions
Accept/Rollback. Installation, limites et essais :
[`docs/ETAPE_14_VALIDATION.md`](../docs/ETAPE_14_VALIDATION.md).
Ne pas confondre les tests synthétiques avec l’écoute physique.

## Tests

Depuis la racine :

```powershell
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend\tests -v
npm run test:frontend
npm run build
npm run test:edge
```

Le scénario Edge requiert Microsoft Edge Stable, Vite, le cœur local et une
base définie par `LEA_EDGE_DB_PATH`; les tests automatisés du projet utilisent
un profil Edge et une base SQLite temporaires.

Les scénarios de l’étape 12 et leurs prérequis isolés sont détaillés dans le
README racine. Ils ne remplacent pas le scénario historique `test:edge`.
Les preuves réelles et les scénarios de panne de l’étape 13 sont décrits dans
`docs/ETAPE_13_VALIDATION.md`. Ne jamais lancer ces scénarios sur la base utilisateur.
