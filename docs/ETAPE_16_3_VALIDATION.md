# Étape 16.3 — Rapport de validation technique

Date : 25 octobre 2026

État : implémentation technique terminée ; campagne globale réalisée, correctifs
finaux en attente de revalidation utilisateur

Périmètre : navigation Web publique en lecture seule uniquement

## A. Résultat

Le Web Gateway peut maintenant rendre certaines pages publiques dont le contenu
utile est produit par JavaScript. La recherche légère, la lecture HTTP classique
et l’extraction statique restent prioritaires. Edge ne démarre que si le HTML
reçu présente une coquille JavaScript générique et trop peu de texte exploitable.

Le même permis manuel 16.1, consommé avant le premier accès réseau, couvre ce
dernier recours. Une page, un script, le modèle ou un échec ne peut pas créer,
renouveler ou élargir cette autorisation.

## B. Moteur et cycle de vie

- `playwright==1.64.1` a été installé dans `backend/.venv` après accord. Le paquet
  Windows téléchargé faisait 38,8 Mo ; aucun navigateur Playwright n’a été installé.
- `EdgeDynamicPageReader` utilise l’exécutable Microsoft Edge Stable déjà présent
  sous `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`.
- Le constructeur ne lance aucun processus. Un verrou autorise une seule session
  dynamique à la fois.
- Chaque session utilise un profil `lea-edge-*` neuf sous un dossier temporaire.
  Elle n’ouvre jamais le profil Edge personnel.
- Le contexte bloque téléchargements et service workers, n’accorde aucune
  permission et désactive extensions, QUIC, WebRTC non proxifié, notifications,
  synchronisation et réseau de fond connu. Le sandbox Edge reste activé.
- Succès, erreur, annulation du tour et annulation de la tâche backend ferment le
  contexte, le pilote, le proxy, les connexions et le profil temporaire.

## C. Barrière réseau

La seule interception Playwright n’est pas considérée comme une isolation réseau.
Un proxy HTTP(S) loopback est créé pour chaque opération et imposé à Edge, y
compris pour les destinations loopback que Chromium contourne normalement.

Le proxy :

- accepte seulement l’hôte exact de la page initiale ;
- réutilise `SafeHttpFetcher.validate_url()` et
  `resolve_public_destination()` ;
- résout toutes les adresses, refuse le nom entier si une IP n’est pas globale,
  puis connecte l’IP publique choisie ;
- accepte uniquement les ports 80/443 ;
- refuse les hôtes tiers, localhost, réseaux privés/réservés et schémas non Web ;
- limite les connexions à 24 et le trafic cumulé à 12 Mio.

Playwright ajoute une seconde barrière : méthodes GET/HEAD seulement, ressources
limitées à document, script, feuille de style, XHR et fetch, hôte initial exact,
80 requêtes au maximum et URL sensibles refusées. Cookies et autorisations du
profil personnel sont absents puisque le profil est neuf ; les en-têtes visibles
d’authentification sont retirés. Les cookies éventuellement créés par le site
restent confinés à la session jetable et ne sont pas retrouvés au lancement suivant.

## D. Lecture autorisée

- Une page principale et deux pages de pagination au maximum.
- Navigation directe vers l’URL validée d’un lien `rel=next` ou dont le libellé
  est explicitement « next », « suivant », « page suivante » ou équivalent borné.
- Aucun `click()` n’est émis.
- Les tableaux sont lus comme texte DOM.
- Les contenus de `<details>` fermés sont lus par `textContent`, sans changer
  l’attribut `open` ni déclencher d’événement.
- Les liens de fichiers connus, au même hôte, peuvent être rapportés comme liens
  non ouverts ; ils ne sont jamais téléchargés.
- Texte final limité à 8 000 caractères, trois pages, 80 requêtes et 20 secondes.

Les fenêtres secondaires sont immédiatement fermées. Les dialogues sont rejetés.
Un formulaire, un bouton, une connexion, un achat, un paiement, une réservation,
un message ou une publication ne sont jamais remplis ni actionnés. Une page de
connexion, un CAPTCHA, un paywall ou une URL transactionnelle est refusé.

## E. Intégration et persistance

`WebGateway._extract_candidate()` tente d’abord le transport HTTP 16.1/16.2. Il
appelle le lecteur dynamique seulement après détection déterministe d’un HTML
insuffisant : marqueur JavaScript requis, racine d’application vide ou très peu
de texte accompagné d’un script qui construit le contenu. Un HTML statique court
mais complet reste sur le parcours normal.

Le texte rendu retourne dans les protections existantes : donnée non fiable,
contexte borné, citations `[S…]` attribuées par le backend, validation des dates
et verdict prudent. La migration SQLite 16 ajoute seulement `dynamic_html` à
`web_sources`. Sont conservés : titre, URL finale, domaine, résumé, fournisseur,
dates déclarées, statut et limite. HTML brut, capture, profil, cookie et script ne
sont jamais persistés.

## F. Tests automatisés

Le site local isolé de `backend/tests/test_dynamic_browser.py` vérifie avec le
vrai Edge installé :

- rendu JavaScript à la demande ;
- trois pages de pagination et refus de la quatrième ;
- tableau et section native fermée ;
- aucun POST depuis un formulaire ou bouton transactionnel ;
- lien de téléchargement rapporté mais jamais demandé ;
- sous-ressource localhost et redirection localhost bloquées ;
- `file://` et origine loopback non explicitement réservée au test refusés ;
- connexion et CAPTCHA refusés ;
- texte d’injection conservé comme donnée ;
- cookie de site absent d’une nouvelle session ;
- annulation utilisateur et annulation de tâche ;
- suppression du profil et fermeture du navigateur après succès et erreur.

Les tests Web Gateway ajoutent l’absence de navigateur pour un HTML statique,
l’absence de recours sans permis, le recours exact pour une coquille JS et le
refus d’un écran d’authentification. La migration 14→15→16, le libellé frontend
et toutes les suites 16.1/16.2 sont également couverts.

Résultats de clôture : 333 tests backend réussis, dont 8 sessions locales avec
le vrai Edge ; 45 tests frontend réussis ; build TypeScript/Vite réussi ; registre
des trois profils validé. Le démarrage réel a exposé l’API saine, Général actif
et le schéma SQLite 16, puis l’arrêt a libéré les ports 8080, 8000 et 5173.
`git diff --check` a réussi après le nettoyage final. L’avertissement restant est
la dépréciation déjà connue de `starlette.testclient` avec `httpx`.

## G. Essais Internet réels

1. `https://quotes.toscrape.com/js/` a d’abord été lu par HTTP. Son texte statique
   ne contenait que l’en-tête ; la détection générique a déclenché Edge. Trois
   pages JavaScript ont été rendues, 6 480 caractères ont été extraits lors de
   l’essai direct et le flux complet a produit une source `dynamic_html`, statut
   `read`, avec une limite indiquant trois pages et aucune interaction.
2. `https://example.com/` a été lu par un `WebGateway` sans lecteur dynamique.
   La source est restée `html/read`, ce qui confirme le chemin statique normal.
3. Après les essais, `Get-Process msedge` retournait zéro processus et
   `data/browser-sessions` n’existait plus.

Aucune conversation, page brute ou donnée personnelle n’a été utilisée pour ces
essais. Les observations dépendent de l’état public des sites le 25 octobre 2026.

## H. Limites assumées

Le proxy applicatif, les options Chromium et l’interception Playwright ne sont
pas un pare-feu ou un espace réseau isolé au niveau du système d’exploitation.
Le tunnel TLS reste chiffré de bout en bout : le proxy contrôle hôte, port, DNS,
IP et volume, tandis que Playwright contrôle méthode et type de requête. Cette
combinaison a été testée, mais n’est pas présentée comme une preuve formelle de
tous les comportements internes futurs d’Edge.

Pour réduire ce risque, Léa refuse volontairement :

- CDN, API et redirections vers un autre hôte, même publics ;
- pagination ou section qui exige un bouton ou un script d’action ;
- authentification, CAPTCHA, paywall et protection anti-robot ;
- téléchargement, média, WebSocket et protocole autre que HTTP(S) ;
- toute méthode autre que GET/HEAD.

Un GET n’a pas une sémantique universellement sans effet secondaire. Léa ne
possède aucun compte, cookie personnel ni autorisation, filtre les chemins
transactionnels connus et n’émet aucun clic, mais ne peut pas prouver la
sémantique métier de chaque URL publique. En cas de doute, l’action demeure
inaccessible. Les politiques Edge d’entreprise peuvent aussi empêcher ou altérer
le lancement ; aucun contournement n’est prévu.

## I. Validation manuelle initialement différée

Conformément à la demande utilisateur, aucun test fonctionnel manuel intermédiaire
dans Edge n’a été demandé. La campagne unique de fin d’étape 16 devra notamment
vérifier une page dynamique publique compatible, une page statique, les sources
`dynamic_html`, un échec d’authentification lisible, l’annulation, puis l’absence
de navigateur au repos, en plus des scénarios scientifiques et factuels 16.1/16.2.

La phase 16.3 s’arrête ici. Aucune étape 17, vision, automatisation OpenHands,
nouveau modèle, commit ou push n’est réalisé.

## J. Commandes principales exécutées

```powershell
.\backend\.venv\Scripts\python.exe -m pip install playwright==1.64.1
.\backend\.venv\Scripts\python.exe -B -m unittest backend.tests.test_dynamic_browser -v
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -p 'test_*.py' -q
npm run test:frontend
npm run build
.\backend\.venv\Scripts\python.exe -B tools/model_config.py
.\lea.ps1 start
.\lea.ps1 status
.\lea.ps1 stop
.\backend\.venv\Scripts\python.exe -m pip check
git diff --check
git status --short
```

Les essais publics ont invoqué directement `WebGateway` et
`EdgeDynamicPageReader` sur les deux URL consignées en section G, sans modèle ni
écriture de conversation.

## K. Correctifs issus de la campagne manuelle globale

La campagne manuelle a révélé que le refus déterministe d’une donnée actuelle ne
créait pas l’attente Web correspondante. Une réponse telle que `Oui, vas-y`
devenait alors une génération locale. Dans l’ancien chemin de confirmation
ambiguë, la collecte retrouvait la bonne requête, mais la synthèse recevait la
confirmation courte comme question courante. Ces deux défauts expliquent les
faux blocs `[Tech]`, le mélange avec un ancien sujet et les références inventées
observés ; aucune consultation Web réelle n’avait eu lieu dans le premier cas.

L’attente est maintenant créée pour les deux chemins et liée à la question, au
message source, à la conversation, au profil, à la révision et à une expiration.
La confirmation est consommée avant le réseau et remplacée par la question
initiale pour la collecte comme pour la synthèse. L'historique des anciens tours
est exclu de cette nouvelle synthèse Web. Une confirmation orpheline,
expirée, réutilisée, modifiée, inter-conversation ou inter-profil ne recherche
rien et demande une nouvelle autorisation.

Les réponses locales qui simulent un outil ou une consultation Web, ainsi que
les citations présentées comme probantes sans collecte, sont refusées par le
backend. En recherche simple, le passage lu reste en RAM pendant le contrôle de
correspondance avec la citation. La sélection écarte le hors-sujet manifeste et
respecte un domaine explicitement écrit. Les scores structurés conservent leurs
associations équipe-nombre ; une inversion ou une contradiction documentée
produit un refus prudent. L’URL officielle directe déjà fonctionnelle reste
prioritaire et aucun résultat particulier n’est codé en dur.

Web désactivé produit désormais un message de conversation persistant sans
réseau ni modèle. Le frontend reconnaît `Oui`, `Vas-y`, `Oui, cherche` et
`Oui, vas-y` pour synchroniser l’indicateur avec la collecte contrôlée.

La validation finale comprend 77 tests Web ciblés, 348 tests backend complets et
45 tests frontend, tous réussis, ainsi qu’un build TypeScript/Vite réussi. Un
essai réel isolé a exécuté météo actuelle → proposition déterministe →
`Oui, vas-y` → Web Gateway → synthèse locale. Trois sources ont été lues et
persistées dans la réponse temporaire sous les identifiants `S1` à `S3` :
`www.meteocity.com`, `meteo.gc.ca` et `www.meteocanada.com`. La première réponse
avait `model_id=null`, l’attente a été consommée et la base utilisateur n’a pas
été modifiée.

La base active passe `integrity_check=ok`, ne contient aucune violation de clé
étrangère et démarre sous le schéma 16. Les trois profils sont exposés par le
registre. Le cycle réel arrêt → démarrage → endpoints sains → arrêt a libéré les
ports 5173, 8000, 8080, 8081 et 18010 ; aucun `llama-server`, état de processus
ni `stdin.empty` ne subsiste. L’ancien incident d’un processus sans état signé
n’a pas été reproduit : le superviseur fail-closed reste volontairement inchangé.

Limites : le rattachement sémantique des citations reste lexical et le contrôle
sportif exige une forme textuelle structurée. Une source sans score explicite,
un alias d’équipe ambigu ou une formulation complexe ne devient pas une preuve
automatique. La campagne manuelle Edge doit donc rejouer les scénarios listés
dans le rapport final avant de clore l’étape 16.

## L. Stabilisation finale avant revalidation utilisateur

Le dernier retour manuel a mis en évidence des défauts distincts, désormais
reproduits par des fixtures : le frontend conservait un second signal
d’autorisation, la borne fournisseur de 500 caractères était appliquée au message
entier, une URL documentaire héritait à tort de l’exigence multi-source, la
sélection sportive pouvait accepter des pages de ville hors sujet et la
pagination attribuait tous les extraits à sa dernière URL. Une phrase contenant
un numéro de version était aussi découpée au premier point, ce qui déclenchait un
repli malgré une citation valide.

La stabilisation supprime la case et le booléen `web_authorized`, sans changer la
préférence globale ni les permis en RAM. Une URL directe utilise maintenant le
mode documentaire, sauf demande explicite de corroboration indépendante. Les
requêtes fournisseur seules restent limitées à 500 caractères. L’extraction HTML
peut exploiter la partie reçue sous la borne existante de 768 Kio, en déclarant
la lecture partielle et en sélectionnant les passages liés à la question.

Les preuves sportives exigent désormais un contexte sportif réel ; les nombres
et versions d’une affirmation citée doivent apparaître dans la source. Chaque
page Edge paginée porte son URL exacte sous un identifiant distinct. Le contrat
de fiabilité 2.1 est vérifié en tête des trois profils et les messages de capacité
emploient un français naturel à la première personne.

Les tests ciblés de cette passe couvrent les messages longs, le contrat d’envoi
strict, la source documentaire unique, la corroboration indépendante, le hors
sujet sportif, les citations valides ou inventées, l’attribution équipe-score,
le HTML partiel, la pagination et les erreurs spécialisées. Ils totalisent 96
tests réussis, y compris les parcours Edge locaux. La revalidation manuelle des
cas NHL, Python, IRIS, vidéo et consentement reste à la charge de l’utilisateur ;
l’étape 16 n’est pas déclarée définitivement validée ici.

La non-régression complète de cette passe compte 356 tests backend et 46 tests
frontend, tous réussis, ainsi qu’un build TypeScript/Vite, `pip check` et la
validation du registre. Un premier démarrage complet a atteint les trois
endpoints mais a échoué lors de la confirmation finale du superviseur ; son
rollback a libéré les ports. Le démarrage isolé du cœur, puis deux démarrages
complets ont ensuite réussi sans modification du cycle de vie. Cet événement
transitoire non reproduit reste signalé plutôt que masqué par un nouveau correctif.

## M. Vérification répétée avant revalidation

La relecture du flux vocal a mis en évidence une course dans l'annulation :
`MediaRecorder.stop()` pouvait lever une erreur après une lecture de l'état
`recording`, interrompant la libération des pistes. Un test reproduit ce cas ;
l'annulation libère maintenant le microphone même lorsque cet arrêt échoue.
Les sections vocales concernées ont été aérées sans changer leurs contrats.

La suite complète réussit : 359 tests backend, 48 tests frontend et le build
TypeScript/Vite. `pip check` ne signale aucune dépendance brisée. La base active
répond `integrity_check=ok`, sans violation de clé étrangère, sous le schéma 16.
Le backend existant répond `ok` sur `/health` et Vite répond HTTP 200 ; la
session utilisateur active n'a pas été interrompue. `git diff --check` passe.
Ces contrôles automatisés ne remplacent pas la revalidation manuelle Edge
annoncée plus haut, ni un essai avec un microphone physique.

## N. Incident de synthèse Web du 29 octobre 2026

Les deux erreurs manuelles ont atteint le modèle après collecte de trois sources.
`llama-server` a rejeté leurs prompts de 8 369 et 8 287 tokens pour une fenêtre
de 8 192, avant toute sortie (`n_tokens=0`). Le prompt système Général seul
occupait 6 432 tokens ; l'ancien budget estimait le reste sans compter sa taille
réelle. Le backend ramenait ensuite ce rejet à l'erreur générique de synthèse.
Les sources de ces tours échoués n'ayant pas été persistées, leur contenu exact
et la présence d'une température ne peuvent pas être établis a posteriori.

Le comptage préalable passe maintenant par `/apply-template` et `/tokenize` du
moteur local. Les extraits envoyés au modèle sont réduits par paliers bornés,
sans modifier les preuves intégrales utilisées par le validateur ni la fenêtre
configurée. Une sortie tronquée et un dépassement ont des erreurs distinctes.
Les valeurs numériques exigent une citation, et une mesure citée doit figurer
avec son unité dans la page réellement lue. Une nouvelle requête explicitement
autorisée peut suivre un échec Web dans la même conversation, avec une collecte
et un permis distincts.

Une collecte publique de trois pages lisibles a reproduit le dépassement avec
un prompt de 8 301 tokens. Après réduction, un essai réel séparé a présenté
7 484 tokens au même modèle, qui a produit une réponse sourcée acceptée par le
validateur. Un parcours API isolé avec des preuves déterministes et le vrai
modèle a ensuite réussi deux recherches successives dans la même conversation.
Les suites complètes donnent 367 tests backend et 48 tests frontend réussis ;
le build, `pip check` et `git diff --check` passent. Ces essais ne constituent
pas une revalidation manuelle dans Edge et ne garantissent pas la disponibilité
future des fournisseurs ou la justesse de toute page publique. Le cœur a été
arrêté puis redémarré avec `lea.ps1 stop-core` et `start-core` ; modèle et backend
répondent, et le frontend resté ouvert sert HTTP 200.

## O. Préparation de clôture — comportement stable et limites explicites

### Fonctionnalités implémentées et vérifiées

La lecture Web reste liée à une demande textuelle explicite ou à la confirmation
en RAM de la question exacte, sous préférence Web active. La case ponctuelle est
supprimée. Les URL publiques directes, les recherches bornées, les documents
uniques, les PDF textuels, les textes vidéo accessibles et le recours Edge public
éphémère conservent leurs protections réseau et leurs statuts de lecture. Le
contrat `reliability.md` 2.1 et le validateur backend refusent les identifiants
de source inventés et les valeurs chiffrées sans preuve lisible correspondante.

Le dernier commit Git précédant cette passe est l'étape 15 : aucune version
intermédiaire manuellement validée de l'étape 16 n'était récupérable par un
reset. Le correctif de budget de contexte a donc été conservé : sur les pages
directes examinées, le prompt complet tenait déjà dans la fenêtre et ce correctif
n'expliquait pas les refus. Le défaut démontré était ailleurs : la sélection
HTML avait écarté le début de Python.org contenant la date de sortie, et le
modèle pouvait omettre la citation sur une seconde phrase malgré une preuve lue.
La lecture directe HTML privilégie maintenant son ouverture sous la même limite
de 1 200 caractères ; les PDF et les recherches générales gardent leur sélection
existante. Une instruction documentaire courte est placée après le bloc Web.

Dans des essais isolés avec le vrai modèle local, l'API a lu une page officielle
des Canadiens et la page Python 3.14.0, puis a publié deux réponses courtes avec
`[S1]` accepté par le validateur. Les deux questions demandaient explicitement
une seule phrase citant `[S1]` ; des formulations moins cadrées ont encore
produit une seconde phrase non citée, refusée par le backend. La première source
établissait le score 4–1
contre Chicago et les deux buts de Jake Evans ; la seconde annonçait la sortie
du 7 octobre 2025. Les tests automatiques vérifient aussi l'absence de réseau
sans consentement, la source documentaire unique, les erreurs honnêtes, les
citations refusées et les protections SSRF.

### Limites connues acceptées

- Les fournisseurs publics peuvent être indisponibles et une URL publiée par un
  moteur peut désormais rediriger vers une page d'erreur. Une telle page ne
  prouve pas le fait recherché ; l'essai a utilisé une autre URL officielle lue.
- Le modèle local peut répondre en plusieurs phrases avec une seule citation
  en tête ou oublier une citation. Le backend refuse alors les chiffres non
  rattachés à une preuve et affiche une limite honnête. Une sortie courte réussie
  ne garantit pas toutes les formulations futures.
- Le contrôle de provenance est déterministe et lexical. Il ne certifie ni la
  vérité éditoriale d'une page ni toutes les relations sémantiques possibles.
  Une source unique permet de décrire ce qu'elle dit, pas de confirmer à elle
  seule un fait général indépendant.

### Améliorations facultatives reportées

Aucune optimisation propre à la météo, nouvelle récupération automatique de
synthèse, extension du contexte, nouveau modèle ou modification du rendu
Markdown n'est ajoutée pendant cette clôture. Ces sujets ne bloquent pas la
version stable et honnête demandée ici.

### Blocage restant

Aucun contournement de consentement, de provenance ou de politique réseau n'a
été observé dans les tests de cette passe. La revalidation manuelle finale dans
Microsoft Edge et la décision de clôture de l'utilisateur restent attendues ;
les essais isolés ne les remplacent pas.

La vérification de clôture compte 368 tests backend et 48 tests frontend réussis,
un build TypeScript/Vite et `git diff --check` sans erreur. Les dossiers
temporaires des tests ont été libérés automatiquement ; aucun nettoyage global
de fichiers ou de données utilisateur n'a été effectué.
Le cœur a été arrêté puis redémarré avec le correctif : `/health` répond `ok`
et l'interface restée ouverte répond HTTP 200. La sauvegarde de travail est
conservée dans `.lea/backups/stage16-closure-20261029`.
