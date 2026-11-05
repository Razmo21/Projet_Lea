Projet Léa
Léa est une assistante personnelle d'intelligence artificielle conçue pour fonctionner principalement en local, sur Windows. Elle réunit conversation, mémoire explicite, programmation assistée, voix et consultation contrôlée du Web dans une interface unique.
État du projet — novembre 2026 : les étapes 1 à 16 sont terminées. L'étape 17 (Markdown et refonte visuelle) est implémentée et validée manuellement ; son commit reste à effectuer. La prochaine étape est la transformation de Léa en application Windows pour finaliser la v1.0.

Léa est encore un projet personnel en développement, et non un installateur Windows prêt à être distribué. Les limites connues et les validations détaillées sont conservées dans docs/.
Sommaire
- Fonctionnalités
- Architecture
- Démarrage local
- Utilisation
- Données et configuration
- Sécurité et limites
- Tests
- Feuille de route
- Documentation
Fonctionnalités
Trois profils spécialisés
Profil	Modèle local actuel	Utilisation
Général	Qwen3 4B	Conversation, explications, rédaction et questions courantes. Raisonnement Low/High.
Vétérinaire	Qwen3.5 9B	Apprentissage vétérinaire et raisonnement clinique théorique. Raisonnement Low/High.
Programmation	Qwen2.5-Coder 7B	Tâches de développement exécutées par OpenHands sur un projet autorisé.


Le profil Programmation n'est pas un chat conventionnel : il sélectionne un dossier de travail, lance une tâche contrôlée et présente les résultats, modifications et possibilités de restauration. Il ne propose pas de sélecteur Low/High.

Un seul modèle d'inférence est chargé à la fois. Les profils et leurs modèles sont associés par configuration, afin de pouvoir remplacer les modèles sans reconstruire Léa.
Conversations et mémoire
- Conversations persistantes dans SQLite : création, recherche, ouverture, renommage et suppression.
- Les conversations Programmation figurent dans cette même liste. Leur ouverture exige le profil Programmation chargé ; leur renommage et leur suppression restent disponibles avec les autres profils.
- Modification d'un ancien message, nouvelle génération et reprise après certaines erreurs, avec protection contre les mises à jour concurrentes.
- Mémoire explicite : commandes telles que Retiens que… et Oublie que…. Les souvenirs ne sont pas extraits automatiquement des discussions ordinaires.
- Chat éphémère dans le profil Général : échanges conservés uniquement en mémoire vive, sans historique ni souvenirs persistants. La session disparaît à sa fermeture ou au rechargement.
Interface et Markdown
- Interface React repensée autour des conversations, avec barre latérale, accueil, recherche et zone de saisie ajustable.
- Thèmes clair et sombre, avec palette inspirée du logo de Léa.
- Rendu Markdown CommonMark/GFM : titres, listes, tableaux, citations, cases à cocher, liens et blocs de code.
- Copie fidèle des messages et copie indépendante des blocs de code.
- Affichage sécurisé : pas d'exécution de HTML actif, de liens dangereux ou de chargement automatique d'images distantes.
- Sources Web présentées dans un panneau repliable, distinct de la réponse du modèle.
- Diagramme facultatif de l'utilisation du CPU, de la RAM et de la VRAM.
- Alertes de ressources centrées dans le bandeau supérieur ; le diagramme reste en bas.
- Avertissements et erreurs présentés par une phrase courte, avec diagnostics techniques conservés en interne.
- Accueil aléatoire propre au profil : cinq phrases Programmation et cinq Vétérinaire, sans rotation automatique.
Le bouton + de la zone de saisie est réservé à une évolution future ; l'importation de fichiers n'est pas encore implémentée. Le rendu LaTeX et la coloration syntaxique ne font pas partie de la v1.0 actuelle.
Voix locale
- Dictée : enregistrement, transcription locale et insertion du texte dans le brouillon, qui reste modifiable avant l'envoi.
- Conversation vocale : enregistrement d'une question, transcription, réponse du modèle puis lecture audio.
- Reconnaissance vocale locale avec Whisper ; synthèse vocale locale avec Kyutai Pocket TTS (voix naturelle de Léa, Estelle) ou Piper/SIWIS selon la configuration.
La conversation vocale fonctionne tour par tour : elle ne réactive pas automatiquement le microphone après chaque réponse. Le Speech-to-Speech continu est reporté à une version ultérieure.
Web Gateway
L'accès Internet est désactivé par défaut et reste soumis à deux conditions :
1. L'option Web doit être activée dans les paramètres.
2. Chaque recherche doit être explicitement demandée ou confirmée pour la question concernée.
Léa ne recherche pas automatiquement des informations sur Internet lorsqu'une simple question est posée. Pour une donnée actuelle sans autorisation, elle peut proposer une recherche ; une confirmation comme Oui, vas-y n'autorise que la demande en attente.

Le Web Gateway prend en charge, sous limites techniques :
- Recherche publique avec DuckDuckGo Lite et repli vers Bing HTML.
- Lecture directe de pages HTTP(S) publiques et consultation de PDF textuels.
- Vérification à partir de plusieurs sources lorsque la demande l'exige.
- Lecture ponctuelle de certaines pages JavaScript avec Microsoft Edge et un profil temporaire isolé.
- Attribution des références [S1], [S2], etc. par le backend, et non par le modèle.
Le Web Gateway conversationnel est disponible pour Général et Vétérinaire. Les tâches du profil Programmation passent par OpenHands, sans accès Web via cet outil.
Programmation avec OpenHands
- Sélection d'un projet dans le répertoire de travail autorisé.
- Panneau Projet toujours visible au-dessus des messages ; consignes et réponses conservées en bulles dans l'historique, y compris pendant le run.
- Exécution locale via OpenHands et Docker Desktop.
- Checkpoints avant modifications, consultation des changements, Accepter ou Restaurer.
- Les décisions de checkpoint accompagnent la réponse de la tâche ; une erreur sans réponse finale reste explicitement signalée.
- Annulation, suivi des runs et diagnostics en cas d'échec.
Une tâche peut modifier correctement des fichiers sans satisfaire la politique automatique de validation. Dans ce cas, Léa annonce un run non validé plutôt qu'une réussite fictive ; la restauration reste disponible. Docker Desktop doit actuellement être démarré manuellement.
Architecture
Interface React / TypeScript / Vite
               │
               ▼
          FastAPI (Léa)
       ┌───────┼───────────┬───────────────┐
       ▼       ▼           ▼               ▼
     SQLite  llama.cpp   Web Gateway    OpenHands
               │                           │
         Modèles Qwen                    Docker

Voix locale : Whisper → modèle actif → Pocket TTS / Piper
Léa est l'application et l'orchestrateur ; le modèle n'est qu'un composant interchangeable. L'historique, les souvenirs, les autorisations, les projets et les checkpoints restent sous le contrôle de Léa, indépendamment des poids du modèle.
Composant	Technologie / rôle
Interface	React, TypeScript, Vite, react-markdown, remark-gfm
API et orchestration	Python, FastAPI
Persistance	SQLite
Inférence locale	llama.cpp et modèles GGUF
Programmation agentique	OpenHands SDK / Agent Server, Docker Desktop
Voix	Whisper, Kyutai Pocket TTS, Piper/SIWIS
Navigation Web dynamique et tests	Playwright avec Microsoft Edge installé localement


Démarrage local
Prérequis
Le projet est actuellement développé et testé sur Windows 11. Avant le démarrage, les dépendances du dépôt, les runtimes et les fichiers de modèles configurés doivent déjà être installés. Le packaging en application Windows n'est pas encore réalisé.

Pour les fonctionnalités de programmation, Docker Desktop doit être disponible. Pour les fonctions vocales, utiliser une fenêtre Microsoft Edge externe : le navigateur intégré de VS Code a déjà présenté un problème de décodage audio.
Démarrer, vérifier et arrêter Léa
Dans PowerShell, depuis la racine du dépôt :
.\lea.ps1 start
.\lea.ps1 status
.\lea.ps1 stop
Après le démarrage, ouvrir : http://127.0.0.1:5173.

Les commandes start et stop gèrent la pile locale que Léa a elle-même lancée : frontend, backend et moteur d'inférence. Elles ne doivent pas arrêter arbitrairement un processus tiers occupant un port.
Utiliser l'interface sans charger l'IA
npm run dev
Ouvrir ensuite http://127.0.0.1:5173. Les boutons Démarrer et Arrêter de l'interface permettent de piloter le cœur local.

Les commandes équivalentes sont :
.\lea.ps1 start-core
.\lea.ps1 status-core
.\lea.ps1 stop-core
La lecture et la modification des paramètres restent possibles avec Vite seul lorsque les dépendances locales nécessaires sont installées.
Utilisation
Écrire à Léa
- Entrée : envoyer un message ou lancer une tâche dans le profil Programmation.
- Maj + Entrée : insérer un retour à la ligne.
- Le champ de saisie s'agrandit jusqu'à quatre lignes, puis défile.
- Le bouton principal propose Conversation vocale à vide, Envoyer avec du texte et Arrêter la réponse pendant le traitement. En Programmation, il annule la tâche avec l'arrêt vérifié existant ; les changements restent à examiner ou à restaurer.
- L'arrêt local interrompt aussi la génération dans llama.cpp. Le moteur peut prendre quelques secondes pour terminer un calcul déjà engagé ; une réponse partielle n'est jamais publiée comme complète.
- Le sélecteur de profil est situé en haut de l'interface. Les réglages Low/High concernent uniquement les profils qui les prennent en charge.
Mémoriser ou oublier une information
Retiens que je préfère les réponses en français.
Oublie que je préfère les réponses en français.
L'ajout de souvenirs est volontaire et déterministe. Un fait mentionné dans une conversation ordinaire n'est pas automatiquement enregistré comme souvenir durable. L'oubli repose sur une correspondance normalisée précise et non sur une recherche sémantique.
Autoriser une recherche Internet
Cherche sur Internet les dernières informations concernant ce sujet.
Une recherche nécessite également l'activation du Web dans les paramètres. Pour une question actuelle posée sans autorisation, attendre la proposition de Léa et confirmer si la recherche est souhaitée.
Lancer une tâche de programmation
1. Démarrer Docker Desktop et rendre le moteur de programmation disponible.
2. Choisir Programmation, puis un projet autorisé dans le workspace.
3. Décrire la tâche dans le champ de saisie et lancer le run.
4. Vérifier les fichiers modifiés et les tests réellement exécutés.
5. Accepter les modifications validées ou Restaurer le checkpoint.
Ne lancer des projets contenant du code exécutable que si leur contenu est digne de confiance. Un succès technique d'OpenHands n'implique pas automatiquement la validation fonctionnelle de la tâche.
Données et configuration
Emplacement	Rôle
config/models.json	Registre central des modèles, profils, capacités et paramètres d'exécution.
data/lea.sqlite3	Conversations, messages, mémoire, préférences et métadonnées persistantes.
models/	Poids des modèles locaux, non destinés à Git.
runtime/	Runtimes et fichiers d'exécution locaux.
backend/app/	API, orchestration, inférence, contrôles et logique métier.
src/	Interface et composants React/TypeScript.
src/styles/index.css	Styles et thèmes principaux.
public/lea-logo.png	Logo et identité visuelle de Léa.
.lea/	État technique temporaire local, ignoré par Git.
docs/	Décisions, comptes rendus et validations détaillées.


Chemins actuels du poste de développement : dépôt L:\Projet_Lea, workspace de programmation L:\IA_WORKSPACE. Ces chemins décrivent l'environnement actuel et ne doivent pas être considérés comme des chemins universels.

Le futur passage à un SSD interne plus rapide devra vérifier les chemins, les dépendances et la configuration du workspace. Les souvenirs et préférences utilisateur pourront être réinitialisés pendant cette migration ; le code source, .git, le registre technique et les modèles nécessaires devront être préservés.

Pour remplacer un modèle compatible, arrêter d'abord Léa, sauvegarder le registre, mettre à jour config/models.json, contrôler le fichier GGUF (taille et SHA-256), puis valider la configuration et tester le profil concerné. Les détails de cette procédure sont consignés dans les décisions techniques du projet.
Sécurité et limites
- Local par défaut. Les conversations et souvenirs sont gérés sur la machine ; aucun compte ou modèle cloud de secours n'est nécessaire à l'inférence ordinaire.
- Web sous consentement. Les recherches publiques peuvent transmettre la requête aux fournisseurs et laisser des traces sur les sites consultés. Le chat éphémère n'offre pas d'anonymat réseau.
- Sources contrôlées. Le backend valide la provenance des références Web, mais ces contrôles ne garantissent pas la vérité de toute information extraite d'une page.
- Navigation bornée. Les protections contre les destinations locales et les actions sensibles réduisent les risques ; elles ne constituent pas un bac à sable réseau formel au niveau du système.
- OpenHands confiné. Les projets sont limités à un workspace autorisé et protégés par des checkpoints, sans garantie absolue d'isolation du code exécuté.
- Fiabilité des modèles. Les Qwen locaux peuvent se tromper, produire un français imparfait ou ne pas terminer une synthèse. Un résultat insuffisamment validé doit être présenté comme tel.
- Fonctionnalités reportées. Pas de Vision, de génération d'images, de mémoire automatique avancée, de véritable conversation Speech-to-Speech continue ni de logiciel Windows installé à ce stade.
Les contrats de fiabilité et les limitations par étape sont documentés dans le dépôt. Les évolutions futures ne doivent pas affaiblir les permissions et les protections déjà validées.
Tests
Depuis la racine du projet :
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -p 'test_*.py'
npm run test:frontend
npm run build
git diff --check
Les tests automatisés incluent des scénarios avec services simulés. Les fonctionnalités sensibles doivent également être testées manuellement avec les vrais modèles et périphériques : Markdown, persistance, Web, microphone, synthèse vocale et OpenHands avec restauration.

La validation de l'étape 17 a couvert ces usages dans Edge. Un run OpenHands a bien créé le fichier demandé et permis sa restauration, mais n'a pas obtenu le statut automatique validated faute de vérification reconnue après modification. Cette limite reste documentée ; elle n'est pas présentée comme une réussite de validation agentique.

Les scripts de test pouvant modifier une base ou des préférences doivent être exécutés uniquement avec leurs environnements isolés, selon la procédure du rapport correspondant.
Feuille de route
Périmètre	État
Étapes 1 à 14 — Fondations, conversations, mémoire explicite, profils, programmation et voix locale	Terminées
Étape 15 — Profil Vétérinaire et contrats de fiabilité	Implémentée ; limites scientifiques documentées
Étape 16 — Web Gateway (recherche, vérification, PDF, navigation dynamique)	Terminée, validée et commitée
Étape 17 — Markdown et refonte visuelle	Implémentée et validée manuellement ; commit à effectuer
Prochaine étape : application Windows	Non commencée
Léa v1.0 — Packaging, tests essentiels et livraison locale	En préparation
Léa v2.0 — Nouveaux modèles et capacités avancées sur le futur PC	Projet ultérieur


La v1.0 vise une application Windows utilisable simplement, avec les fonctions déjà présentes. La v2.0 pourra réévaluer les modèles, la Vision, la génération d'images, la mémoire automatique, la programmation avancée et la conversation vocale continue, en fonction du nouveau matériel et des tests réels.
Documentation
- [`AGENTS.md`](AGENTS.md) — Règles de travail et conventions pour les agents de développement.
- [`TODO.md`](TODO.md) — Suivi de la feuille de route et des travaux restants.
- [`CHANGELOG.md`](CHANGELOG.md) — Historique des changements.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — Décisions techniques et arbitrages.
- [`docs/ETAPE_13_VALIDATION.md`](docs/ETAPE_13_VALIDATION.md) — Programmation avancée.
- [`docs/ETAPE_14_VALIDATION.md`](docs/ETAPE_14_VALIDATION.md) — Voix et microphone.
- [`docs/ETAPE_15_VALIDATION.md`](docs/ETAPE_15_VALIDATION.md) — Profil Vétérinaire.
- [`docs/ETAPE_16_1_VALIDATION.md`](docs/ETAPE_16_1_VALIDATION.md), [`16.2`](docs/ETAPE_16_2_VALIDATION.md) et [`16.3`](docs/ETAPE_16_3_VALIDATION.md) — Web Gateway.
- [`docs/ETAPE_17_VALIDATION.md`](docs/ETAPE_17_VALIDATION.md) — Markdown, interface et campagne de validation.
Principe de développement : avancer par étapes limitées, garder une architecture modulaire et ne déclarer une fonctionnalité validée qu'après des vérifications réelles. Codex intervient sur le code ; l'utilisateur conserve la décision de validation et la responsabilité des commits.
