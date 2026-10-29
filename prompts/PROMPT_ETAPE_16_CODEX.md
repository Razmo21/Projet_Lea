# PROJET LÉA — ÉTAPE 16 : INTÉGRATION COMPLÈTE DU WEB
## PROMPT MAÎTRE CODEX — TROIS PHASES DE DÉVELOPPEMENT

Tu travailles sur le projet Léa, dont tu connais déjà l'architecture, l'historique, les conventions et les étapes précédentes.

Nous entamons **l'étape 16 : intégration du Web**.

Cette étape est importante : Léa doit acquérir la capacité de consulter des informations sur Internet, de lire des sources publiques, de vérifier des affirmations et de naviguer sur certains sites.

Cependant, elle doit conserver son identité fondamentale : un assistant IA local, léger, fiable, contrôlé par son utilisateur et indépendant des modèles employés.

**Lis intégralement ce cahier des charges avant de commencer. Il contient trois phases majeures, mais tu n'es autorisé à implémenter que la phase 16.1 pour le moment.**

Les phases 16.2 et 16.3 sont incluses dès maintenant afin de définir une architecture cohérente, extensible et durable.

---

# 0. RÈGLES ABSOLUES DE CETTE ÉTAPE

## 0.1. Contrôle exclusif de l'utilisateur sur Internet

**Léa ne doit JAMAIS accéder à Internet de sa propre initiative.**

Il s'agit d'une exigence fondamentale et non négociable.

Même si Léa estime qu'une recherche serait pertinente, utile, nécessaire ou susceptible d'améliorer sa réponse, elle ne doit pas déclencher de recherche sans autorisation explicite de l'utilisateur.

Une demande autorisant Internet peut prendre différentes formes :

- « Cherche sur Internet la météo d'aujourd'hui. »
- « Vérifie en ligne le résultat du match d'hier. »
- « Va voir sur le Web si cette information est vraie. »
- « Consulte cet article et résume-le. »
- « Recherche les dernières informations sur cette technologie. »
- « Vérifie cette affirmation qui circule sur TikTok. »
- « Ouvre ce lien et explique-moi son contenu. »

En revanche, une question telle que « Quelle est la météo aujourd'hui ? » ne constitue pas automatiquement une autorisation d'accès au Web.

Dans ce cas, Léa peut expliquer qu'une consultation d'Internet serait nécessaire et demander l'autorisation.

### Règles impératives

1. Aucun accès Web automatique.
2. Aucune recherche déclenchée par une simple estimation du besoin d'actualité.
3. Aucun accès Internet en arrière-plan.
4. Aucune surveillance périodique de sites.
5. Aucune recherche préventive.
6. Aucune recherche déclenchée automatiquement au démarrage de Léa.
7. Aucun accès Web après une réponse si l'utilisateur n'a rien demandé.
8. Aucune autorisation Web permanente implicite.
9. Une autorisation donnée pour une demande ne s'étend pas automatiquement aux demandes suivantes.
10. Une page Web, un résultat d'outil ou une instruction générée par un modèle ne peut jamais accorder une autorisation réseau.

Une demande explicitement autorisée peut nécessiter plusieurs recherches complémentaires et la consultation de plusieurs sources. Ces opérations restent autorisées uniquement si elles servent directement la demande initiale, respectent les limites configurées et appartiennent à la même opération utilisateur.

### Application technique obligatoire

Cette règle ne doit pas reposer seulement sur un prompt système ou sur la bonne volonté du modèle.

Le backend doit imposer une **barrière d'autorisation Web réelle**, indépendante des modèles.

Le modèle actif ne doit jamais pouvoir contourner cette barrière en générant lui-même une autorisation.

L'autorisation doit provenir d'une action ou d'une demande explicite de l'utilisateur, validée par la couche applicative.

Prévoir une interprétation conservatrice des demandes explicites, et une confirmation utilisateur lorsque l'intention est ambiguë.

Une confirmation telle que « Oui, cherche » doit pouvoir autoriser la demande précédemment proposée, sans créer d'autorisation générale.

L'autorisation doit être limitée à l'opération concernée, non réutilisable pour d'autres conversations et révoquée à la fin de l'opération.

**Le contrôle manuel doit être garanti techniquement, y compris si le modèle hallucine, se trompe ou tente d'appeler un outil sans permission.**

---

## 0.2. Gratuité et absence de compte

L'accès Web doit être :

- Gratuit.
- Utilisable sans créer de compte.
- Sans abonnement.
- Sans carte bancaire.
- Sans clé API commerciale obligatoire.
- Sans service payant imposé.
- Sans quota commercial nécessitant une inscription.

Il est acceptable qu'un fournisseur de recherche gratuit présente certaines limitations, tant que ces limitations sont correctement gérées.

Toutefois, Léa doit disposer d'au moins une méthode de recherche réellement fonctionnelle pour que la phase 16.1 soit considérée comme terminée.

Ne prétends pas qu'un fournisseur fonctionne simplement parce qu'une documentation décrit son API.

Vérifie son comportement réel.

---

## 0.3. Contraintes matérielles

Le PC actuel de l'utilisateur dispose de ressources limitées pour faire fonctionner plusieurs modèles IA locaux.

Par conséquent :

- Évite les services lourds.
- Évite les conteneurs supplémentaires inutiles.
- Évite les dépendances volumineuses sans justification.
- N'ajoute pas de modèle IA supplémentaire pour gérer le Web.
- Ne charge jamais simultanément plusieurs modèles pour effectuer une recherche.
- Ne fais pas tourner un navigateur automatisé en permanence.
- Ne lance pas de service consommant beaucoup de RAM au démarrage.
- Privilégie les traitements HTTP légers et asynchrones.
- Limite le parallélisme, les pages ouvertes, la taille des réponses et les délais d'attente.
- Libère les ressources dès qu'une opération est terminée.

**L'ajout du Web ne doit pas dégrader sensiblement le fonctionnement local de Léa lorsque celui-ci n'est pas utilisé.**

Les phases 16.1 et 16.2 doivent fonctionner sans navigateur automatisé lourd.

La phase 16.3 devra charger son moteur de navigation uniquement à la demande.

---

## 0.4. Préservation du projet existant

Les étapes précédentes sont considérées comme terminées et stabilisées.

Tu dois préserver :

- Le frontend existant.
- Le backend FastAPI.
- Les profils Général, Programmation et Vétérinaire.
- Le registre des modèles.
- La sélection et le remplacement des modèles.
- Les modes de raisonnement Low et High.
- La mémoire.
- L'historique des conversations.
- La transcription vocale Whisper.
- La synthèse vocale Pocket TTS et Piper.
- Les fonctions de démarrage et d'arrêt.
- L'intégration OpenHands.
- Les restrictions du profil Programmation.
- Les paramètres existants.
- La base de données et ses informations.
- Les mécanismes de sécurité.
- L'architecture modulaire et indépendante des modèles.

Ne réalise aucune refonte générale du frontend ou du backend.

Ne modifie pas le comportement des fonctions précédentes sans nécessité démontrée.

Les contrats des profils Général, Programmation, Vétérinaire et le contrat global de fiabilité ont été récemment optimisés.

**Ne réécris pas ces contrats.**

Seules des adaptations ponctuelles strictement nécessaires pour refléter la nouvelle disponibilité conditionnelle du Web sont autorisées.

Ne réintroduis aucune ancienne version des contrats.

---

## 0.5. Absence d'actions sensibles sur Internet

**Léa doit uniquement rechercher, consulter, lire, analyser et expliquer des informations publiques.**

Il est strictement interdit d'implémenter :

- Une connexion automatisée à un compte.
- La saisie ou la conservation d'identifiants.
- Une authentification sur un site.
- La gestion de comptes utilisateur.
- L'envoi de formulaires à des services externes.
- La publication de commentaires ou de contenus.
- L'envoi de messages.
- Les achats.
- Les commandes.
- Les paiements.
- Les réservations.
- Les opérations financières.
- Les téléchargements arbitraires sur le PC.
- L'installation de logiciels obtenus sur Internet.
- L'exécution de code fourni par un site Web.
- Les modifications de données sur des services externes.
- La navigation autonome sans demande utilisateur.

### Téléchargements

Si l'utilisateur demande de trouver un fichier, un document, un logiciel ou un téléchargement :

**Léa doit lui fournir le lien officiel ou pertinent, et non télécharger le fichier à sa place.**

La lecture temporaire en mémoire d'un document public, comme un PDF, reste permise si elle est nécessaire pour répondre à une demande explicite.

Cette lecture ne doit pas être confondue avec un téléchargement utilisateur permanent.

Les éventuels fichiers temporaires strictement nécessaires au traitement doivent être limités, isolés et nettoyés.

### Évolution future

L'architecture peut prévoir des points d'extension pour de futures capacités agentiques.

Cependant, aucune capacité interdite ci-dessus ne doit être développée, activée ou exposée pendant l'étape 16.

L'utilisateur décidera lui-même d'éventuelles évolutions après une amélioration de son matériel et des modèles disponibles.

---

# 1. ARCHITECTURE GLOBALE DU WEB

Créer un composant commun, indépendant des modèles, que nous appellerons provisoirement :

**Léa Web Gateway**

Son rôle sera de centraliser l'ensemble des communications Web autorisées.

Architecture conceptuelle :

Utilisateur
→ Frontend Léa
→ Backend FastAPI
→ Contrôle d'autorisation Web
→ Léa Web Gateway
→ Fournisseur de recherche ou lecteur de pages
→ Résultats normalisés et sources
→ Modèle actif
→ Réponse à l'utilisateur.

Cette représentation est conceptuelle. Adapte son implantation à l'architecture réelle du dépôt.

## 1.1. Indépendance des modèles

Le Web Gateway ne doit dépendre ni de Qwen3-4B, ni de Qwen2.5-Coder, ni de Qwen3.5-9B, ni d'un modèle futur.

Un remplacement de modèle doit conserver la capacité Web sans refonte du système.

Les appels aux outils, leur orchestration et leurs autorisations doivent être gérés par le backend et non par des conventions propres à un seul modèle.

Étudie le mécanisme existant de génération et d'orchestration avant de choisir la méthode d'intégration.

Si certains modèles ne disposent pas d'un appel d'outils natif suffisamment fiable, une orchestration backend contrôlée peut être préférable.

Il n'est pas nécessaire que le modèle décide lui-même du lancement d'une recherche.

L'utilisateur doit conserver cette décision.

---

## 1.2. Fournisseur de recherche interchangeable

Créer une abstraction permettant de remplacer le fournisseur de recherche sans modifier :

- Le frontend.
- Les profils.
- Les contrats.
- Le mécanisme de citations.
- La lecture des pages.
- L'orchestration générale.

Étudier en priorité :

**SearXNG et les solutions publiques gratuites ne nécessitant aucun compte.**

Attention : de nombreuses instances publiques SearXNG désactivent la sortie JSON, appliquent des limitations ou sont indisponibles.

Il faut détecter ces cas.

Évaluer également d'autres méthodes gratuites et raisonnablement maintenables, notamment l'exploitation autorisée de pages publiques de résultats de recherche ou d'interfaces documentées ne nécessitant pas de compte.

Ne contourne pas les CAPTCHA, protections anti-bot, conditions d'accès ou restrictions explicites d'un service.

Ne suppose pas qu'une méthode non officielle sera durablement stable.

### Résilience

Prévoir, si cela est justifié :

- Un fournisseur principal.
- Un mécanisme de repli.
- Des erreurs propres et explicites.
- Une configuration remplaçable.
- Des délais d'attente.
- Une détection des réponses invalides.
- Une gestion des indisponibilités.

Ne développe pas un système complexe de dizaines de fournisseurs.

L'objectif est une solution gratuite, simple, fonctionnelle et maintenable.

Un SearXNG auto-hébergé ne doit pas devenir une dépendance obligatoire si cela impose de faire tourner Docker ou un service lourd en permanence.

---

## 1.3. Schéma commun des résultats

Normaliser les résultats Web avec les informations réellement disponibles.

Prévoir notamment :

- Titre.
- URL.
- Domaine.
- Extrait.
- Fournisseur ou origine.
- Date de publication, si réellement disponible.
- Date de consultation.
- Contenu consulté, lorsque disponible.
- État de récupération.
- Identifiant de source.
- Éventuelles limites ou erreurs.

Ne fabrique jamais de date de publication.

Distingue la date d'un événement, la date de publication d'un article et la date de consultation.

Les sources doivent pouvoir être rattachées aux passages utilisés dans les réponses.

---

## 1.4. Autorisations et confidentialité

Le Web Gateway doit refuser toute requête ne disposant pas d'une autorisation utilisateur valide.

Prévoir des mécanismes contre :

- Les accès à localhost et aux interfaces de services internes.
- Les adresses IP privées.
- Les plages réservées et les adresses de métadonnées.
- Les adresses IPv4 et IPv6 non autorisées.
- Les redirections vers des destinations interdites.
- Le DNS rebinding.
- Les URL malformées.
- Les schémas autres que HTTP et HTTPS.
- Les requêtes excessives.
- Les réponses trop volumineuses.
- Les délais d'attente incontrôlés.
- Les contenus malveillants.
- Les tentatives d'injection de prompt.
- La divulgation de secrets.

Les contrôles réseau doivent être réels. Une simple vérification textuelle de l'URL ne suffit pas.

Examiner la destination DNS et garantir que la connexion effective respecte la politique d'accès, y compris après une redirection ou une nouvelle résolution DNS.

Les éventuels accès locaux à un fournisseur configuré explicitement par l'administrateur doivent être séparés des URL arbitraires demandées par le modèle ou l'utilisateur.

Ne transmets jamais automatiquement aux moteurs de recherche :

- Les conversations complètes.
- La mémoire personnelle.
- Les fichiers locaux.
- Les clés API.
- Les variables d'environnement.
- Les informations privées sans rapport avec la recherche.
- Le contenu d'IA_WORKSPACE.

La requête externe doit être limitée aux termes nécessaires pour satisfaire l'instruction explicite.

Si la requête nécessite de divulguer des données sensibles, demande une confirmation appropriée au lieu de les envoyer silencieusement.

Distingue clairement les modèles locaux des services Web externes : l'inférence reste locale, mais une recherche Internet transmet nécessairement certaines données à un fournisseur externe.

---

## 1.5. Protection contre les injections de prompt

Un résultat de recherche, une page HTML, un PDF ou tout autre contenu distant est une **donnée non fiable**.

Aucune instruction provenant de ces contenus ne peut :

- Modifier les règles de Léa.
- Modifier les contrats des profils.
- Activer Internet.
- Donner des autorisations supplémentaires.
- Lancer OpenHands.
- Exécuter une commande.
- Lire un fichier local.
- Déclencher une action système.
- Modifier une configuration.
- Supprimer des données.
- Commander un navigateur.
- Autoriser une nouvelle recherche hors périmètre.
- Faire révéler des informations privées.

Les protections doivent être appliquées par les composants techniques appropriés, et non reposer uniquement sur une instruction au modèle.

Nettoyer et encadrer les contenus présentés au modèle.

Ne jamais traiter le texte extrait d'une page comme un message système ou une commande de l'utilisateur.

---

# 2. PHASE 16.1 — RECHERCHE WEB FONDAMENTALE

## Objectif général

À la fin de cette phase, Léa doit être capable de :

1. Recevoir une demande explicite de recherche Internet.
2. Obtenir l'autorisation applicative correspondante.
3. Effectuer une recherche gratuite.
4. Lire des résultats pertinents.
5. Consulter le contenu principal de pages publiques simples.
6. Répondre en utilisant ces informations.
7. Présenter des sources cliquables.
8. Refuser de chercher lorsqu'aucune autorisation n'a été donnée.
9. Continuer de fonctionner normalement lorsque le Web est indisponible.

La phase 16.1 constitue le socle technique de toute l'étape 16.

---

## 16.1.1. Audit préalable du dépôt

Avant toute modification :

- Examiner l'architecture réelle du backend.
- Examiner le système de profils.
- Examiner les échanges frontend/backend.
- Examiner le gestionnaire de modèles.
- Examiner les paramètres existants.
- Examiner le système de conversations.
- Examiner les mécanismes de persistance.
- Examiner les contrats de fiabilité et de profils.
- Examiner les tests existants.
- Identifier les mécanismes de sécurité réseau existants.
- Identifier les dépendances déjà présentes.

Présente brièvement ton diagnostic architectural avant de réaliser des modifications importantes.

Réutilise autant que possible les composants existants.

Ne crée pas une deuxième architecture parallèle si une extension propre de l'architecture actuelle suffit.

---

## 16.1.2. Création du Web Gateway

Implémenter un service Web modulaire au niveau du backend.

Ce service doit prendre en charge :

- Les demandes de recherche autorisées.
- Les demandes d'ouverture d'URL autorisées.
- La validation des destinations.
- La communication avec les fournisseurs.
- La normalisation des résultats.
- L'extraction de contenu.
- La gestion des erreurs.
- Les limites de ressources.
- La traçabilité des sources.
- L'annulation d'une opération.

Le service doit être partagé entre les profils.

Ne crée pas trois implémentations Web distinctes.

---

## 16.1.3. Recherche gratuite

Implémenter un premier fournisseur gratuit réellement fonctionnel.

Explorer SearXNG et les solutions de repli raisonnables.

Documenter clairement :

- Le choix du fournisseur.
- Les limitations connues.
- Les conditions de fonctionnement.
- Les éventuelles dépendances.
- Le mécanisme de remplacement.
- Les erreurs possibles.

Lorsqu'une recherche échoue :

- Ne fabrique pas de résultats.
- N'annonce pas qu'Internet a été consulté avec succès.
- N'utilise pas des résultats fictifs.
- Indique clairement l'indisponibilité.
- Permets une nouvelle tentative sur demande.

Une recherche doit retourner de véritables résultats lorsqu'un fournisseur est disponible.

---

## 16.1.4. Lecture de pages publiques

Implémenter la consultation de pages HTML publiques.

Privilégier une extraction légère du contenu principal.

Étudier une bibliothèque comme Trafilatura si elle s'intègre correctement aux contraintes du projet.

Extraire, lorsque possible :

- Titre.
- Texte principal.
- URL.
- Métadonnées pertinentes.
- Date publiée réellement identifiable.

Éviter le texte inutile des menus, publicités et pieds de page.

Prévoir des limites de taille et de temps.

Ne pas interpréter les instructions intégrées aux pages comme des commandes.

Ne pas charger de navigateur complet pour les pages HTML simples.

---

## 16.1.5. Contrôle manuel des recherches

Intégrer la barrière d'autorisation au fonctionnement conversationnel.

### Cas A — Autorisation explicite

Utilisateur :
« Recherche sur Internet le résultat du dernier match des Canadiens. »

Résultat attendu :
Léa effectue une recherche et fournit les résultats disponibles, en identifiant la date du match et les sources.

### Cas B — Aucune autorisation

Utilisateur :
« Quel est le résultat du dernier match des Canadiens ? »

Résultat attendu :
Léa n'effectue aucune requête réseau.

Elle peut répondre avec une information dont elle connaît clairement la date, ou expliquer qu'une recherche serait nécessaire et demander la permission.

Elle ne doit jamais inventer un score actuel.

### Cas C — Autorisation ambiguë

Utilisateur :
« Tu peux regarder ce qui se passe avec cette technologie ? »

Résultat attendu :
Si l'intention d'utiliser Internet n'est pas suffisamment claire, Léa demande une confirmation concise.

### Cas D — Confirmation

Léa :
« Veux-tu que je recherche cette information sur Internet ? »

Utilisateur :
« Oui, vas-y. »

Résultat attendu :
L'autorisation concerne uniquement la demande en attente, et non toutes les recherches futures.

### Cas E — Demande suivante

Après une recherche autorisée, l'utilisateur pose une nouvelle question sans demander Internet.

Résultat attendu :
Aucun nouvel accès Web.

### Cas F — Tentative de contournement

Le modèle tente d'appeler le Web Gateway malgré l'absence d'autorisation.

Résultat attendu :
Le backend refuse réellement l'opération, sans requête externe.

Ces cas doivent être couverts par des tests.

Une simple consigne au modèle n'est pas une validation acceptable.

---

## 16.1.6. Intégration aux profils

Le Web doit être disponible dans :

- Général.
- Programmation.
- Vétérinaire.

Toujours sous autorisation explicite de l'utilisateur.

### Général

Usages principaux :

- Météo actuelle.
- Résultats sportifs.
- Actualités.
- Technologies.
- Informations récentes.
- Questions nécessitant des sources externes.

### Programmation

Usages principaux :

- Documentation technique officielle.
- Versions récentes de bibliothèques.
- Compatibilité logicielle.
- Notes de publication.
- Problèmes techniques documentés.

**Important : l'accès Web conversationnel du profil Programmation ne doit pas donner un accès Internet libre au terminal OpenHands.**

Les restrictions agentiques déjà en place restent inchangées.

### Vétérinaire

Usages principaux :

- Publications scientifiques.
- Recommandations professionnelles.
- Consensus vétérinaires.
- Informations médicales nécessitant une référence actuelle.

Le modèle doit distinguer une recommandation documentée, une étude préliminaire et une interprétation.

Ne jamais présenter une source non consultée comme vérifiée.

---

## 16.1.7. Intégration au frontend

Ajouter les éléments nécessaires sans refondre l'interface.

Prévoir :

- Un indicateur discret lorsqu'une recherche Web est en cours.
- Un affichage clair lorsque le Web a réellement été utilisé.
- Des références cliquables.
- Des messages d'erreur compréhensibles.
- Une possibilité d'annuler une recherche.
- Un réglage général permettant de désactiver complètement l'accès Web.

L'accès Web doit rester manuel même lorsque le réglage général l'autorise.

Le réglage « Web autorisé » signifie uniquement que Léa peut exécuter une recherche **sur demande explicite**.

Il ne doit jamais signifier « recherche automatique ».

Conserver la cohérence visuelle actuelle.

Ne réalise pas la refonte graphique prévue dans une autre étape.

---

## 16.1.8. Historique, mémoire et voix

Les réponses utilisant Internet doivent pouvoir être conservées dans l'historique avec leurs sources.

Ne transforme pas automatiquement des informations trouvées en souvenirs personnels.

Ne stocke pas inutilement de gros contenus HTML ou des copies intégrales de pages dans la base de données.

Préserver les conversations historiques existantes et leur compatibilité.

Le fonctionnement vocal doit continuer normalement.

Une demande explicite prononcée à voix haute peut autoriser une recherche comme une demande écrite, à condition que le backend applique les mêmes règles d'autorisation.

Aucune recherche ne doit être déclenchée à cause d'une reconnaissance vocale ambiguë sans confirmation appropriée.

---

## 16.1.9. Tests obligatoires

Créer des tests déterministes utilisant des fournisseurs simulés pour éviter de rendre la suite de tests dépendante d'Internet.

Tester notamment :

- Recherche explicitement autorisée.
- Recherche non autorisée.
- Autorisation expirée.
- Autorisation réutilisée.
- Confirmation d'une demande en attente.
- Absence de transmission des souvenirs privés.
- Fournisseur indisponible.
- Timeout.
- Résultat vide.
- Réponse JSON invalide.
- URL invalide.
- Redirection dangereuse.
- Adresse locale interdite.
- DNS et destination réseau interdits.
- HTML malveillant.
- Injection de prompt.
- Nettoyage des ressources.
- Annulation.
- Historique et citations.
- Préservation des profils.
- Fonctionnement hors ligne.

Effectuer également une vérification réelle du fournisseur choisi, lorsque l'environnement et les permissions le permettent.

Ne confonds pas les tests simulés avec une preuve que le fournisseur public fonctionne actuellement.

Si une recherche réelle ne peut pas être vérifiée, signale précisément ce point.

---

## CRITÈRES DE VALIDATION DE LA PHASE 16.1

La phase est terminée uniquement si :

1. Léa peut effectuer une véritable recherche Internet sur demande.
2. Le contrôle manuel est imposé par le backend.
3. Aucun accès Web ne se produit sans autorisation.
4. Les sources affichées correspondent aux résultats réels.
5. Les trois profils sont compatibles.
6. Le fonctionnement hors ligne est préservé.
7. Les protections réseau essentielles sont actives.
8. Les tests existants ne régressent pas.
9. La charge supplémentaire au repos est faible.
10. L'utilisateur peut tester les fonctions depuis l'interface.

### Exemples de validation manuelle

- « Cherche sur Internet la météo actuelle à Montréal. »
- « Recherche le résultat du dernier match des Canadiens de Montréal. »
- « Consulte les dernières informations sur Python. »
- « Cherche une recommandation vétérinaire récente sur l'insuffisance rénale féline. »
- « Quelle est la météo actuelle ? » — sans autorisation Web.
- « Désactive le Web », puis tentative de recherche.

Ces exemples ne remplacent pas les tests automatisés.

### ARRÊT OBLIGATOIRE

**Après avoir terminé la phase 16.1, arrête ton travail.**

Ne commence aucune tâche de la phase 16.2 ou 16.3.

Remets un rapport de validation.

L'utilisateur procédera à ses propres tests et effectuera lui-même le premier commit Git.

Tu attendras ensuite son autorisation explicite pour continuer.

---

# 3. PHASE 16.2 — RECHERCHE APPROFONDIE ET VÉRIFICATION DES FAITS

## Condition de démarrage

**Cette phase ne doit commencer qu'après validation explicite de la phase 16.1 par l'utilisateur.**

Elle devra réutiliser l'architecture précédemment créée, sans reconstruire le Web Gateway.

## Objectif général

Permettre à Léa de vérifier des affirmations en consultant plusieurs sources pertinentes et en expliquant précisément ce que les éléments disponibles permettent de conclure.

Cette phase est particulièrement importante pour :

- Les actualités.
- Les informations politiques.
- Les publications sur les réseaux sociaux.
- Les affirmations provenant de TikTok.
- Les informations scientifiques.
- Les nouvelles technologies.
- Les rumeurs.
- Les déclarations publiques.
- Les données contradictoires.

**Léa doit aider à vérifier, pas donner automatiquement raison à une publication ni la déclarer fausse sans preuve.**

---

## 16.2.1. Recherches complémentaires contrôlées

Permettre plusieurs recherches sur un même sujet.

Par exemple :

Utilisateur :
« Vérifie sur Internet si cette affirmation sur une nouvelle batterie est vraie. »

Léa peut :

1. Rechercher l'affirmation.
2. Identifier son origine.
3. Chercher des sources primaires.
4. Consulter des sources complémentaires.
5. Comparer les résultats.
6. Formuler une conclusion étayée.

Toutes ces recherches doivent appartenir à la même opération explicitement autorisée.

Imposer des limites configurables de requêtes, de sources et de durée.

Ne pas lancer indéfiniment des recherches complémentaires.

---

## 16.2.2. Comparaison et fiabilité des sources

Développer une sélection des sources pertinente, sans système arbitraire de crédibilité basé uniquement sur le nom du domaine.

Prendre notamment en compte :

- La proximité avec la source primaire.
- L'existence de preuves consultables.
- La date.
- La pertinence.
- La cohérence avec d'autres sources indépendantes.
- Le contexte original.
- Les limites méthodologiques.
- La distinction entre faits et opinions.

Privilégier les sources primaires lorsque possible :

- Documents officiels.
- Communiqués originaux.
- Résultats sportifs officiels.
- Organismes météorologiques.
- Documentation technique officielle.
- Articles scientifiques.
- Déclarations originales accessibles.

Ne considère pas plusieurs copies d'une même dépêche comme plusieurs confirmations indépendantes.

Une source de qualité ne garantit pas automatiquement que chaque affirmation qu'elle contient est correcte.

---

## 16.2.3. Vérification des dates

Distinguer rigoureusement :

- Date de publication.
- Date de mise à jour.
- Date de l'événement.
- Date de consultation.

Lorsqu'une information dépend de la date, Léa doit pouvoir préciser à quel moment elle se rapporte.

Exemple :

Un article publié aujourd'hui peut décrire un événement survenu il y a plusieurs années.

Ne jamais confondre les deux.

Pour les scores sportifs, tenir compte de la date réelle du match et, si nécessaire, du fuseau horaire.

Pour les actualités, ne pas qualifier une information d'actuelle simplement parce qu'elle apparaît en tête des résultats.

---

## 16.2.4. Vérification d'affirmations provenant des réseaux sociaux

Exemple :

Utilisateur :
« J'ai vu un TikTok disant que Donald Trump a annoncé telle mesure. Vérifie sur Internet si c'est vrai. »

Léa doit rechercher :

- L'affirmation exacte.
- Son contexte.
- Sa date.
- Les déclarations originales lorsqu'elles sont accessibles.
- Les sources primaires pertinentes.
- Les confirmations indépendantes.
- Les éventuelles contradictions.

La conclusion doit distinguer, selon les preuves disponibles :

- Affirmation confirmée.
- Affirmation partiellement confirmée.
- Affirmation contredite.
- Affirmation trompeuse ou sortie de son contexte.
- Information insuffisante pour conclure.

Ne force pas un verdict binaire lorsque les preuves ne le permettent pas.

Ne prétends jamais avoir visionné une vidéo dont le contenu n'a pas été réellement accessible.

Si TikTok ou une autre plateforme empêche la consultation, Léa peut demander une transcription, un extrait ou une description de l'affirmation.

Ne contourne pas les protections des plateformes.

---

## 16.2.5. Lecture des documents publics

Étendre la lecture aux documents publics pertinents, notamment les PDF.

Prévoir une extraction limitée et sécurisée.

Contraintes :

- Lecture en mémoire lorsque raisonnablement possible.
- Taille maximale configurable.
- Limite du nombre de pages ou de caractères.
- Délais d'attente.
- Vérification du type de contenu réel.
- Protection contre les fichiers malformés.
- Pas d'exécution de contenu actif.
- Pas de stockage durable du document sans besoin justifié.
- Nettoyage des temporaires éventuels.

Ne pas installer de système OCR lourd pour cette phase.

Si un PDF est composé uniquement d'images sans texte exploitable, expliquer cette limite.

Ne prétends pas avoir lu intégralement un document dont seule une partie a été extraite.

---

## 16.2.6. Liens vers des vidéos publiques

Permettre l'analyse des métadonnées, descriptions ou transcriptions accessibles publiquement.

Cela concerne notamment des liens provenant de :

- TikTok.
- YouTube.
- Autres plateformes publiques.

Cette fonctionnalité doit être opportuniste et non dépendante d'une API payante.

Si le contenu textuel est indisponible :

- Ne pas inventer la vidéo.
- Ne pas simuler son visionnement.
- Ne pas contourner les restrictions.
- Proposer à l'utilisateur de fournir le texte pertinent.

**Ne développe pas de système de compréhension vidéo dans cette phase.**

L'analyse visuelle et multimodale relève d'une évolution distincte.

---

## 16.2.7. Citations et preuves

Améliorer le rattachement entre les affirmations et les sources.

Lorsque Léa présente une information issue du Web :

- Identifier les sources effectivement consultées.
- Fournir des liens utilisables.
- Éviter les références inventées.
- Ne pas citer un document simplement parce qu'il apparaît dans les résultats.
- Distinguer un extrait de moteur d'une page réellement consultée.
- Expliquer les contradictions importantes.
- Reconnaître les limites de vérification.

Les références doivent être associées à des identifiants contrôlés par le backend.

Une référence générée librement par le modèle ne doit pas devenir automatiquement une source considérée comme valide.

Prévoir une validation des citations avant leur affichage.

Aucune citation fictive ne doit être rendue comme une source vérifiée.

---

## 16.2.8. Gestion des résultats contradictoires

Lorsqu'une information est contradictoire :

1. Identifier les points de désaccord.
2. Vérifier les dates et le contexte.
3. Examiner les preuves accessibles.
4. Distinguer l'incertitude réelle des informations périmées.
5. Présenter une conclusion proportionnée.

Éviter les conclusions inventées.

Si les sources ne permettent pas de trancher, Léa doit le dire.

Ne pas remplacer la vérification par un vote majoritaire entre sites.

---

## 16.2.9. Tests obligatoires

Tester :

- Recherche multi-sources.
- Respect de l'autorisation manuelle.
- Nombre maximal de recherches.
- Sources contradictoires.
- Sources non indépendantes.
- Dates différentes.
- Contenu périmé.
- Source primaire disponible.
- Source primaire inaccessible.
- PDF valide.
- PDF malformé.
- PDF trop volumineux.
- PDF sans texte exploitable.
- Lien TikTok inaccessible.
- Transcription absente.
- Citation inventée par le modèle.
- Source affichée mais non consultée.
- Tentative d'injection dans un article ou un PDF.
- Annulation.
- Absence de fuite d'informations privées.
- Non-régression de la phase 16.1.

Utiliser des contenus simulés pour les tests déterministes.

Compléter par quelques vérifications réelles lorsque les conditions permettent un accès Web autorisé.

---

## CRITÈRES DE VALIDATION DE LA PHASE 16.2

La phase est terminée lorsque Léa peut :

1. Examiner plusieurs sources pertinentes.
2. Vérifier une affirmation récente.
3. Détecter une contradiction importante.
4. Distinguer les dates.
5. Lire les documents publics pris en charge.
6. Ne pas prétendre avoir consulté une vidéo inaccessible.
7. Afficher uniquement des citations réellement fondées.
8. Reconnaître les cas impossibles à confirmer.
9. Respecter strictement l'autorisation Web.
10. Conserver les fonctionnalités validées en phase 16.1.

### Validation manuelle

Proposer des tests réalistes :

- Une affirmation vérifiable provenant d'une actualité.
- Une affirmation volontairement fausse.
- Une affirmation sortie de son contexte.
- Un lien TikTok accessible ou inaccessible.
- Un article scientifique public.
- Un document PDF.
- Deux sources présentant des informations contradictoires.

### ARRÊT OBLIGATOIRE

**Après la phase 16.2, arrête ton travail.**

Ne commence pas la phase 16.3.

Remets un rapport complet.

L'utilisateur procédera à ses tests et réalisera lui-même le deuxième commit Git.

Attends son autorisation explicite pour la suite.

---

# 4. PHASE 16.3 — NAVIGATION WEB PUBLIQUE EN LECTURE SEULE

## Condition de démarrage

**Cette phase ne doit commencer qu'après validation explicite de la phase 16.2 par l'utilisateur.**

Elle complète les deux phases précédentes.

Elle ne transforme pas Léa en agent autonome capable d'agir sur des comptes ou sur des services.

## Objectif général

Permettre à Léa de lire certains sites publics dont le contenu ne peut pas être correctement extrait par une simple requête HTTP.

Exemples :

- Pages dont le contenu est généré en JavaScript.
- Articles utilisant des interfaces dynamiques.
- Pages publiques à pagination.
- Sites nécessitant l'ouverture d'une section pour afficher du texte.
- Tableaux publics dont les données apparaissent après chargement.
- Contenus publics difficiles à consulter avec le lecteur HTML standard.

**La navigation reste limitée à la lecture d'informations publiques.**

---

## 16.3.1. Moteur de navigation léger et facultatif

Étudier Playwright ou une solution comparable.

Contraintes impératives :

- Ne jamais lancer le navigateur automatiquement au démarrage de Léa.
- Ne jamais le maintenir ouvert en permanence.
- Ne jamais le charger pour une recherche simple.
- Ne pas lancer plusieurs navigateurs inutilement.
- Limiter strictement le nombre de pages et processus.
- Imposer des délais d'attente.
- Fermer les pages après utilisation.
- Fermer le navigateur à la fin de l'opération.
- Libérer les ressources après annulation ou erreur.

Étudier la possibilité d'utiliser un navigateur Chromium déjà installé sur le PC, notamment Edge, lorsque cette option permet une intégration sûre et fiable.

Ne réutilise jamais le profil personnel du navigateur de l'utilisateur.

Aucune session personnelle, aucun mot de passe et aucun cookie de son navigateur habituel ne doivent être accessibles.

Le navigateur automatisé doit disposer d'un contexte isolé et éphémère.

Une installation additionnelle volumineuse doit être évitée autant que possible et ne doit pas être réalisée silencieusement.

Si une dépendance indispensable exige une installation ou un téléchargement sur le PC de développement, documente-le et obtiens l'accord approprié avant cette opération.

---

## 16.3.2. Navigation autorisée

Permettre uniquement les opérations nécessaires à la lecture.

Exemples :

- Ouvrir une page publique autorisée.
- Attendre un chargement raisonnable.
- Lire le texte visible.
- Suivre un lien public pertinent.
- Ouvrir une section de lecture.
- Développer un contenu textuel masqué.
- Parcourir une pagination publique.
- Lire un tableau dynamique.
- Extraire les informations accessibles.

Toutes ces actions doivent appartenir à la demande explicitement autorisée.

La navigation doit respecter un budget maximal de pages, d'actions et de temps.

Ne pas laisser le modèle décider librement d'une succession illimitée de clics.

---

## 16.3.3. Interdictions absolues

Le navigateur ne doit jamais :

- Se connecter à un compte.
- Accéder au profil personnel Edge ou Chrome.
- Saisir un identifiant.
- Saisir un mot de passe.
- Créer un compte.
- Remplir ou soumettre un formulaire transactionnel.
- Publier un commentaire.
- Envoyer un message.
- Effectuer un achat.
- Ajouter un produit à un panier.
- Initier un paiement.
- Effectuer une réservation.
- Télécharger un fichier utilisateur.
- Installer une extension.
- Installer un programme.
- Exécuter un script arbitraire fourni comme commande par une page.
- Lire des fichiers locaux.
- Accéder aux services internes du PC.
- Contourner un CAPTCHA.
- Contourner un paywall.
- Contourner une authentification.
- Modifier des informations sur un service distant.

Bloquer les méthodes et comportements susceptibles de modifier un état distant lorsque cela peut être appliqué techniquement.

Un clic n'est pas automatiquement sûr : certaines interfaces déclenchent des actions même sans formulaire explicite.

Privilégier une navigation fondée sur des destinations publiques validées et des actions dont le comportement de lecture est suffisamment établi.

En cas de doute sur l'effet d'un élément interactif, ne pas cliquer.

---

## 16.3.4. Isolation et permissions du navigateur

Appliquer des restrictions fortes :

- Session éphémère.
- Aucune réutilisation des cookies personnels.
- Aucune persistance d'identifiants.
- Aucun accès aux fichiers locaux.
- Aucun accès aux adresses internes.
- Aucun téléchargement utilisateur.
- Aucun accès aux périphériques sensibles.
- Aucun accès automatique au microphone ou à la caméra.
- Aucun accès aux notifications.
- Aucun accès au presse-papiers personnel.
- Aucune élévation de privilèges.
- Aucun accès non autorisé au réseau local.

Appliquer une politique réseau cohérente avec celle du Web Gateway.

Examiner les requêtes déclenchées par le navigateur lui-même, notamment les sous-ressources et redirections.

Bloquer les destinations locales et les communications non nécessaires.

Ne pas considérer l'isolation du navigateur comme acquise sans vérification.

Si une protection essentielle ne peut pas être garantie, ne pas activer la fonctionnalité concernée.

---

## 16.3.5. Intégration à la recherche existante

La navigation dynamique doit être un outil complémentaire, et non le chemin normal de recherche.

Ordre recommandé :

1. Recherche légère.
2. Consultation HTTP classique.
3. Extraction du contenu principal.
4. Navigation dynamique uniquement si nécessaire et explicitement couverte par la demande.

Ne transforme pas une recherche simple en session de navigateur.

Si une page nécessite une connexion, explique simplement qu'elle n'est pas accessible dans le cadre des permissions de Léa.

Si un site empêche la consultation automatisée, n'essaie pas de contourner ses protections.

---

## 16.3.6. Consultation des contenus dynamiques

Prendre en charge, lorsque techniquement et légalement possible :

- Articles dynamiques.
- Tableaux de données publiques.
- Pagination.
- Sections déroulantes.
- Contenus textuels publics nécessitant JavaScript.

Pour TikTok et autres plateformes :

- Lire les métadonnées et transcriptions publiques disponibles.
- Ne pas prétendre comprendre les images ou le son d'une vidéo sans capacité réellement disponible.
- Ne pas créer de compte.
- Ne pas contourner les restrictions.
- Ne pas promettre que toutes les plateformes seront compatibles.

Si une vidéo est inaccessible, demander les informations nécessaires à l'utilisateur.

---

## 16.3.7. Liens de téléchargement

Si la navigation permet d'identifier un fichier intéressant :

- Fournir son lien à l'utilisateur.
- Privilégier le site officiel lorsque pertinent.
- Préciser ce que le lien semble contenir.
- Signaler toute incertitude sur son authenticité.

Ne pas télécharger le fichier sur le PC à la place de l'utilisateur.

Ne pas lancer automatiquement une installation.

Ne pas ouvrir automatiquement un exécutable.

L'utilisateur décide lui-même s'il souhaite télécharger ou installer quoi que ce soit.

---

## 16.3.8. Tests obligatoires

Tester notamment :

- Chargement à la demande.
- Aucun navigateur au repos.
- Fermeture après utilisation.
- Fermeture après erreur.
- Annulation.
- Limite des processus.
- Limite des pages.
- Limite des clics.
- Page JavaScript simple.
- Pagination publique.
- Contenu déroulant.
- Page nécessitant une authentification.
- Page proposant un téléchargement.
- Formulaire.
- Bouton de paiement.
- Tentative d'action non autorisée.
- Tentative de lecture de fichier local.
- Tentative d'accès localhost.
- Redirection interne.
- Requête de sous-ressource interdite.
- Injection de prompt depuis une page.
- Aucune utilisation de cookies personnels.
- Aucun accès à un compte utilisateur.
- Aucun contournement de CAPTCHA.
- Aucune consommation de ressources persistante après fermeture.
- Non-régression des phases 16.1 et 16.2.

Utiliser des sites de test locaux isolés pour simuler les interfaces et les comportements dangereux.

Cela ne constitue pas une permission d'ouvrir arbitrairement le réseau local depuis le navigateur de production.

Les exceptions de test doivent rester confinées à l'environnement de test.

---

## CRITÈRES DE VALIDATION DE LA PHASE 16.3

La phase est terminée uniquement si :

1. Léa peut consulter au moins un site public dynamique qui nécessite réellement un moteur de navigation.
2. Le navigateur fonctionne uniquement sur demande.
3. L'autorisation manuelle reste obligatoire.
4. Les sites classiques n'utilisent pas inutilement le navigateur.
5. Les comptes et authentifications sont hors périmètre.
6. Les téléchargements utilisateur sont interdits.
7. Les achats et actions transactionnelles sont interdits.
8. Les protections réseau sont vérifiées.
9. Les ressources sont libérées après utilisation.
10. Les profils et fonctionnalités précédents ne régressent pas.

Si certaines plateformes refusent l'automatisation, documenter la limitation plutôt que de développer un contournement.

Si une fonction ne peut pas être rendue suffisamment sûre, la laisser désactivée et l'indiquer explicitement.

### ARRÊT OBLIGATOIRE

Après la phase 16.3 :

- Effectue les vérifications autorisées.
- Prépare le rapport final.
- Arrête ton travail.
- Ne commence aucune étape ultérieure de la roadmap.
- Ne réalise aucun commit.
- Ne réalise aucun push.

L'utilisateur procédera aux tests manuels finaux et au troisième commit Git.

---

# 5. EXIGENCES TRANSVERSALES AUX TROIS PHASES

## 5.1. Aucune hallucination sur les résultats Web

Léa possède désormais des contrats renforcés de fiabilité.

Le Web doit respecter et soutenir ces contrats.

**Il est strictement interdit de présenter un résultat inventé comme provenant d'Internet.**

Le système doit distinguer :

- Une recherche réellement exécutée.
- Une recherche qui a échoué.
- Un résultat retourné par un fournisseur.
- Une page réellement consultée.
- Un extrait uniquement fourni par un moteur.
- Une affirmation effectivement soutenue par une source.
- Une hypothèse formulée par le modèle.

Le backend doit conserver une traçabilité suffisante pour valider les références affichées.

Aucune source non retrouvée dans les résultats de l'opération ne doit être présentée comme vérifiée.

En cas d'échec, Léa doit dire qu'elle n'a pas pu vérifier l'information.

Elle ne doit jamais inventer un résultat de match, une température, une actualité, une citation ou un article récent.

---

## 5.2. Fiabilité supérieure à la richesse des résultats

Une réponse comportant trois sources réellement consultées et pertinentes vaut mieux qu'une réponse comportant quinze références superficielles.

Ne multiplie pas les recherches sans raison.

Ne présente pas une liste interminable de résultats si quelques sources permettent de répondre correctement.

Lorsque le sujet demande une vérification plus approfondie, explique les preuves et leurs limites.

L'utilisateur recherche avant tout des informations fiables, pas une démonstration de complexité technique.

---

## 5.3. Fonctionnement intégralement local hors recherche

Léa reste un assistant local.

Lorsque le Web n'est pas sollicité :

- Aucun appel au fournisseur de recherche.
- Aucun chargement de navigateur.
- Aucune tâche réseau de recherche en arrière-plan.
- Aucune dépendance aux services Web.
- Aucune obligation de connexion Internet.
- Aucune dégradation du fonctionnement des profils.

Le mode hors ligne doit demeurer pleinement fonctionnel.

Ne considère pas l'absence de connexion Internet comme un problème empêchant Léa de démarrer.

---

## 5.4. Intégration aux paramètres

Réutiliser le Centre de paramètres existant.

Prévoir uniquement les réglages réellement utiles, par exemple :

- Autoriser ou désactiver entièrement le Web.
- Afficher le fournisseur utilisé.
- Configurer un fournisseur de recherche compatible.
- Définir des limites raisonnables de requêtes et de temps.
- Activer ou désactiver le navigateur dynamique lorsque la phase 16.3 existera.

Ne crée pas une page de paramètres parallèle.

Ne propose jamais un mode de recherche automatique.

**Le mode manuel est permanent et non modifiable dans cette étape.**

---

## 5.5. Charge mémoire et performances

Mesurer ou évaluer de manière reproductible :

- La consommation supplémentaire au repos.
- L'utilisation du processeur pendant la recherche.
- La mémoire consommée pendant une opération.
- La libération des ressources après la recherche.
- La réactivité du frontend.
- L'impact sur l'inférence du modèle actif.

Éviter les processus persistants non nécessaires.

Respecter la contrainte d'un seul modèle local chargé à la fois.

Ne pas provoquer le chargement d'un modèle supplémentaire pour analyser les résultats Web.

Ne pas créer de système de scraping massif.

Ne pas conserver de navigateur en arrière-plan.

Documenter honnêtement les mesures réellement effectuées et distinguer les estimations des observations.

---

## 5.6. Architecture extensible

Même si Léa utilise actuellement des modèles relativement modestes, son architecture doit pouvoir évoluer.

Prévoir une séparation claire entre :

- Les capacités Web.
- Les fournisseurs.
- L'orchestration.
- Les autorisations.
- Les modèles.
- Les profils.
- La présentation des résultats.

Si les modèles sont remplacés ultérieurement par un modèle local plus puissant, les capacités Web doivent rester réutilisables.

Ne fige pas l'architecture autour des particularités de Qwen.

Toutefois, ne développe pas maintenant les capacités agentiques futures.

**L'extensibilité ne justifie pas une complexité inutile dans la version actuelle.**

---

# 6. MÉTHODE DE TRAVAIL OBLIGATOIRE

## 6.1. Un seul cahier des charges, trois réalisations distinctes

Ce document constitue le cahier des charges maître de l'étape 16.

Il ne faut pas l'interpréter comme une autorisation de réaliser les trois phases immédiatement.

### Exécution autorisée maintenant

**PHASE 16.1 UNIQUEMENT.**

Les phases 16.2 et 16.3 doivent servir à anticiper les interfaces et les points d'extension.

Ne développe pas leurs fonctionnalités avant autorisation explicite.

Ne prépare pas silencieusement des travaux inutiles appartenant aux phases futures.

---

## 6.2. Validation entre les phases

Le cycle de travail est le suivant :

**Premier cycle**

1. Codex réalise 16.1.
2. Codex exécute ses tests.
3. Codex fournit un rapport.
4. L'utilisateur effectue ses tests manuels.
5. Les problèmes sont corrigés.
6. L'utilisateur valide.
7. L'utilisateur réalise son commit Git.

**Deuxième cycle**

1. L'utilisateur autorise explicitement 16.2.
2. Codex réalise uniquement 16.2.
3. Tests et rapport.
4. Validation manuelle.
5. Corrections éventuelles.
6. Commit utilisateur.

**Troisième cycle**

1. L'utilisateur autorise explicitement 16.3.
2. Codex réalise uniquement 16.3.
3. Tests et rapport.
4. Validation manuelle.
5. Corrections éventuelles.
6. Commit utilisateur.

Ne contourne jamais ce séquencement.

---

## 6.3. Discipline Git et intégrité

- Ne réalise aucun commit.
- Ne réalise aucun push.
- Ne change pas de branche sans autorisation.
- Ne réécris pas l'historique Git.
- Ne réinitialise pas le dépôt.
- Ne supprime pas de modifications préexistantes.
- Ne détruis pas les fichiers utilisateur.
- Ne supprime pas les bases de données.
- Ne supprime pas les sauvegardes.
- Ne nettoie pas agressivement les dépendances ou modèles.
- Ne modifie pas les fichiers sensibles sans nécessité.

Avant toute intervention, vérifie les modifications préexistantes.

Si une modification extérieure entre en conflit avec ton travail, signale-la.

Les commits seront réalisés manuellement par l'utilisateur après validation.

---

## 6.4. Discipline des modifications

Pour chaque phase :

1. Inspecte le code existant.
2. Définis une architecture ciblée.
3. Réutilise les composants stables.
4. Implémente les fonctions prévues.
5. Ajoute les tests nécessaires.
6. Exécute les vérifications.
7. Corrige les régressions.
8. Vérifie la sécurité.
9. Vérifie les ressources.
10. Remets ton rapport.

Ne réalise pas de refonte générale non demandée.

Ne déplace pas arbitrairement les fichiers.

Ne crée pas de fonctionnalités périphériques.

Ne modifie pas les contrats récemment optimisés sauf adaptation minimale réellement nécessaire à la disponibilité du Web.

---

## 6.5. Rapports obligatoires

À la fin de chaque phase, fournis :

### A. Fonctionnalités réalisées

Ce qui fonctionne effectivement.

### B. Fichiers modifiés

Liste des principaux fichiers créés ou modifiés, avec leur rôle.

### C. Architecture

Résumé de l'intégration technique et des interfaces utilisées.

### D. Tests exécutés

Présente :

- Les commandes réellement exécutées.
- Le nombre de tests réussis et échoués lorsqu'il est disponible.
- Les compilations ou builds effectués.
- Les résultats de validation.
- Les tests non exécutés.
- Les limites des simulations.

N'invente aucun résultat.

### E. Sécurité

Indique les protections réellement implémentées et les éventuelles limitations.

### F. Performances

Indique les observations ou mesures réelles disponibles.

### G. Régressions

Précise les fonctionnalités existantes vérifiées et celles qui ne l'ont pas été.

### H. Validation manuelle

Fournis une liste courte et ordonnée de tests que l'utilisateur peut effectuer dans l'interface.

### I. Limitations restantes

Distingue :

- Les limitations normales du fournisseur.
- Les problèmes non résolus.
- Les fonctionnalités reportées à la phase suivante.
- Les capacités volontairement interdites.

### J. État Git

Indique les modifications présentes sans réaliser de commit.

---

# 7. CONDITIONS D'ACCEPTATION GLOBALES DE L'ÉTAPE 16

À la fin des trois phases, Léa doit pouvoir :

- Rechercher une météo actuelle sur demande explicite.
- Vérifier un résultat sportif récent.
- Consulter des informations sur une nouvelle technologie.
- Chercher des actualités.
- Vérifier une affirmation médiatique ou politique.
- Comparer plusieurs sources.
- Consulter un article public.
- Lire un document PDF public compatible.
- Examiner une affirmation issue de TikTok lorsque son contenu est accessible ou fourni.
- Reconnaître qu'une information ne peut pas être vérifiée.
- Fournir des sources réellement consultées.
- Ouvrir certains sites publics utilisant JavaScript.
- Fournir des liens de téléchargement plutôt que télécharger elle-même.
- Fonctionner avec Général, Programmation et Vétérinaire.
- Continuer de fonctionner entièrement hors ligne lorsque le Web n'est pas sollicité.

Elle ne doit jamais :

- Se connecter à un compte.
- Acheter quoi que ce soit.
- Télécharger un fichier utilisateur à sa place.
- Remplir ou soumettre des formulaires transactionnels.
- Publier un contenu.
- Contourner les restrictions d'un site.
- Utiliser le Web sans autorisation.
- Inventer des résultats de recherche.
- Inventer des sources.
- Inventer une consultation de page.
- Présenter une vérification qui n'a pas eu lieu comme réussie.
- Accéder aux fichiers ou services locaux par l'intermédiaire d'une URL malveillante.
- Laisser tourner un navigateur ou un service lourd inutilement.

Ces restrictions doivent rester actives quel que soit le modèle utilisé.

---

# 8. INSTRUCTION D'EXÉCUTION IMMÉDIATE

**Nous commençons maintenant uniquement la PHASE 16.1 — RECHERCHE WEB FONDAMENTALE.**

Tu dois :

1. Lire entièrement ce cahier des charges.
2. Examiner l'architecture actuelle de Léa.
3. Identifier les points d'intégration.
4. Choisir une solution de recherche gratuite et sans compte, après vérification de sa faisabilité.
5. Concevoir un Web Gateway modulaire et léger.
6. Implémenter le contrôle manuel strict de l'accès Internet.
7. Intégrer la recherche et la lecture de pages publiques aux trois profils.
8. Ajouter les citations et les éléments d'interface nécessaires.
9. Préserver tous les composants existants.
10. Développer et exécuter les tests pertinents.
11. Vérifier que Léa n'effectue aucune recherche sans autorisation.
12. Fournir un rapport détaillé et honnête.

**Ne commence pas la phase 16.2.**

**Ne commence pas la phase 16.3.**

**Ne réalise aucun commit ni push.**

**Ne considère pas une recherche simulée comme une preuve que la recherche réelle fonctionne.**

Si un choix technique présente un risque important pour la sécurité, la stabilité ou les performances, privilégie une solution plus simple et fiable et explique la limitation.

Si une fonctionnalité ne peut pas être correctement réalisée dans les contraintes établies, ne simule pas sa réussite.

À la fin de la phase 16.1, arrête-toi et attends la validation de l'utilisateur.

**Objectif final : offrir à Léa un accès Internet réellement utile, gratuit, léger et vérifiable, sans jamais lui retirer le contrôle de l'utilisateur sur ses actions.**