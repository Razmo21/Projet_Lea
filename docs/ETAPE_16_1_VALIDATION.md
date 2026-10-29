# Étape 16.1 — Rapport de validation technique

Date : 22 octobre 2026 ; correctif d’accès Web : 23–24 octobre 2026
État : phase techniquement acceptée ; campagne globale réalisée, correctifs
finaux en attente de revalidation utilisateur
Périmètre historique : phase 16.1 uniquement ; la suite 16.2 est documentée séparément

## A. Fonctionnalités réalisées

- Recherche Web gratuite après accord explicite : DuckDuckGo Lite prioritaire,
  puis une seule tentative Bing HTML si le premier fournisseur échoue.
- Lecture bornée de pages HTML publiques simples et ouverture directe d’une URL.
- Permission backend éphémère, liée à une requête, consommée avant le réseau et
  impossible à réutiliser.
- Confirmation en RAM pour une intention ambiguë ou une requête semblant privée.
- Préférence générale `web_enabled`, désactivée par défaut, sans mode automatique.
- Même Web Gateway pour Général, Programmation et Vétérinaire.
- Sources cliquables persistées avec domaine, fournisseur, dates disponibles et
  statut de lecture ; aucune page HTML complète conservée.
- Indicateur de recherche, erreurs lisibles et annulation depuis l’interface.
- Demande vocale explicitement Web dirigée vers le même contrat backend.
- Réponse backend déterministe pour une information actuelle sans accord Web :
  aucun appel modèle ou réseau, sans bloquer une question historique datée.
- Origine persistée des échecs Web afin de ne plus les afficher comme une panne
  générique de génération du modèle.
- Après un échec Web, une nouvelle recherche repart d'un brouillon neuf et
  exige un nouvel envoi ; retry et modification ne recyclent jamais l'accord consommé.

## B. Principaux fichiers créés ou modifiés

- `backend/app/web_gateway.py` : autorisations, fournisseur, client HTTP sûr,
  extraction HTML, normalisation et contexte Web non fiable.
- `backend/app/main.py` : orchestration conversationnelle, annulation et partage
  entre profils.
- `backend/app/migrations.py`, `backend/app/database.py` : migrations 13 et 14,
  préférence, sources attachées aux réponses et origine bornée des échecs.
- `backend/app/preferences.py`, `tools/preferences.py`, `src/preferences.ts` :
  persistance locale du réglage hors modèle.
- `src/App.tsx`, `src/Settings.tsx`, `src/conversations.ts`, `src/index.css` :
  consentement, état en cours, annulation et sources.
- `config/models.json` et `config/prompts/*.md` : capacité déclarée et adaptation
  minimale des trois contrats à des extraits Web non fiables.
- `backend/tests/test_web_gateway.py` et tests existants : cas réseau, API,
  préférences et frontend.
- `AGENTS.md`, `README.md`, `TODO.md`, `CHANGELOG.md`, `docs/DECISIONS.md` :
  état, limites et décision d’architecture.

## C. Architecture

Le Web Gateway est un module du backend FastAPI existant. Le navigateur envoie
la question et un UUID d’annulation ; il n’envoie jamais l’historique ni un
booléen d’autorisation. Le backend déduit l’accord du texte explicite ou consomme
une confirmation rattachée à la demande exacte. `WebAuthorizationManager` garde
permis et confirmations en RAM.
`WebGateway` consomme le permis, appelle la chaîne bornée de `SearchProvider`, lit les pages via
`SafeHttpFetcher`, puis joint des extraits inertes au dernier message destiné au
modèle local. Le modèle ne possède aucun outil réseau.

`DuckDuckGoHtmlProvider` utilise l’interface publique Lite. Après un échec public,
`BingHtmlProvider` peut faire une seule tentative indépendante ; les liens de
suivi Bing sont décodés sans les consulter afin que la source finale soit citée.
L’interface `SearchProvider` conserve la même autorisation et la même barrière
HTTP pour les deux. Trafilatura n’a pas été ajoutée : le besoin 16.1 est couvert par le
parseur standard borné, sans nouvelle dépendance. La lecture ignore scripts,
styles, formulaires, navigation, pieds de page et blocs latéraux ; elle récupère
une date uniquement lorsqu’une métadonnée HTML la déclare réellement.

Le profil Programmation utilise l’endpoint local du modèle pour synthétiser ces
extraits, mais aucun outil OpenHands n’est engagé. Une recherche ne crée donc ni
Agent Server, ni run, ni checkpoint et ne donne aucun réseau au terminal.

### Correctif après les premiers essais Edge

Deux causes distinctes ont été reproduites le 23 octobre :

- le frontend reconnaissait une formulation comme « Cherche sur Internet… » pour
  son indicateur, mais transmettait encore seulement l’état de la case Web dans
  `web_authorized`. Ce premier correctif a aligné l’accord effectif du tour. La
  stabilisation finale a ensuite supprimé la case et le champ : le backend
  reclasse toujours lui-même le texte, vérifie `web_enabled`, émet le permis et
  le consomme avant le réseau ;
- l’interface HTML classique de DuckDuckGo a présenté une protection externe.
  L’interface publique Lite a alors été retenue comme endpoint prioritaire après
  comparaison réelle. Aucun second passage DuckDuckGo ni contournement n’est fait.

La requête brute contenait aussi la directive d’interface « Cherche sur
Internet », qui dégradait les résultats et pouvait provoquer une page de
protection. Une expression déterministe retire seulement cette directive
initiale ; le modèle ne reformule jamais la requête et le permis reste lié au
message original. Enfin, le parseur de page appelait `.lower()` sur une valeur
absente lorsqu’une balise `<meta>` ordinaire ne portait ni `property`, ni `name`,
ni `itemprop`. Ce cas HTML réel est maintenant accepté et couvert par un test.

Les échecs DNS/connexion, timeout, HTTP, protection externe, absence de résultat
et structure HTML incompatible ont des messages distincts. Le journal technique
conserve seulement l’étape, l’hôte, le type d’exception et le statut HTTP ; il
n’enregistre ni la requête, ni le chemin, ni le contenu de page.

### Correctif de fiabilité après la seconde validation manuelle

La requête naturelle sur le dernier match des Canadiens a reproduit le défaut :
DuckDuckGo Lite renvoie HTTP 200, mais le document contient son formulaire de
protection et aucun résultat. Les mêmes conditions réussissent sur les requêtes
Python, météo et actualité ; l’échec est donc intermittent et lié à la requête,
pas à l’inférence locale. Le backend marquait pourtant la question avec
`model_error`, et le frontend affichait tout message échoué comme « Échec de la
génération ». La migration additive 14 conserve désormais un `failure_kind` Web
borné ; le détail HTTP et le libellé persistant distinguent réseau, délai,
blocage, résultat vide, extraction et indisponibilité collective.

Onze instances SearXNG publiques distinctes ont été essayées : HTTP 429, contrôle
de sécurité ou défi anti-robot, sans résultat statique exploitable. Elles ne sont
pas intégrées. Bing HTML a répondu sans compte ni clé aux quatre catégories. Le
secours reçoit au plus une requête composée uniquement des mots déjà autorisés ;
les noms propres sont placés en tête pour éviter que le moteur ne traite seulement
la formule interrogative. Son fournisseur est persisté avec chaque source.

L'essai factuel a ensuite montré que Bing trouvait seulement des pages d'accueil
NHL/RDS, insuffisantes pour établir le score. La même condensation déterministe
est donc appliquée avant l'unique requête primaire, et non comme une relance après
un défi. Pour la question sportive, elle conserve exactement `Canadiens Montréal
résultat dernier match` : DuckDuckGo répond alors normalement avec la page de
résultats récente. Aucun terme, score, adversaire ou date n'est ajouté, aucun
CAPTCHA n'est résolu et le budget reste d'une tentative par fournisseur.

Un échec Web persisté exige par ailleurs un nouvel accord de l'utilisateur. Les
routes historiques de retry et d'édition le refusent côté serveur, même si le
texte seul paraît local. Dans l'interface, l'action recopie la question dans une
nouvelle conversation, coche Web, puis attend un nouveau clic sur Envoyer. Le
tour échoué reste intact et aucune permission n'est réutilisée.

Les contrats contenaient déjà une règle générale sur les informations périmées,
mais le modèle ne l’a pas appliquée pendant l’essai sans Web. Un premier
correctif ajoutait seulement une consigne de tour. Le test manuel « Quel temps
fait-il actuellement à Québec ? » a révélé deux causes restantes : la tournure
« quel temps fait-il » n’était pas couverte par le lexique météo, et une question
reconnue était encore transmise à Qwen, qui pouvait ignorer la consigne.

Le détecteur couvre désormais cette intention météo française. Pour toute
catégorie actuelle reconnue sans accord réseau, l’orchestrateur finalise lui-même
une réponse honnête, sans appeler le modèle, le fournisseur ou le transport HTTP
du Web Gateway. La réponse propose une autorisation ponctuelle si le réglage Web
est actif, ou son activation dans Paramètres sinon. Elle porte un `model_id` nul
et aucune source. Les années passées et connaissances stables suivent toujours
le modèle local normal.

## D. Tests exécutés

Tests déterministes couverts : accord explicite, absence/désactivation de
l’accord, expiration et réutilisation, confirmation en attente, requête privée,
non-transmission des souvenirs, fournisseur vide ou malformé, MIME invalide,
timeout, taille, URL locale, DNS mixte, redirection dangereuse, HTML malveillant,
prompt injection, annulation pendant la collecte ou la synthèse, persistance des
sources et compatibilité des trois profils. Le correctif ajoute DuckDuckGo
disponible/bloqué, secours disponible/indisponible, deux fournisseurs en échec,
budget de deux tentatives, fournisseur réellement cité, météo actuelle, dernier
score, actualités récentes, version actuelle, contre-exemples historiques et
absence mesurée d’appel modèle/fournisseur/transport sans accord. Les fournisseurs utilisent
HTML ; le cas « JSON invalide » du prompt est donc représenté par une réponse
fournisseur malformée et non par un parseur JSON inutilisé.

Commandes réellement exécutées pendant l’implémentation :

```powershell
.\backend\.venv\Scripts\python.exe -B -m unittest backend.tests.test_web_gateway -v
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend\tests -p "test_*.py" -v
npm run test:frontend
npm run build
git diff --check
.\lea.ps1 stop
.\lea.ps1 start
.\lea.ps1 status
```

Un essai Internet réel, distinct des simulations, a exécuté la requête
`Python 3.14 official release`. DuckDuckGo a retourné des résultats réels et le
gateway a lu trois pages publiques : deux sur `www.python.org` et une sur
`test.python.org`, toutes au statut `read`. L’essai complet a duré environ
4,5 secondes dans cet environnement.

Après le correctif historique, DuckDuckGo Lite a relu trois pages Python publiques
au statut `read`. Deux essais ont ensuite traversé l’endpoint réel
`POST /api/conversations/messages`, le modèle local et la persistance des
sources : l’un avec « Cherche sur Internet… » et `web_authorized=false`, l’autre
avec une question sans marqueur et `web_authorized=true`. Les deux réponses ont
été `completed`, avec trois sources HTTPS cliquables fournies par DuckDuckGo
Lite. Ces valeurs documentent l’ancien contrat, supprimé lors de la stabilisation
finale ; un test de non-régression vérifie désormais que ce champ est refusé. Les
deux conversations de diagnostic ont été supprimées immédiatement.

Le correctif de fiabilité a ensuite exécuté quatre collectes réelles, directement
par le gateway et sans conversation persistée :

| Catégorie | Fournisseur effectif | Résultat observé |
| --- | --- | --- |
| Technique — dernière version stable de Python | DuckDuckGo Lite | Deux lectures `python.org`, une `devguide.python.org`. |
| Sport — dernier match des Canadiens | DuckDuckGo Lite, termes condensés avant l'unique essai | `canadiensmtl.com` lu, TVA Sports en extrait, `nhl.com` lu. |
| Météo actuelle à Montréal | DuckDuckGo Lite | Trois lectures : deux `meteomedia.com`, une `meteo.gc.ca`. |
| Actualité montréalaise | DuckDuckGo Lite | TVA Nouvelles et 24 heures lus ; Radio-Canada conservé en extrait seulement. |

Ces essais démontrent la disponibilité observée le 23 octobre 2026, pas un SLA
des fournisseurs gratuits. Aucun HTML brut ni texte de requête n’a été persisté.

Sur une base temporaire isolée, le parcours API → gateway → modèle Général →
SQLite a ensuite exécuté exactement « Quel est le résultat du dernier match des
Canadiens de Montréal ? ». La réponse réelle donne mardi 20 octobre, San Jose et
`MTL 3 — 4 SJS`, puis précise que les Canadiens ont perdu : c'est le fait attendu
**Sharks de San José 4 – 3 Canadiens de Montréal**. La collecte contient trois
sources DuckDuckGo réelles. Le modèle conserve parfois l'ordre domicile–visiteur
malgré la consigne générique « vainqueur en premier » et peut omettre `[S1]` ; le
score reste non ambigu et le panneau de sources reste exact, sans réécriture ni
citation fabriquée. Un second parcours réel, sans accord Web, a produit zéro
source et Général a explicitement refusé de confirmer le dernier résultat avant
de proposer une recherche autorisée. Les bases temporaires ont été retirées à la
fermeture des tests ; la base personnelle n’a reçu aucune conversation d’essai.

Résultats finaux du correctif : 295 tests backend réussis, 0 échec ; 44 tests frontend
réussis, 0 échec ; build TypeScript/Vite réussi. `git diff --check` réussit
également (les avertissements de conversion LF/CRLF n’indiquent aucune erreur).
La suite backend finale a été exécutée Léa arrêtée : sous Windows, le watcher
Vite actif gardait ponctuellement un dossier de checkpoint de test ouvert et
empêchait son renommage avant toute assertion. Le test isolé puis la suite complète
passent après l'arrêt normal de Vite ; aucun code checkpoint n'a été modifié.
Un redémarrage réel sans génération ni run actif a chargé le nouveau backend :
modèle Général, FastAPI et Vite sont revenus `actif`, `/health` répond `ok`, la
migration active vaut 14, la préférence Web reste inchangée et les trois profils
annoncent `web_research`. Léa a été laissée active comme avant ce redémarrage.

La validation visuelle et fonctionnelle dans Microsoft Edge n’est pas déclarée
réussie ici ; elle appartient à l’utilisateur.

## E. Sécurité

- HTTP/HTTPS seulement, ports 80/443, aucune information d’identification dans
  l’URL, aucun proxy ambiant, cookie, référent ou redirection automatique. Le
  cookie jar est vidé avant chaque requête, y compris après un `Set-Cookie` reçu
  pendant une redirection ; un test de transport vérifie qu’il n’est jamais rejoué.
- Résolution de toutes les adresses et refus si l’une n’est pas globale ;
  connexion épinglée à l’IP approuvée avec Host/SNI d’origine.
- Revalidation de chaque redirection et limites sur requête, redirections,
  sources, temps, taille téléchargée et texte extrait.
- Rejet de localhost, réseaux privés, loopback, link-local, réservés, multicast
  et destinations de métadonnées cloud par la politique d’adresses.
- Permission émise par le backend et consommée avant le réseau ; ni le modèle ni
  une page ne peut l’émettre.
- Pages traitées comme données non fiables, sans rôle système ni exécution.
- Fournisseur limité à la question courante ; aucun souvenir, historique, prompt,
  chemin ou fichier local transmis.
- Deux tentatives de moteur au maximum, même User-Agent, aucun changement
  d’identité, aucun CAPTCHA résolu et aucun retour vers DuckDuckGo après son défi.

Limite normale : aucun filtre applicatif ne peut garantir l’exactitude éditoriale
d’une page publique. Léa cite la provenance, mais le contenu reste à évaluer.

## F. Performances

Il n’existe aucune boucle, connexion ou tâche Web au repos. Chaque requête crée
un client court puis le ferme. Les limites sont : deux fournisseurs essayés une
fois chacun au maximum, 500 caractères pour la requête condensée transmise au
fournisseur — et non pour le message utilisateur —,
30 secondes pour l’opération, trois sources, trois redirections, 512 Kio pour la
page de recherche, 768 Kio par page et 1 200 caractères extraits par source.
Le build frontend observé produit un bundle JavaScript d’environ 258 Kio avant
compression. Aucun moteur, modèle, service ou conteneur n’a été ajouté.

## G. Régressions vérifiées

Les suites couvrent conversations, historique, migrations SQLite, mémoire
explicite, profils, modèles, paramètres, ressources, voix, OpenHands, preuves,
checkpoints, Accept/Rollback et politiques terminal. Le test multi-profils Web
confirme qu’aucun `agent_run` n’est créé. La voix physique, un vrai run OpenHands
et une synthèse Web par chacun des trois modèles réels ne sont pas rejoués par
les tests automatiques de cette phase.
La base utilisateur n’a reçu que les migrations additives 13 et 14 au redémarrage ;
aucune conversation, mémoire, préférence existante, run ou checkpoint n’a été
supprimé ou réinitialisé.

## H. Validation manuelle proposée

1. Démarrer Léa, ouvrir Paramètres, activer « Autoriser les demandes Web
   explicites », puis valider.
2. En Général, cocher l’accord ponctuel et demander exactement « Quel est le
   résultat du dernier match des Canadiens de Montréal ? » ; vérifier le fait
   **Sharks de San José 4 – 3 Canadiens de Montréal, le 20 octobre** et que les
   sources portent le fournisseur réellement utilisé.
3. Poser la même question sportive, puis une météo actuelle, sans case ni mention
   Internet ; vérifier l’aveu de non-vérification, la proposition Web et l’absence
   de sources. Poser ensuite une question sportive datée de 1993 et vérifier une
   réponse locale ordinaire.
4. Demander « Peux-tu regarder ce qui se passe avec cette technologie ? », puis
   répondre « Oui, vas-y » ; vérifier que la question suivante reste locale.
5. Tester une recherche en Programmation et confirmer qu’aucun run OpenHands ni
   conteneur n’est créé, puis une recherche vétérinaire récente.
6. Annuler une recherche en cours et vérifier l’échec lisible sans réponse inventée.
7. Désactiver le Web dans Paramètres et vérifier qu’une nouvelle recherche est
   refusée avant le fournisseur.
8. Redémarrer Léa et vérifier la préférence, l’historique et les sources.

## I. Limitations restantes

- DuckDuckGo Lite est gratuit et sans compte, mais peut modifier son HTML,
  limiter le trafic ou présenter un défi anti-robot.
- Bing HTML est lui aussi externe, gratuit sans garantie, et peut modifier son
  balisage ou limiter la requête. S’il échoue après DuckDuckGo, Léa s’arrête avec
  une erreur Web claire et n’appelle pas le modèle.
- Les instances SearXNG publiques évaluées ont renvoyé des limitations ou défis ;
  elles ne sont pas utilisées comme repli trompeur.
- L’extraction légère n’est pas un moteur de lisibilité complet et peut conserver
  du texte secondaire ou manquer le contenu de sites complexes.
- À la clôture de 16.1 : aucun JavaScript, PDF, compte, formulaire, téléchargement,
  CAPTCHA, paiement, publication ou site authentifié.
- La comparaison approfondie et les PDF sont désormais réalisés en 16.2 et
  documentés dans `ETAPE_16_2_VALIDATION.md`. Le navigateur dynamique reste
  reporté à 16.3 et n’est pas commencé.
- Aucun accès Internet agentique pour OpenHands ou son terminal.
- La classification d’actualité reste volontairement ciblée et ne prétend pas
  comprendre toutes les formulations possibles. En revanche, tout cas reconnu
  est traité sans modèle : son honnêteté ne dépend plus de l’obéissance de Qwen.
- Le modèle Général peut omettre les repères `[S1]` dans son texte malgré la
  consigne ; seules les sources réellement collectées sont alors affichées dans
  le panneau dédié, sans ajout automatique d’une citation fictive.
- Pour un score, le modèle peut conserver l'ordre domicile–visiteur plutôt que le
  vainqueur en premier ; Léa ne réécrit pas son texte avec une heuristique sportive.

## J. État Git

Les modifications de travail existantes et celles de la phase 16.1 restent non
commitées. Aucun commit, push, prune ou nettoyage global n’a été effectué.
