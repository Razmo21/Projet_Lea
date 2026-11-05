# Étape 16.2 — Rapport de validation technique

Date : 25 octobre 2026
État : implémentation technique terminée ; campagne globale réalisée, correctifs
finaux en attente de revalidation utilisateur
Périmètre : phase 16.2 uniquement ; phase 16.3 non commencée

## A. Fonctionnalités réalisées

- Recherche approfondie déclenchée uniquement par une demande Web explicitement
  autorisée qui exprime une vérification, comparaison, rumeur ou fact-check.
- Jusqu’à trois recherches complémentaires sous le permis 16.1 déjà consommé,
  quatre sources par défaut et six au plafond injectable.
- Répartition des premiers résultats entre la recherche initiale, la recherche
  d’origine et la recherche de contexte ; aucune boucle ou planification modèle.
- Déduplication des URL, origines éditoriales probables et copies textuelles.
  Filtre lexical minimal contre les résultats manifestement hors sujet, sans
  score arbitraire de crédibilité fondé sur le domaine.
- Conclusion backend « impossible à vérifier » et aucun appel modèle lorsque
  moins de deux origines indépendantes ont réellement été lues.
- Contrat de synthèse distinguant affirmation confirmée, partiellement confirmée,
  contredite, trompeuse/hors contexte ou impossible à vérifier.
- Dates de publication, mise à jour, document et consultation conservées sous
  des libellés distincts ; aucune date d’événement inventée.
- Identifiants `[S1]` à `[S6]` attribués par le backend. Une référence modèle
  hors de cet ensemble est neutralisée avant la persistance.
- PDF textuels publics lus en mémoire avec limites de taille, pages, caractères,
  décompression et parsing ; aucun OCR, fichier durable ou contenu actif.
- Pages vidéo traitées opportunément : titre, description, dates et transcription
  JSON-LD publique seulement. Sans texte accessible, Léa demande une transcription
  ou une description et ne prétend pas avoir visionné la vidéo.
- Affichage frontend du type de preuve, du statut réel, des dates et des limites.

## B. Fichiers principaux créés ou modifiés

- `backend/app/web_gateway.py` : orchestration approfondie, pertinence,
  indépendance, PDF, vidéo, budgets et validation des citations.
- `backend/app/main.py` : verdict backend en cas de preuves insuffisantes et
  validation finale des références avant SQLite.
- `backend/app/migrations.py`, `backend/app/database.py` : migration 15 et
  persistance de six preuves typées au maximum.
- `backend/requirements.txt` : `pypdf==6.21.2`, bibliothèque Python pure.
- `src/lib/conversations.ts`, `src/App.tsx` : contrat et présentation des preuves.
- `backend/tests/test_web_research.py` : scénarios déterministes de 16.2.
- `tests/frontend/conversations.test.ts` : libellés de preuve.
- `AGENTS.md`, `README.md`, `TODO.md`, `CHANGELOG.md`, `backend/README.md`,
  `docs/DECISIONS.md` : état, décisions et limites de la phase.

## C. Architecture et autorisation

La phase ne crée aucun second gateway. `WebAuthorizationManager.consume()`
supprime toujours le permis avant le premier accès. `WebGateway.retrieve()`
choisit ensuite le parcours simple 16.1 ou le parcours approfondi 16.2 à partir
du texte autorisé. Les recherches complémentaires restent déterministes et
directement rattachées à l’affirmation initiale ; une page, un PDF ou le modèle
ne peut ni les autoriser ni étendre leur budget.

Le fournisseur conserve l’interface `SearchProvider`. Les lots de résultats
sont parcourus par rang, puis le lecteur SSRF existant revalide DNS, IP, port et
chaque redirection. Les sources sont numérotées seulement après lecture ou
qualification honnête comme `snippet_only`.

Une origine est une heuristique de déduplication, pas une note de fiabilité.
Les textes identiques sur plusieurs domaines ne comptent qu’une fois. Un filtre
lexical conservateur exige un recouvrement minimal avec les termes factuels de
la demande. Il vaut mieux échouer avec `web_no_results` que présenter quatre
sites indépendants mais hors sujet comme corroboration.

## D. PDF et vidéo

`SafeHttpFetcher` accepte le PDF uniquement dans le parcours documentaire, avec
une limite propre au type réellement annoncé. La signature `%PDF-` est vérifiée ;
un corps PDF annoncé comme HTML est refusé. `pypdf` reçoit au maximum 5 Mio et
ses propres plafonds sont ramenés à 8 Mio par flux décompressé, 32 Mio de travail
de décodage, 250 000 opérations de parsing, 40 pages et 12 000 caractères utiles.
Les PDF chiffrés, corrompus, sans texte ou uniquement image échouent sans OCR.

Le PDF reste en `BytesIO`. Une annulation est contrôlée avant et pendant le
transport puis juste après l’extraction ; le résultat tardif est jeté. Une page
individuelle déjà en cours d’analyse dans la bibliothèque Python n’est pas tuée
brutalement, mais son entrée, sa décompression, son nombre de pages et sa durée
globale restent bornés.

Pour les plateformes vidéo reconnues, le parseur statique accepte seulement les
métadonnées HTML et JSON-LD. `video_metadata` indique expressément l’absence de
transcription et l’absence de visionnement. `video_transcript` n’est attribué
que si un champ de transcription publique a réellement été extrait.

## E. Citations et conclusions

Chaque `WebSource` reçoit un `source_id` contrôlé. SQLite dérive de nouveau cet
identifiant de la position persistée, ce qui empêche le modèle de créer une
source. Après l’inférence, tout marqueur `[S…]` absent de l’opération est remplacé
par « référence Web non vérifiée retirée ». Le panneau affiche les sources
collectées par le backend, jamais une bibliographie libre du modèle.

Cette validation prouve la provenance et le statut technique d’une source. Elle
ne prétend pas établir automatiquement que chaque phrase du modèle est une
conséquence logique parfaite du document. Le verdict demandé reste proportionné ;
une synthèse sans verdict reconnu, ou un verdict positif sans identifiant de
source valide, est remplacée par « impossible à vérifier avec certitude ».

Le vrai essai complet a confirmé cette frontière : le texte extrait de la page
officielle Python contenait bien « Release date: Oct. 7, 2025 », mais le modèle
local a tout de même répondu « partiellement confirmée » et a confondu la date
d’un article secondaire avec la date de l’événement.

Le correctif de fiabilité du 25 octobre reste déterministe et borné. Lorsqu’une
affirmation contient une unique date civile complète, le gateway normalise les
formes françaises, anglaises et ISO sans confondre les numéros de version. Il
rapproche les passages pertinents, retire des appuis d’événement les dates de
publication, mise à jour et document déjà typées, puis conserve les identifiants
des pages réellement lues qui contiennent chaque date. Les horodatages ISO tels
que `2025-10-14T19:30:00Z` sont couverts.

Une confirmation exige deux références lues contenant la date demandée. Une
contradiction exige deux références lues contenant la même date alternative.
Un extrait `snippet_only` ne satisfait jamais ce contrôle. Si le verdict du
modèle ne cite pas les bons appuis, le backend le remplace par une conclusion
prudente et indique les passages datés disponibles au lieu d’inventer une
confirmation. Ce mécanisme n’accorde aucune crédibilité par nom de domaine et
ne contient aucune règle propre à Python.

## F. Tests automatisés

Les tests déterministes couvrent : trois recherches et leur plafond, permission
absente ou consommée, origines indépendantes, copies, contradiction, source
primaire lisible ou inaccessible, dates différentes, contenu ancien, hors-sujet,
injection distante, annulation, preuve insuffisante sans modèle, référence
inventée, source `snippet_only`, PDF valide/malformé/trop grand/sans texte/MIME
incohérent, limite de pages, vidéo inaccessible, métadonnées seules,
transcription publique, migration 14→15 et non-régression 16.1. Le correctif
ajoute la reproduction Python, les dates éditoriales ISO horodatées, deux appuis
concordants, deux appuis contradictoires, un conflit un-contre-un et le refus de
citations réelles mais non pertinentes pour le verdict daté.

Commandes exécutées pour la clôture technique :

```powershell
.\backend\.venv\Scripts\python.exe -B -m unittest backend.tests.test_web_gateway backend.tests.test_web_research -v
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -q
npm run test:frontend
npm run build
git diff --check
.\lea.ps1 start
.\lea.ps1 status
.\lea.ps1 stop
```

Résultats finaux : 321 tests backend réussis, 45 tests frontend réussis, build
TypeScript/Vite réussi et `git diff --check` réussi. L’unique avertissement est
la dépréciation déjà connue de `starlette.testclient` avec `httpx` ; aucune
dépendance n’a été remplacée pendant cette phase ciblée.

## G. Vérifications Internet réelles

Les quatre premiers essais ont utilisé directement le gateway, sans modèle et
sans base SQLite. Aucune conversation ni page brute n’a été persistée.

1. **Technologie et date** — « Python 3.14.0 publié le 7 octobre 2025 » : trois
   recherches logiques, plusieurs pages réellement lues dont `python.org`, avec
   dates déclarées conservées. DuckDuckGo a été intermittent et Bing a servi de
   repli sur certaines recherches.
2. **PDF public** — PDF de test W3C : lecture `application/pdf` réussie en RAM,
   texte « Dummy PDF file » extrait, type `pdf` et date interne conservée.
3. **Vidéo publique** — page YouTube publique : texte exploitable indisponible
   sous les limites statiques ; retour explicite demandant la transcription,
   sans prétendre voir ou écouter la vidéo.
4. **Affirmation populaire** — Grande Muraille visible depuis la Lune : Bing a
   retourné plusieurs domaines hors sujet. L’essai a révélé ce défaut ; après
   ajout du filtre de pertinence, la même demande termine honnêtement avec
   `web_no_results` au lieu de compter ces pages comme confirmations.
5. **Flux complet de Léa** — démarrage modèle/backend/frontend avec une base
   isolée, préférence Web active puis `POST /api/conversations/messages` avec
   accord ponctuel. La réponse a terminé en 25,74 s et SQLite a conservé quatre
   références backend (`python.org`, deux pages secondaires réellement lues et
   un extrait de moteur clairement marqué). Le modèle a cependant produit le
   verdict prudent mais factuellement discutable décrit en section E.
6. **Comparaison avant/après ciblée** — reproduction avant correction en 25,85 s :
   « partiellement confirmée », S1 déclarée à tort imprécise, et dates éditoriales
   des 12/14 octobre transformées en dates de sortie. Après correction, plusieurs
   collectes ont confirmé que Python.org et au moins une page secondaire lue
   contenaient explicitement le 7 octobre, tandis que le 14 octobre restait une
   date de page. Le dernier flux complet (25,46 s) a rejeté le verdict positif du
   modèle faute de deux citations correspondantes et a répondu « impossible à
   confirmer » sans publier les fausses dates. La base isolée est supprimée après
   les suites finales et Léa reste arrêtée.

Ces observations datent du 24–25 octobre 2026 et ne constituent aucun SLA des
fournisseurs gratuits.

## H. Sécurité et ressources

- Aucun accès Web sans la préférence active et l’accord du tour.
- Aucun cookie, proxy ambiant, compte, formulaire, JavaScript, téléchargement
  utilisateur, exécution distante, OCR ou navigateur.
- Même barrière SSRF et même épinglage DNS pour HTML, PDF et pages vidéo.
- Historique, mémoire, fichiers locaux et prompts absents des requêtes fournisseur.
- Quatre sources par défaut, six au maximum, trois recherches, 45 secondes et
  contexte approfondi limité à 4 000 caractères.
- Aucun processus, service, conteneur ou modèle supplémentaire au repos.
- `pypdf` est importé dans le backend existant et ne démarre aucun worker ;
  l’extraction PDF utilise un thread ponctuel borné puis libéré.

Les temps observés sont d’environ 7 secondes pour la collecte directe Python,
25 à 29 secondes pour ses flux complets avec inférence locale, et moins d’une
seconde pour le PDF W3C. La tentative sociale avec trois replis Bing a pris
environ 23 secondes. Ces valeurs dépendent du réseau et du modèle actif.

## I. Régressions et validation manuelle différée

Les suites complètes couvrent conversations, mémoire, préférences, profils,
voix, ressources, migrations, OpenHands, checkpoints, Accept/Rollback et toutes
les barrières 16.1. Aucun test manuel Edge n’est réalisé maintenant, conformément
à la décision de le regrouper après 16.3.

À la fin de l’étape 16, vérifier au minimum dans Edge :

1. Fact-check récent avec plusieurs sources et repères `[S…]` cohérents.
2. Affirmation fausse puis affirmation sortie de son contexte.
3. Contradiction entre une source originale et une analyse indépendante.
4. PDF public textuel, puis PDF image sans texte.
5. Lien vidéo avec description/transcription, puis plateforme inaccessible.
6. Même requête sans accord Web : zéro réseau et proposition d’autorisation.
7. Recherche en Général, Programmation et Vétérinaire sans run OpenHands.

## J. Limitations et état Git

- Les fournisseurs gratuits restent intermittents et peuvent modifier leur HTML.
- Le filtre de pertinence est lexical et conservateur : une preuve pertinente
  dans une autre langue ou avec un vocabulaire très différent peut être écartée.
- L’indépendance par origine et empreinte détecte les doublons évidents, pas
  toutes les reprises éditoriales d’une même dépêche.
- Le rapprochement renforcé porte uniquement sur une date civile complète unique.
  Les dates partielles, intervalles, heures, calendriers non grégoriens et
  formulations implicites restent à interpréter par le modèle.
- La présence lexicale d’une date dans un passage ne prouve pas sa sémantique :
  négation, citation d’une rumeur ou contexte complexe peuvent encore exiger une
  lecture humaine. Pour cette raison, le backend peut refuser un verdict mal cité,
  mais ne transforme jamais seul un comptage de dates en confirmation factuelle.
- Si une date d’événement est identique à la date éditoriale de la page, le filtre
  conservateur peut ne pas la compter comme appui. Cette possibilité de faux
  négatif est préférée à la confusion observée entre article et événement.
- Les PDF image exigeraient un OCR, volontairement absent. Les contenus actifs,
  formulaires et JavaScript restent interdits.
- Les vidéos ne sont ni téléchargées, ni décodées, ni comprises visuellement.
- La phase 16.3 et tout navigateur dynamique sont non commencés.

Toutes les modifications restent dans le worktree. Aucun commit ni push.
