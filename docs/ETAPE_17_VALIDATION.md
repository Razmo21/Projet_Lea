# Étape 17 — Markdown et interface conversationnelle

Date : 1er novembre 2026. Base : `d9a2f75`, étape 16 commitée par l’utilisateur.
Derniers ajustements visuels vérifiés le 2 novembre 2026.
L’étape 17 est implémentée ; la validation manuelle reste à effectuer.
Le packaging Windows n’est pas commencé. Aucun commit ni push pendant ce travail.

## Diagnostic et correction du Markdown

Le défaut démontré était dans `App.tsx` : chaque message était rendu avec
`<p>{message.content}</p>`. React affichait donc les délimiteurs Markdown comme
du texte, et CSS conservait les sauts de ligne sans interpréter la structure.
Il n’y avait aucun parseur Markdown frontend.

Le trajet de données a été relu : filtre de réponse du modèle, stockage par
paramètres SQLite, JSON API, `ConversationMessage.content`, rendu et copie.
Le nouveau test API confirme l’identité exacte du contenu modèle, de la ligne
SQLite et du message relu après recréation de l’application. Entités, chemins
Windows, code et antislashs sont conservés. La base locale consultée en lecture
seule ne contenait aucun message assistant : aucune ancienne anomalie de double
échappement n’a donc pu être attribuée à un enregistrement réel.

La correction est un rendu CommonMark/GFM, sans modifier le texte enregistré.
`**bonjour**` est du gras ; `\*\*bonjour\*\*` affiche les astérisques littéraux.
Il serait incorrect de deviner que tous les antislashs viennent d’une anomalie.
Le texte déjà volontairement échappé reste donc littéral, dans les nouveaux
messages comme dans l’historique. Aucune migration ni correction destructive.

Pris en charge : titres, paragraphes, sauts de ligne, gras/italique/barré,
listes imbriquées, listes ordonnées, tâches, citations, liens, tableaux,
code en ligne, blocs avec/sans langage, séparateurs, Unicode et Markdown incomplet.
La génération n’est pas diffusée en continu dans l’application existante : le
message en attente reste visible et la réponse est rendue dès réception.

## Présentation et accessibilité

- Barre permanente avec recherche, nouvelle conversation, sélection et dates.
  Aucun bouton pour la masquer ni piège de focus. Jusqu’à 600 pixels de large,
  elle passe au-dessus du chat avec historique horizontal compact.
- Conversation centrale avec bulles distinctes pour l’utilisateur et Léa.
  Défilement automatique limité à une lecture déjà située en bas.
- Saisie ajustable et bornée ; Entrée envoie, Maj+Entrée ajoute une ligne,
  conformément au retour utilisateur. Les commandes
  d’annulation existantes Web, audio et run restent disponibles. Aucun faux
  bouton d’annulation générale de l’inférence n’est ajouté.
- Thèmes clair/sombre couvrant paramètres, voix, programmation et ressources.
  Choix appliqué immédiatement, mémorisé sous `lea.appearance.theme` dans ce
  navigateur, défaut système au premier chargement, avis si stockage refusé.
  Les préférences IA et vocales restent révisionnées dans SQLite.
- État du cœur et commandes Démarrer/Arrêter visibles au pied de la barre.
  Les erreurs restent visibles. Paramètres utilisables avec l’IA arrêtée.
- Focus visible, libellés des commandes, sources dépliables, tableaux/code
  accessibles au clavier. Aucun mouvement imposé ; effets de survol seulement
  si le système n’a pas demandé une réduction des mouvements.
- Diagramme et commandes vocales compactés sur petit écran : la fenêtre
  320 × 568 conserve au moins 140 pixels de conversation avec diagramme affiché.

## Sécurité et invariants

Le HTML brut est ignoré ; aucun `dangerouslySetInnerHTML` ni moteur HTML ajouté.
Les liens actifs exigent une URL HTTP(S) absolue sans identifiants. Les schémas
JavaScript, data, file et les chemins relatifs sont inertes. Les liens s’ouvrent
sur clic dans un onglet séparé avec `noopener`, `noreferrer` et sans referrer.
Ce contrôle du rendu n’est pas une isolation réseau ou une certification du lien.
Les images distantes ne sont pas chargées. Les tests surveillent réellement les
requêtes externes, pas uniquement l’absence d’images dans les captures.

Les sources affichées viennent de `web_sources`, avec nature de la preuve,
dates et limitations. `[S999]` seul ne crée ni lien ni référence. Le backend
garde l’autorité sur les citations, le consentement, les permissions et les runs.
Le bouton Web ponctuel reste absent. Aucun contrat, moteur, modèle, endpoint,
schéma SQLite, permission, capture audio ou comportement réseau métier modifié.
Cette description concerne la refonte initiale ; le complément éphémère
explicitement demandé ensuite ajoute les routes RAM décrites plus bas, sans
modifier les routes de conversation persistante ni le schéma SQLite.

Lors de la refonte initiale, la comparaison des arbres TypeScript a confirmé
les 30 fonctions internes existantes d’`App` inchangées, ainsi que les fonctions
de sauvegarde des paramètres et la chaîne audio. Le complément décrit plus bas
adapte la sélection au renommage, la cible de suppression et le clavier, tout
en conservant les routes et contrôles de révision existants. La fermeture vocale
rend le focus au bouton d’ouverture.

## Dépendances et fichiers

| Élément | Rôle |
| --- | --- |
| `react-markdown` 10.1.0 | Rendu React CommonMark, sans HTML actif |
| `remark-gfm` 4.0.1 | Tableaux, tâches, texte barré et syntaxe GFM |
| `tsx` 4.23.15, développement | Exécuter les tests React/TSX |
| Vite 7.3.7 / source-map-js 1.2.2 | Correctifs compatibles des alertes npm constatées |

Pas de moteur mathématique ni coloration syntaxique : leur ajout serait
facultatif. Pas de bibliothèque d’icônes, framework de style, police distante,
CDN, serveur MCP ou plugin. Prettier 3.6.2 utilisé ponctuellement pour la mise
en forme ; aucune dépendance de production correspondante.

Fichiers de production principaux : `src/App.tsx`,
`src/components/Settings.tsx`, `src/components/VoiceControls.tsx`,
`src/styles/index.css`, `package.json`, `package-lock.json`.
Image locale ajoutée : `public/lea-logo.png`, copie exacte du PNG fourni dans
la conversation (1254 × 1254 pixels, 1 814 794 octets). Réutilisée pour la barre
et l’icône d’onglet déclarée dans `index.html`, sans ressource distante.
Composants ajoutés puis rangés : `src/components/MarkdownMessage.tsx`,
`src/components/WebSources.tsx`, `src/components/ConversationSidebar.tsx`,
`src/components/AutoTextarea.tsx`, `src/components/Icon.tsx`,
`src/lib/appearance.ts`, `src/hooks/useAppearance.ts`.
Tests : `backend/tests/test_api.py`, `tests/frontend/markdown.test.tsx`,
`tests/frontend/appearance.test.ts`, `tests/e2e/edge-stage17.py`.
Documentation : `AGENTS.md`, `README.md`, `TODO.md`, `CHANGELOG.md`,
`docs/DECISIONS.md` et ce rapport. Le prompt 17 fourni par l’utilisateur est
conservé tel quel.

Sources de choix : [documentation react-markdown](https://github.com/remarkjs/react-markdown)
et [documentation remark-gfm](https://github.com/remarkjs/remark-gfm).

## Vérifications automatisées

| Vérification | Résultat |
| --- | --- |
| Tests frontend complets | 59 réussis, 0 échec |
| Tests backend complets, complément éphémère inclus | 378 réussis, 0 échec |
| Build TypeScript/Vite | Réussi sans avertissement de compilation |
| Edge installé, contexte jetable | 23 groupes de scénarios réussis |
| Réseau externe du banc Edge | 0 requête ; toutes les API interceptées |
| Erreurs JavaScript du banc Edge | 0 |
| Audit npm après correctifs | 0 vulnérabilité signalée |
| `git diff --check` | Réussi |

Dernier passage backend : 378 tests en 96,408 s, code de sortie Python 0.
Dernier build : JavaScript 436,82 Ko (135,00 Ko gzip), CSS 20,63 Ko
(4,90 Ko gzip), plus le PNG local de 1,81 Mo. Ce sont des tailles de fichiers,
pas une mesure de RAM. La durée backend varie avec la charge locale et les
scénarios Playwright internes ; aucun délai de production n’a été modifié.

Les scénarios Edge couvrent Markdown et copies, rechargement, sélection et
recherche, thèmes, Low/High, retour avec brouillon, envoi et suppression de Régénérer,
annulation Web, erreurs, vue vocale et refus de microphone simulé,
Programmation avec échec/validation/annulation, Accept/Rollback simulés,
ressources inconnues, démarrage/arrêt simulés, renommage et suppression ciblée.
Le scénario Programmation saisit aussi une consigne qui mentionne Internet et
confirme qu’elle crée un run, sans requête de conversation ni appel Web.
Le navigateur est **Edge 156.0.4314.58**. Captures examinées : accueil clair,
conversation sombre, paramètres clair/sombre, voix et Programmation.
Dimensions : 1920 × 1080, 1024 × 768, 768 × 700, 600 × 600,
390 × 844 et 320 × 568, plus vues initiales 1440 × 1000.

Un premier passage backend en sandbox a refusé un remplacement atomique dans
le checkpoint temporaire d’un test ; le même test et la suite complète passent
hors sandbox, sans modification de la sécurité des checkpoints. Le lanceur TSX
a également nécessité l’exécution hors du compte sandbox Windows pour `os.userInfo`.
Ces limites de l’environnement de test ne sont pas masquées par un test ignoré.

Commandes depuis la racine :

```powershell
npm run test:frontend
npm run build
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -q
node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5174 --strictPort
.\backend\.venv\Scripts\python.exe -B tests/e2e/edge-stage17.py
npm audit
git diff --check
git status --short
```

Le banc Edge exige le build servi localement sur 5174 et Playwright déjà présent
dans le Python backend. L’aperçu statique a été retenu pour le dernier passage :
un second serveur de développement frais a temporairement tardé à servir le PNG,
alors que le premier passage complet et l’aperçu ont chacun réussi les 23 groupes.
Il ferme son navigateur dans un `finally`. Les captures et
résultats vont dans `.test-runtime/stage17`, ignoré par Git. Aucun projet réel,
conversation personnelle, souvenir ou checkpoint utilisateur n’est modifié.
Le Vite de test et les contextes Edge sont arrêtés après validation ; le port
5174 est libéré. Aucun dossier temporaire de test ne reste dans `backend/tests`.
Les captures synthétiques et journaux de validation restent disponibles dans
le dossier ignoré indiqué ci-dessus. `git status` ne contient que les fichiers
de cette étape et le prompt utilisateur, sans artefact de build suivi.

## Limites et validation manuelle attendue

### Ajustements après le premier essai utilisateur

Les lignes de la barre latérale proposent un crayon et une poubelle au survol
ou au focus clavier, toujours visibles sur écran tactile. Le crayon charge la
conversation avant d’ouvrir l’éditeur existant avec sa révision actuelle ; la
poubelle conserve la confirmation et la vérification de révision. Supprimer une
ligne inactive ne remplace pas la conversation affichée ni le brouillon.

Les commandes vocales compactes et la flèche d’envoi sont réunies dans la
saisie. Les infobulles et noms accessibles restent présents ; l’enregistrement
remplace le microphone par une icône d’arrêt. Un portail React place ces
commandes sans démonter leur contrôleur audio lors du passage au mode vocal.
La marque latérale n’affiche plus « personnelle · locale ».

Le pied latéral propose Démarrer et Arrêter, avec les mêmes verrous
et appels au contrôleur qu’auparavant. La phrase locale est retirée.
Le champ commence sur une ligne et grandit jusqu’à quatre lignes, puis défile
intérieurement. La mesure tient compte des lignes repliées, de la hauteur de
police et des espacements ; effacer le brouillon le ramène à une seule ligne.
Le banc Edge vérifie les limites une/deux/quatre/cinq lignes, un texte replié sans
saut explicite et le défilement effectif, y compris aux six tailles de fenêtre.

Entrée utilise le bouton d’envoi existant et respecte son état désactivé ;
Maj+Entrée conserve une ligne. Les événements de composition IME et de répétition
sont exclus. Le banc Edge couvre ces touches, l’alignement des icônes, le
renommage d’une autre conversation et la suppression refusée, en conflit ou
confirmée, avec conservation du brouillon. Aucun backend ni moteur audio modifié
par ce complément ; la validation du microphone physique reste manuelle.

Le « + » désactivé, le texte, les commandes vocales et l’envoi
partagent maintenant la même ligne (58 pixels de hauteur au repos sur grand
écran). Les états vocaux, erreurs et avis Web restent visibles dessous.
Le bouton Paramètres remplace le « × » en haut de la barre ; le retour conserve
le focus et l’éditeur ouvert, y compris en tactile. Le sélecteur
de profil est à droite de l’en-tête. Son menu natif reçoit explicitement le
fond et le texte du thème ; les couleurs des options sont vérifiées dans Edge.
« Modèle prêt » remplace les trois libellés dépendant du profil sans masquer
les états de chargement, erreurs ou pertes répétées de surveillance.

Le « + » ne modifie ni la conversation ni le brouillon, ne déclenche aucune
requête et n’ouvre aucun sélecteur de fichier. Seul un commentaire réserve son
usage futur. Nouvelle conversation reste disponible dans la barre. Le libellé
« Vos conversations » devient « Conversations ». Le code de repli, son écoute
de largeur, le masque mobile et l’icône correspondante devenus inutiles sont
retirés. La barre reste visible dans les paramètres et la vue vocale ; les
actions sur les conversations y sont désactivées pour conserver le contexte.
Les tests Edge vérifient ces états, les boutons du cœur, le logo chargé depuis
le projet, les six tailles et l’absence de fermeture par Échap.

Le bouton autonome Régénérer et son gestionnaire frontend inutilisé sont retirés.
Le texte envoyé quitte le champ dès la prise du verrou de génération. Le banc
retarde la réponse pour vérifier la présence d’une seule bulle et du champ vide.
Un refus sans conversation enregistrée ou un conflit restitue le brouillon ;
un échec enregistré reste dans l’historique. Une erreur de chargement de liste
après un envoi déjà confirmé ne remet pas le texte dans le champ. La voix
conserve son brouillon clavier indépendant, comme auparavant.

Complément vérifié : 57 tests frontend, 21 groupes Edge (dont un contexte
tactile supplémentaire), build et `git diff --check` réussis. La suite backend
n’a pas été répétée pour ces changements exclusivement frontend. Les fichiers
touchés sont `App.tsx`, `AutoTextarea.tsx`, `ConversationSidebar.tsx`, `VoiceControls.tsx`, `Icon.tsx`,
`index.css`, `agentRuns.ts`, `tests/frontend/conversations.test.ts`, le banc Edge
et les documents README/TODO/CHANGELOG/ce rapport, ainsi que `index.html` et
`public/lea-logo.png` pour le logo fourni.
Les captures d’accueil, mobile et survol ont été examinées visuellement.

La première passe du 2 novembre agrandit la marque latérale à 20 pixels et « Conversations »
à 14 pixels. Le titre Léa du bandeau est retiré ; l’accueil contient seulement
« Bonjour, comment puis-je vous aider aujourd'hui ? », sans logo central ni
texte secondaire. Les infobulles et noms accessibles sont « Dictée » et
« Envoyer » au repos ; les états d’enregistrement et d’envoi restent explicites.
Les espaces entre Dictée, Conversation vocale et Envoyer mesurent chacun
8 pixels, vérifiés dans Edge aux six dimensions de fenêtre.

Le nouveau PNG fourni remplace le précédent, sans génération ni retouche.
Les variables CSS communes reprennent ses verts profonds, sa menthe et son
ivoire ; les erreurs et avertissements gardent des couleurs distinctes.
Le banc mesure le contraste des textes principal/secondaire sur les six fonds,
des états sur la surface, du bouton principal et des options natives du sélecteur.
Minimum de ces combinaisons : 4,95:1 en clair, 5,01:1 en sombre. Cette vérification
ne constitue pas un audit d’accessibilité complet ; les commandes désactivées
restent volontairement atténuées.

Le banc attend désormais la réponse de rechargement de la conversation après
son démarrage simulé, puis la réactivation de la saisie. Attendre seulement la
valeur du profil laissait le test saisir trop tôt lors d’une transition.
Le dernier passage complet réussit ; aucune logique de démarrage de production
n’a été modifiée pour cette synchronisation du test.

À la demande de l’utilisateur, la pile locale a été redémarrée avec `lea.ps1`.
Les composants étaient déjà arrêtés, mais un ancien PID backend avait été
réattribué à `msdtc.exe` : le lanceur a correctement refusé de l’arrêter.
Après vérification des processus et des ports libres, seul `processes.json`
périmé a été archivé dans `.lea`, sans tuer ce service Windows. `lea.ps1 stop`
a confirmé l’arrêt puis `lea.ps1 start` a rendu actifs modèle Général, backend
et interface. Aucune modification du lanceur ni des données utilisateur.

### Complément demandé le 2 novembre : accueil et chat éphémère

Le champ reste défilable par molette, toucher et clavier après quatre lignes.
Un rail de trois pixels apparaît alors à sa droite, après les commandes vocales
et d’envoi. L’accueil est centré dans la zone de conversation.
Un des six titres demandés est choisi au chargement, à Nouvelle conversation,
au retour des paramètres ou à la sortie du chat éphémère. Aucun minuteur ne
change le titre au repos ; seul son fondu d’apparition est animé, selon la
préférence de réduction des mouvements.

Le bouton, déplacé ensuite en haut à gauche du chat, ouvre **Chat éphémère**, exclusivement sous Général,
et ferme/efface la session au second clic, y compris pendant une réponse.
Le brouillon et la conversation normaux sont séparés et reviennent à la sortie.
Pendant ce mode, le changement de profil et les actions sur l’historique sont
désactivés pour éviter un transfert involontaire du texte privé.

Le backend possède un registre RAM séparé : huit sessions maximum, trente
minutes d’inactivité avant expiration, cent messages et environ 256 Kio de
contexte par session, réduits par paires. Il n’existe aucune sauvegarde de ce
registre ni accès aux souvenirs. Les identifiants ne vont ni dans l’URL de la
page, ni dans localStorage/sessionStorage. Le frontend observe l’identité du
backend via le polling existant pour oublier une session après redémarrage.
Le rechargement efface la vue et demande la fermeture ; si le navigateur est
tué ou le backend injoignable, l’expiration couvre la session serveur abandonnée.

La dictée et les réponses vocales empruntent la route éphémère quand ce mode
est actif. Les messages vocaux ne prétendent alors plus enregistrer un historique.
La chaîne STT/TTS locale reste celle déjà validée ; aucun nouvel essai physique
du microphone ou des haut-parleurs n’est revendiqué.

Le Web a été explicitement demandé dans ce mode. Réglage global, consentement
manuel ponctuel, confirmation liée au tour, SSRF, limites HTTP, budgets du
modèle et validation des citations restent ceux du Gateway. L’historique privé
n’est pas transmis au moteur de recherche ni utilisé comme preuve Web.
Les sources consultées restent seulement en RAM avec la réponse.
Le lecteur Edge est exclu pour ne pas créer de profil navigateur sur disque :
une page nécessitant JavaScript peut échouer. Les hôtes ne sont pas journalisés
par le diagnostic d’erreur du Gateway dans cette portée ; des métadonnées
techniques sans contenu peuvent subsister dans les journaux habituels.

**Limite de confidentialité :** ni les moteurs de recherche, ni les sites,
ni le système d’exploitation ou le réseau ne sont sous ce contrôle. Le mode
ne garantit donc pas l’anonymat réseau, l’absence de journaux externes ou un
effacement forensique de la RAM/fichier d’échange. Aucun dialogue n’est écrit
par Léa dans SQLite ou un fichier d’historique.

Preuves de validation :

- Neuf tests backend dédiés : absence d’écriture dans toutes les tables SQLite,
  aucun appel à la lecture des souvenirs, sessions isolées, Web sans accord
  réellement absent au transport, confirmation à usage unique et citations,
  refus localhost, profil Général exclusif, origine hostile, erreurs et fermeture
  pendant l’inférence avec libération du coordinateur. Limites et effacement RAM
  vérifiés séparément.
- Deux tests frontend supplémentaires et parcours Edge : titre inchangé après
  35 secondes simulées, renouvellement à la navigation, centrage mesuré, défilement
  sans rail, absence de stockage navigateur, retour du brouillon normal,
  fermeture pendant une réponse, rechargement et changement d’instance backend.
- Essai **réel avec le modèle Général local** sur base isolée : code de test
  rappelé au tour suivant ; lecture HTTP simulée de faits publics sur les abeilles,
  réponse « Les abeilles sont des insectes pollinisateurs [S1]. » acceptée avec
  source réelle du jeu de test. Statut 200, SQLite inchangée, session effacée.
  Aucun accès Internet réel dans cet essai ; ce n’est pas une validation de
  disponibilité de DuckDuckGo/Bing.
- Un passage a rencontré `WinError 5` sur `os.replace` dans l’ancien test de
  rollback de checkpoint. Les douze tests de checkpoints puis les 378 tests
  complets ont réussi à la relance, sans modification de ce composant. Cause
  système exacte non établie ; incident intermittent conservé dans le rapport.
- Cœur arrêté/redémarré proprement via `lea.ps1 stop-core/start-core`, Général
  prêt et interface HTTP 200. Session RAM vide ouverte/fermée sur l’API relancée.
  Les deux bases temporaires d’un premier test à connexion mal fermée ont été
  supprimées après correction du test ; aucune donnée utilisateur supprimée.

Fichiers supplémentaires : `backend/app/ephemeral.py`, routes dans `main.py`,
portée privée des diagnostics dans `web_gateway.py`,
`src/hooks/useEphemeralChat.ts`, `src/components/Welcome.tsx` et
`src/lib/api.ts` (helper existant déplacé sans changement de
comportement). Raccordement dans `App.tsx`, `models.ts`, `VoiceControls.tsx`,
`Icon.tsx` et `index.css`. Tests : `test_ephemeral.py`, `welcome.test.tsx` et
complément du banc Edge. Aucune dépendance ni migration ajoutée.

### Campagne manuelle restante

Dernier ajustement visuel du 2 novembre : Conversation vocale et Envoyer
occupent le même emplacement à droite du champ. La première commande apparaît
quand le brouillon est vide (ou ne contient que des espaces), la seconde avec
du texte. Pendant une réponse, l’envoi reste désactivé ; Entrée à vide ne lance
pas la voix. Le bouton de dictée et le contrôleur audio restent montés.
Le bouton éphémère se trouve à gauche du bandeau du chat, hors barre latérale,
et partage les dimensions 30 × 30 pixels du bouton Paramètres.

Fichiers de ce dernier ajustement : `App.tsx`, `VoiceControls.tsx`, `index.css`,
le banc Edge et README/TODO/CHANGELOG/ce rapport. Aucune dépendance ajoutée.
Les 59 tests frontend, le build et le banc Edge sont relancés ; les 378 tests
backend ci-dessus précèdent ce changement exclusivement visuel.

Le dernier affinage retire le titre et les boutons Renommer/Supprimer du haut
des messages ; le crayon et la poubelle de la barre latérale restent l’unique
accès à ces actions. Les réponses de Léa reçoivent une bulle distincte. Le
contenu des paramètres reste borné, mais son panneau défilant occupe toute la
zone principale afin de placer le rail à droite. Le diagramme RAM/CPU/VRAM est
désormais enfant de cette zone et son titre visuel redondant est retiré.

La page Paramètres est ensuite simplifiée sans modifier les données persistées :
Apparence, Général, Vétérinaire, Ressources, Web et microphone/voix restent
présents. La carte informative Programmation est retirée de cette page ; le
profil, ses projets, ses runs, Docker/OpenHands et leurs protections ne changent
pas. Les cartes utilisent deux colonnes sur écran large et une sur petit écran.
Microphone et voix locale occupent toute la largeur dans deux panneaux distincts,
avec tous leurs contrôles antérieurs. La validation devient un grand bouton
centré, sans carte décorative ; ses messages restent juste dessous. Le bouton
Paramètres agit comme bascule et demande toujours confirmation si un brouillon
n’est pas enregistré. Le bouton Retour aux conversations reste disponible.

Le frontend auparavant plat est rangé sans refonte fonctionnelle : vues dans
`src/components/`, hooks dans `src/hooks/`, contrats et fonctions dans `src/lib/`,
feuille commune dans `src/styles/`. `App.tsx` et `main.tsx` restent les points
d’entrée. Le backend, les modèles, les données, la configuration et les anciens
rapports ne sont pas déplacés. Le rail de trois pixels de la saisie est dégagé à
droite des commandes au lieu de passer sous le bouton principal.

Le dernier ajustement fonctionnel demandé simplifie Programmation sans modifier
le moteur agentique. La saisie inférieure devient l’unique consigne OpenHands ;
le champ « Tâche de développement », le titre d’accueil et le bouton de départ
disparaissent. Envoyer démarre le run ; **Annuler la tâche** apparaît dans
l’encadré Projet pendant son exécution. Les résumés textuels du statut, de la
validation et du checkpoint ne sont plus répétés ; les erreurs
actionnables, la liste des changements et les décisions Accepter/Restaurer
restent visibles quand elles s’appliquent.

Le profil Programmation ne porte plus `web_research`. Texte et voix démarrent
toujours une tâche, y compris si la formulation mentionne Internet. Une garde
backend refuse les quatre routes de génération conversationnelle avant leur
classification Web ou leur écriture SQLite pour tout profil `agent_runs`.
OpenHands reste hors ligne et son contrat lui demande de déclarer une donnée
externe manquante plutôt que de l’inventer. Général, Vétérinaire et le chat
éphémère conservent leurs autorisations Web manuelles existantes.

Les essais navigateur utilisent le vrai moteur Edge et le vrai frontend, mais
des API simulées. Ils ne constituent pas une nouvelle validation d’inférence,
de microphone physique, de haut-parleurs, de moteur vocal ou de Docker.
Le test SQLite/API emploie une base temporaire et un modèle simulé.
Les limites scientifiques de Vétérinaire et les refus prudents du Web restent
ceux des étapes précédentes. Une URL affichée n’est pas une garantie de vérité.

### Dernières retouches : séparateurs, alertes et résultat des tâches

Le bandeau supérieur possède le même séparateur que le panneau des ressources.
Lorsque le diagramme est visible, une ligne de grille commune aligne son bord
supérieur avec celui du pied de la barre latérale, y compris avec une alerte.
Le trait latéral rejoint les deux bords ; les boutons gardent leurs marges.
« Léa est prête » est retiré du pied de page. Les erreurs et transitions du cœur
sont centrées en haut, aussi dans les paramètres et la vue vocale. Aucun polling
ni calcul de taille JavaScript supplémentaire n’est ajouté.

La simplification précédente masquait aussi le résultat utile des tâches.
`AgentRunResult` réaffiche la réponse finale Markdown ou le motif d’échec reçu
du backend, indépendamment du diff et de la décision de checkpoint. Un run
échoué reste signalé comme tel même s’il contient une réponse partielle ; une
ancienne validation absente reste explicitement non vérifiée. Un checkpoint
vide indique « Aucun fichier modifié ».

Le run réel signalé par l’utilisateur (`8c8cf7db-05c8-4077-a8d3-cfdbb5a075ad`)
a été examiné en lecture seule : `state=failed`, `result_summary=null`, résultat
OpenHands `execution_error` / `OpenHandsExecutionError`, état terminal d’erreur.
Il ne contient aucune réponse finale à récupérer. Le correctif rétablit son
affichage honnête ; il ne prétend pas corriger cette défaillance agentique.
Aucun nouveau run réel ni accès au contenu du projet utilisateur n’a été lancé.

Vérifications de cette passe :

- `npm run test:frontend` : **63/63**, dont quatre tests du résultat de tâche.
- `npm run build` : TypeScript/Vite réussis ; JS 438,01 ko (135,40 ko gzip),
  CSS 21,95 ko (5,12 ko gzip).
- `backend/.venv/Scripts/python.exe -B tests/e2e/edge-stage17.py`, sur le build
  servi localement par Vite preview : **25 groupes réussis** dans Edge
  156.0.4314.58, 139 appels API simulés, aucune requête externe ni erreur JS.
  Alignement mesuré aux tailles prévues, trait bord à bord, alerte centrée,
  disparition après récupération, réponse sans diff et après Accept/rechargement.
- Interface habituelle HTTP **200**, contrôleur local **ready**. Serveur preview
  et navigateur jetable fermés après les tests, sans arrêter la session utilisateur.
- `git diff --check` réussi. Les **378 tests backend** consignés précédemment
  précèdent ces retouches exclusivement frontend ; ils n’ont pas été relancés ici.

Fichiers de cette passe : `src/App.tsx`, `src/components/ConversationSidebar.tsx`,
nouveau `src/components/AgentRunResult.tsx`, `src/styles/index.css`, nouveau
`tests/frontend/agent-result.test.tsx`, `tests/e2e/edge-stage17.py` et documentation
README/TODO/CHANGELOG/DECISIONS/ce rapport. Aucune dépendance ajoutée.

### Complément du 3 novembre : vrais runs et fil de programmation

La demande porte sur l'exécution réelle des tâches et sur leur présentation
conversationnelle. Aucun changement du moteur OpenHands, des poids, des contrats
de génération ni des protections réseau/workspace n'a été nécessaire.

**Diagnostic.** Le run utilisateur `76f685d2-e2c1-4b85-9b7e-3c19c5d0da16`
a effectivement exécuté 32 actions `file_editor view /workspace`, toutes suivies
d'une observation. Le projet `Test` était vide hors métadonnées internes Git.
Le modèle a répété la lecture du dossier jusqu'à `MaxIterationsReached` ; aucune
lecture du contenu d'un fichier texte n'est démontrée. Ce cas reste une limite
agentique, pas une réussite à masquer ni un motif pour ajouter une heuristique.

**Corrections d'interface.** L'envoi texte demandait seulement un run, sans
activer le contrat conversationnel déjà utilisé par la voix. Il utilise désormais
`record_conversation`, l'identifiant de conversation et les révisions/profil/projet
attendus. La consigne apparaît immédiatement, puis son tour persisté la remplace
sans doublon. La réponse, l'état en cours ou l'échec restent dans une bulle de Léa.
Les décisions Accepter/Restaurer accompagnent le résultat concerné ; le résultat
reste consultable après décision. Le panneau Projet est au-dessus du défilement,
avec l'annulation. Les anciens runs sans conversation restent affichables.

Une annulation terminait également le tour SQLite, mais la vue pouvait conserver
son ancienne révision. Elle relit maintenant la conversation avant d'autoriser la
tâche suivante. Les réponses tardives de sélection/diff sont ignorées et la
navigation ne détourne pas une tâche en cours vers une autre conversation.

**Essais réels.** Deux tâches ont utilisé le modèle local et les conteneurs
OpenHands existants, dans `L:\IA_WORKSPACE\Lea_RunCheck_b9a0cb18`, avec une base
SQLite isolée sous `.test-runtime/` :

| Run | Exécution observée | Résultat et décision |
| --- | --- | --- |
| `311239c4-7364-44fa-aca8-fe0f6678df89` | Lecture des deux fichiers Python, correction de `a - b` en `a + b`, `python -B -m unittest -v` vert, outil de fin. 106,4 s jusqu'au résultat. | `completed` / `validated`. Rollback effectué ; SHA-256 du fichier restauré identique à l'original. |
| `30873306-942f-417f-b037-b917b4688d0e` | Lecture de `note.txt`, restitution exacte de « Bonjour depuis le projet de controle Lea. », outil de fin. 67,8 s. | `completed` / `validated`, aucun fichier modifié. Accept effectué sur ce checkpoint sans changement. |

Le frontend réel a aussi été ouvert dans un Edge jetable pendant le second run :
consigne visible une seule fois, bulle de résultat et panneau Projet fixe. Cet
essai complète le banc d'interface simulé ; il ne valide pas le microphone.
La pause demandée auparavant avait annulé le premier essai de cette fixture
(`18a68639-055b-462c-a87f-b80b115bf2e9`) ; il n'est pas compté comme un succès.

**Vérifications finales.**

- `backend/.venv/Scripts/python.exe -B -m unittest discover -s backend/tests -q` :
  **379 tests réussis**, 43,499 s. Le nouveau test vérifie deux tâches conservées
  après un échec, un refus de révision périmée sans troisième run et l'interdiction
  d'accepter un run non validé.
- `npm run test:frontend` : **63 tests réussis**.
- `npm run build` : TypeScript/Vite réussis ; JS 439,62 ko (135,86 ko gzip),
  CSS 22,12 ko (5,15 ko gzip).
- `backend/.venv/Scripts/python.exe -B tests/e2e/edge-stage17.py`, avec Vite preview
  local : **26 groupes réussis**, Edge 156.0.4314.58, 150 appels API simulés,
  zéro requête externe et zéro erreur JavaScript. Deux consignes successives,
  annulation, sélection/rechargement, décisions et maintien de Projet vérifiés.
- Bases habituelle et isolée : `PRAGMA integrity_check = ok`, aucune erreur de
  clé étrangère. Les checkpoints de test contiennent les trois fichiers attendus,
  sans cache Python ; états finaux respectivement `rolled_back` et `accepted`.
- Aucun conteneur des deux essais ne subsiste, aucun conteneur OpenHands géré
  actif. Aucune suppression d'image, de volume, de conversation ou de checkpoint.
- Arrêt propre de la pile isolée avec `./lea.ps1 stop`, puis `./lea.ps1 start`
  sans `LEA_DB_PATH` : interface HTTP 200, Général `ready`, projet habituel `Test`,
  aucune génération, aucun run ni récupération en attente. Navigateur jetable
  et serveur preview fermés ; session habituelle laissée prête.
- `git diff --check` : réussi. Aucun commit ni push.

Fichiers de cette passe : `src/App.tsx`, `src/components/AgentRunResult.tsx`,
`src/styles/index.css`, `tests/frontend/agent-result.test.tsx`,
`tests/e2e/edge-stage17.py`, `backend/tests/test_openhands_api.py`, README, TODO,
CHANGELOG, DECISIONS et ce rapport. Aucune nouvelle dépendance. Les preuves de
test restent ignorées par Git dans `.test-runtime/` ; les journaux et checkpoints
conservés ne sont pas supprimés pour embellir le résultat.

**Limites.** Les contrôles ne rendent pas le modèle infaillible : le dossier vide
a provoqué une boucle et le premier succès a produit son bilan en anglais.
L'interface rapporte ces sorties sans les inventer. Les boutons de décision
suivent le dernier run de la conversation sélectionnée ; les tours précédents
conservent leur réponse dans l'historique. Cette passe n'ajoute pas un explorateur
de tous les checkpoints historiques ni de nouvelle récupération agentique.

### Ajustements du 4 novembre : arrêt, accueils, historique et alertes

Les quatre compléments demandés sont implémentés ensemble :

- Projet tient sur une ligne compacte et conserve le sélecteur et Actualiser.
  Son bouton Annuler est retiré. La commande principale affiche Conversation
  vocale à vide, Envoyer avec un brouillon, Arrêter la réponse pendant le travail.
  Un arrêt demandé pendant la création d'un run attend son identifiant puis
  appelle l'annulation vérifiée existante. La vue vocale peut aussi arrêter la réponse.
- Programmation et Vétérinaire possèdent chacun cinq titres spécialisés dans
  `Welcome.tsx`. Le titre apparaît seulement dans la vue vide, centré entre
  Projet et la saisie en Programmation. Il change à la navigation, sans minuteur.
- Les conversations contenant des runs restent dans la liste SQLite commune.
  Leur ouverture exige Programmation chargé ; la route GET applique aussi ce
  contrôle. Crayon et poubelle restent accessibles avec les autres profils.
  Le renommage ne charge plus la conversation et préserve le brouillon courant.
  Aucun déplacement de données ni migration du schéma.
- Les alertes RAM/CPU/VRAM et d'indisponibilité apparaissent au centre du bandeau
  supérieur. Le diagramme reste en bas. Un portail React déplace seulement le
  message de la collecte existante ; les alertes restent visibles diagramme
  masqué et dans les paramètres/la voix. À petite largeur, elles occupent une
  ligne centrée du bandeau pour préserver l'accès aux commandes.

### Messages courts et récupération du Frontend — 5 novembre

Les avertissements et erreurs visibles passent par une présentation commune,
sans modifier les erreurs backend, leurs statuts HTTP, les diagnostics conservés
ou les refus de sécurité. Les cas connus gardent leur motif utile, par exemple
« Ouvrez Docker Desktop », « Contexte trop long pour le modèle » ou
« Restauration refusée car le projet a changé ». Un diagnostic inconnu utilise
une phrase neutre liée à son contexte au lieu d'être tronqué et de perdre une
négation. Les alertes simultanées restent séparées par un point médian.

Le blocage du lanceur Frontend venait du bootstrap `npm.cmd`, conservé après que
le vrai listener `node` avait été identifié. Une identité ultérieurement ambiguë
de ce bootstrap empêchait à la fois `start` et `stop`. Après vérification de
l'ascendance, du PID et du port 5173, seul le listener `node` est désormais
persisté comme autorité du Frontend. Les anciens records `npm.cmd` sont détachés
sans adopter ni arrêter leur PID. Un listener ou un propriétaire de port inconnu
reste refusé comme avant.

Vérifications : 388 tests backend, 71 tests frontend, 31 groupes Edge, build de
production et tests PowerShell du lanceur réussis. Un cycle réel a démarré
Modèle, Backend et Frontend, affiché leurs trois PID comme actifs, puis libéré
les ports 8080, 8000 et 5173 ainsi que la VRAM à l'arrêt.

**Arrêt réel : diagnostic et correction.** Les premiers tests simulés confirmaient
la fermeture de la tâche HTTP, mais l'essai avec Général a révélé que le transport
non diffusé laissait llama.cpp travailler : son slot était encore occupé après
11,562 secondes d'observation. Ce résultat n'a pas été présenté comme un succès.
Le transport utilise maintenant un flux SSE interne, assemblé en RAM, avec un
délai total borné et une fin contrôlée. Aucun fragment ni pensée interne ne rejoint
l'interface ou SQLite ; les validations finales restent obligatoires.

Le second essai réel a observé `is_processing=true`, puis l'arrêt HTTP confirmé,
une réponse 409 « La réponse a été interrompue. », et `is_processing=false` après
**5,578 secondes**. Une nouvelle demande dans la même session a reçu HTTP **200**.
La session éphémère de test a ensuite été effacée (204), et Programmation réactivé
(200). Les preuves techniques sans contenu utilisateur sont dans les fichiers
ignorés `.test-runtime/response-stop-real-before.json` et `response-stop-real.json`.
Le délai observé est une limite pratique : ce bouton n'est pas un arrêt instantané
d'une opération de calcul déjà engagée. Aucun nouveau run Docker n'était nécessaire
pour déplacer sa commande d'annulation ; son parcours est couvert par les tests API
et Edge, et les vrais runs du 3 novembre restent les preuves agentiques précédentes.

**Validation automatisée et environnement.**

- `backend/.venv/Scripts/python.exe -B -m unittest discover -s backend/tests -q` :
  **388 tests réussis**, 45,304 s. Annulation de Général/Vétérinaire, modification,
  réessai, collecte/synthèse Web, session RAM, jetons inconnus/dupliqués, origine
  externe refusée, fermeture des enfants et nouvelle demande après interruption.
  Les tests de transport couvrent Unicode fragmenté, réflexion exclue, flux coupé,
  JSON malformé, limite de sortie, dépassement de contexte et fermeture HTTP.
- `npm run test:frontend` : **64 tests réussis**. `npm run build` réussi.
- Banc `tests/e2e/edge-stage17.py` servi par Vite preview : **30 groupes réussis**,
  Edge 156.0.4314.58, 188 appels API simulés, zéro requête externe et zéro erreur JS.
  Six dimensions jusqu'à 320 × 568, états voix/envoi/arrêt, titres spécialisés,
  continuité après arrêt, renommage/suppression hors profil et centrage des alertes.
- Redémarrage du cœur pour charger le backend corrigé ; profil Programmation et
  projet habituel `Test` rétablis. Serveur preview et Edge jetable fermés.
- `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, `git diff --check` et état
  final du démarrage contrôlés. Aucun commit, push ni suppression de donnée utilisateur.

Fichiers concernés : `src/App.tsx`, `src/components/Welcome.tsx`, `VoiceControls.tsx`,
`ResourcePanel.tsx`, `ConversationSidebar.tsx`, `src/hooks/useEphemeralChat.ts`,
`src/lib/conversations.ts`, `src/styles/index.css`, `backend/app/main.py`,
`database.py`, `inference.py`, `backend/tests/test_response_cancellation.py`
(nouveau), `test_openhands_api.py`, `test_inference.py`,
`tests/frontend/welcome.test.tsx`, `tests/e2e/edge-stage17.py` et documentation.
Aucune dépendance, aucun modèle ni composant de la prochaine étape ajouté.

### Vérification manuelle avant clôture

Dans Edge, valider avant clôture :

1. Apparence des deux thèmes, redimensionnement et zoom ; barre latérale et clavier.
2. Réponse réelle avec titres, liste, tableau, code ; copie et rechargement.
3. Historique, recherche, modification/régénération, mémoire explicite existante.
4. Profils Général et Vétérinaire, Low/High indépendants, paramètres conservés.
5. Consentement Web textuel, sources, annulation et erreurs lisibles en Général
   et Vétérinaire ; absence de Web conversationnel en Programmation.
6. Dictée avec le microphone physique, conversation vocale et les deux voix.
7. Docker ouvert manuellement, consigne dans la saisie inférieure, petit run
   Programmation, arrêt depuis la saisie, diff, Accept ou Rollback ; historique
   verrouillé hors Programmation, crayon et poubelle toujours disponibles.
8. Diagramme facultatif et arrêt/redémarrage habituel de Léa.

Pour le packaging futur, conserver les composants locaux, prévoir la persistance
de l’origine de l’interface ou le transfert explicite du seul thème, et traiter
alors la configuration de l’origine backend. L’adresse loopback existante n’a
pas été refondue ici. Aucun composant visuel ajouté ne contient un chemin disque
propre au PC ; aucune migration vers SSD ou application Windows n’est réalisée.
