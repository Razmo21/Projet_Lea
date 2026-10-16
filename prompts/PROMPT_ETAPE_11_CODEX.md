# Prompt Codex — Étape 11 finale

## Architecture indépendante des modèles de Léa

Tu dois réaliser **uniquement l'étape 11**, de **11A à 11G**, dans :

```text
L:\Projet_Lea
```

L'étape 10 est terminée et validée.

Tu connais déjà Projet Léa, son architecture, son historique et les décisions prises au cours des étapes précédentes.

**Ne repars pas de zéro.**

Nous avons décidé de suspendre le laboratoire GLM/Colibrì et de poursuivre le développement avec les deux modèles Qwen actuellement utilisés.

L'objectif de l'étape 11 est simple :

> Rendre Léa indépendante des modèles d'intelligence artificielle utilisés, afin de pouvoir remplacer facilement chaque modèle par un autre sans devoir modifier toute l'architecture de Léa.

Les modèles actuels doivent continuer à fonctionner comme avant.

Si je veux remplacer le modèle Général ou Programmation par un autre modèle compatible avec le moteur déjà pris en charge, je dois pouvoir le faire **principalement en modifiant un fichier de configuration central**.

Si, plus tard, nous voulons utiliser un autre moteur d'inférence comme Colibrì, l'architecture devra permettre l'ajout d'un adaptateur ciblé, sans réécrire les composants de Léa.

**Cette étape est exclusivement architecturale.**

Ne la transforme pas en chantier de nouvelles fonctionnalités, de refonte du frontend ou d'intégration de nouveaux modèles.

---

# 1. Règles générales

Travaille de manière autonome, méthodique et rigoureuse.

Avant toute modification, lis obligatoirement :

- `AGENTS.md`
- `README.md`
- `TODO.md`
- `CHANGELOG.md`
- `docs/DECISIONS.md`, s'il existe
- les éventuels fichiers d'instructions supplémentaires du dépôt ;
- le code actuel du registre modèles/profils ;
- les composants actuels de chargement et de commutation des modèles ;
- les scripts PowerShell et fichiers de configuration concernés ;
- les modules liés au profil Programmation et à OpenHands.

Lis les documents présents en entier lorsqu'ils constituent les instructions ou les décisions de référence du projet.

Si un fichier n'existe pas, ne l'invente pas. Signale simplement son absence si elle est pertinente.

Vérifie ensuite l'état réel du dépôt :

```text
git status
git diff --check
git log -1 --oneline
```

Ne suppose pas que les fichiers sont identiques à ceux de notre dernière conversation.

N'écrase aucune modification locale préexistante.

Si l'état Git présente des modifications inattendues pouvant être affectées par cette étape, signale-les avant d'intervenir dessus.

Interdictions :

- Aucun commit.
- Aucun push.
- Aucun rebase.
- Aucun reset destructif.
- Aucun `git clean`.
- Aucune modification de l'historique Git.
- Aucune suppression non vérifiée.
- Aucun téléchargement de nouveau modèle.
- Aucune modification du laboratoire GLM/Colibrì.
- Aucune réinstallation inutile de composants existants.

Réutilise ce qui fonctionne déjà.

Ne reconstruis pas une infrastructure que nous avons précédemment validée.

---

# 2. Architecture finale recherchée

La séparation attendue est la suivante :

```text
                         LÉA
                          │
              ┌───────────┴───────────┐
              │                       │
        Conversations              Mémoire
              │                       │
              └───────────┬───────────┘
                          │
                  Gestion des profils
                          │
             ┌────────────┴────────────┐
             │                         │
        Général                  Programmation
             │                         │
       Contrat Général         Contrat Programmation
             │                         │
       Permissions              Outils / OpenHands
             │                         │
             └────────────┬────────────┘
                          │
                 Registre central
                   profils/modèles
                          │
                 Adaptateur du moteur
                          │
                       llama.cpp
                          │
                Modèle Qwen sélectionné
```

Cette représentation est conceptuelle.

Adapte-la à l'architecture réelle du dépôt au lieu de créer artificiellement chacun de ces composants.

## Principes obligatoires

- **Léa reste l'application principale et l'orchestrateur.**
- Les conversations et la mémoire appartiennent à Léa, pas au modèle.
- Les profils définissent les comportements, les permissions et les outils autorisés.
- Un modèle est un composant interchangeable.
- Un moteur d'inférence est responsable des opérations spécifiques à l'exécution du modèle.
- Le profil Général ne doit pas dépendre structurellement de Qwen3.
- Le profil Programmation ne doit pas dépendre structurellement de Qwen2.5-Coder.
- OpenHands reste le moteur agentique de Programmation.
- Le remplacement d'un modèle ne doit pas modifier les règles de sécurité des profils.
- Plusieurs profils pourront éventuellement utiliser le même modèle compatible.
- Chaque profil pourra conserver son propre modèle.
- Le système ne doit pas supposer qu'un modèle quelconque sait effectuer des appels d'outils.

Attention : **l'indépendance des modèles ne signifie pas que tous les modèles sont automatiquement compatibles avec tous les profils.**

Il faut permettre leur remplacement tout en conservant les exigences techniques indispensables.

---

# 3. Ce qui est explicitement reporté

Ne réalise PAS maintenant :

- La page Paramètres de Léa.
- Le bouton Paramètres.
- Une API de modification des modèles.
- Un sélecteur de fichiers de modèles dans le frontend.
- Le remplacement des Qwen actuels.
- L'intégration de GLM/Colibrì.
- Le développement d'un moteur d'inférence supplémentaire.
- Un système universel de détection automatique des capacités de tous les modèles.
- Les paramètres Low/High de raisonnement.
- Le démarrage ou l'arrêt automatique de Docker Desktop.
- La programmation avancée.
- Les nouvelles capacités OpenHands.
- L'intégration Windows avancée.
- Les fonctionnalités Web.
- La vision.
- Le microphone.
- La génération d'images.
- La refonte visuelle.
- Les nouveaux profils.
- Le fine-tuning.
- Le RAG.

Pour l'étape 11 :

**Nous voulons uniquement modifier l'architecture nécessaire pour rendre les modèles interchangeables.**

La future étape 12 concernera le centre de paramètres.

L'étape 13 concernera la programmation avancée, dont le périmètre exact sera revu ultérieurement.

Ne commence ni l'étape 12 ni l'étape 13.

---

# 4. Barrières strictes

Respecte cet ordre de réalisation :

```text
11A — Audit des dépendances aux modèles
11B — Configuration centrale des modèles
11C — Séparation profils / modèles
11D — Indépendance des moteurs d'inférence
11E — Intégration au cycle de vie et à OpenHands
11F — Validation architecturale et non-régression
11G — Commentaires, nettoyage, documentation et clôture
```

Après chaque sous-étape :

1. Effectue les modifications prévues.
2. Exécute les tests ciblés disponibles.
3. Corrige les problèmes constatés.
4. Relance les tests concernés.
5. Vérifie que les fonctionnalités existantes restent cohérentes.
6. Ne passe à la sous-étape suivante qu'après validation de la précédente.

Si un mécanisme de suivi des étapes existe déjà dans le dépôt, réutilise-le lorsqu'il est adapté. N'introduis pas un nouveau système de progression uniquement pour cette étape.

Si une décision architecturale importante ne peut pas être tranchée à partir du code existant, explique les options et demande mon avis.

---

# 5. 11A — Audit des dépendances aux modèles

C'est la première véritable tâche.

Avant de modifier l'architecture, identifie comment Léa utilise actuellement ses modèles.

Inspecte notamment :

- Le registre des profils et des modèles créé ou adapté à l'étape 10.
- Les configurations existantes.
- Les chemins des poids GGUF.
- Les identifiants des modèles.
- Les commandes de lancement de llama.cpp.
- Les paramètres de contexte et de mémoire.
- Les mécanismes de démarrage et d'arrêt.
- Le gestionnaire de commutation Général / Programmation.
- Les communications backend / moteur d'inférence.
- La configuration du modèle utilisée par OpenHands.
- Les valeurs spécifiques à Qwen présentes dans le code.
- Les dépendances croisées entre profils et moteurs.

## Recherche des dépendances

Pour chaque dépendance identifiée, détermine si elle doit être :

```text
KEEP
CONFIGURE
ADAPT
REMOVE
```

- `KEEP` : conserver, car elle est déjà correctement isolée.
- `CONFIGURE` : déplacer une valeur configurable vers le registre central.
- `ADAPT` : modifier une interface ou un composant pour supprimer une dépendance inutile.
- `REMOVE` : supprimer uniquement du code devenu réellement obsolète.

Ne transforme pas automatiquement toute référence à Qwen en problème.

Une référence à Qwen est parfaitement normale dans la configuration du modèle Qwen.

Elle devient problématique lorsqu'un composant général de Léa dépend inutilement de son identité.

## Résultat attendu de 11A

Présente brièvement :

- Les dépendances actuellement présentes.
- Les parties déjà correctement architecturées.
- Les problèmes qu'il faut réellement corriger.
- Les fichiers concernés.
- Le plan de modifications proposé.

Évite les refactorisations sans justification technique.

---

# 6. 11B — Configuration centrale des modèles

Nous avons décidé que **le remplacement manuel des modèles passera d'abord par un fichier de configuration central**.

Aucune interface de modification n'est nécessaire à cette étape.

## Objectif

Je veux pouvoir remplacer un modèle compatible en modifiant principalement sa configuration.

Par exemple :

```text
Profil Général
    ↓
Modèle enregistré dans le registre
    ↓
Chemin du nouveau fichier GGUF
    ↓
Démarrage du modèle sélectionné
```

Ce flux ne doit pas nécessiter de modifier plusieurs fichiers Python.

## Registre

Réutilise et améliore le registre déjà existant à l'étape 10.

Il devra représenter clairement les éléments nécessaires, notamment :

- Les identifiants des modèles.
- Les associations profil/modèle.
- Les chemins des fichiers modèles.
- Le moteur utilisé.
- Les paramètres de chargement.
- Les paramètres de contexte.
- Les capacités importantes pour les profils.
- Les paramètres spécifiques au moteur lorsque nécessaire.

Choisis uniquement les champs réellement utiles.

Il ne faut pas créer un registre gigantesque avec des dizaines d'options hypothétiques.

## Source de vérité

Évite les duplications contradictoires.

Si une valeur est enregistrée dans la configuration centrale, elle ne doit pas rester codée en dur ailleurs sans nécessité.

Conserve les valeurs spécifiques à l'installation locale dans une configuration adaptée, sans publier accidentellement de secrets ou de données personnelles dans Git.

Si l'application doit prendre en charge des chemins locaux variables, prévois une méthode simple et documentée.

## Validation

Le système doit détecter proprement :

- Une configuration invalide.
- Un modèle inconnu.
- Un fichier modèle absent.
- Un chemin incorrect.
- Un moteur non pris en charge.
- Une association profil/modèle incohérente.
- Une capacité essentielle manquante ou non déclarée.

Les erreurs doivent être compréhensibles.

Ne fais pas planter silencieusement Léa.

## Tests 11B

Teste :

- Configuration valide.
- Profil Général correctement associé.
- Profil Programmation correctement associé.
- Remplacement d'une référence de modèle par configuration.
- Modèle inconnu.
- Chemin absent.
- Moteur non pris en charge.
- Configuration malformée.
- Absence de duplication contradictoire des valeurs importantes.

Utilise des configurations temporaires pour les tests de remplacement.

Ne modifie pas définitivement les modèles officiels simplement pour tester un autre chemin.

---

# 7. 11C — Séparation profils / modèles

Cette sous-étape doit rendre la séparation entre les profils et leurs modèles explicite.

## Profil Général

Conserve :

- Son identité.
- Ses instructions.
- Ses règles de fiabilité.
- Ses permissions.
- Ses interactions avec la mémoire.
- Son fonctionnement conversationnel.

Mais le fonctionnement du profil ne doit pas dépendre du nom précis de son Qwen actuel.

## Profil Programmation

Conserve :

- Son contrat de comportement.
- Ses permissions.
- Ses outils autorisés.
- Son intégration OpenHands.
- Son confinement.
- Ses règles de validation.
- Ses checkpoints.
- Ses mécanismes d'acceptation et de rollback.

Le cerveau du profil Programmation doit être référencé par configuration.

Le profil ne doit pas être construit autour d'un nom de modèle particulier.

## Exigences propres aux profils

Il faut distinguer :

```text
Le profil demande certaines capacités.

Le modèle déclare ou fournit ces capacités.

Le moteur permet leur utilisation.
```

Par exemple, Programmation nécessite certaines fonctionnalités pour utiliser OpenHands correctement.

Ne considère pas qu'un modèle devient compatible simplement parce qu'il répond à une conversation.

Pour l'étape 11, contente-toi de vérifier les exigences nécessaires aux profils actuels.

Ne développe pas un système général sophistiqué d'analyse automatique des modèles.

## Modèles partagés

L'architecture doit permettre de représenter deux profils associés au même modèle.

Cela ne signifie pas qu'il faut obligatoirement charger plusieurs profils simultanément ou lancer plusieurs serveurs pour un même modèle.

Préserve les règles actuelles de chargement, de commutation et de limitation des ressources.

## Tests 11C

Valide :

- Général et Programmation conservent leurs contrats respectifs.
- Les modèles sont sélectionnés indépendamment de la logique métier.
- Deux profils peuvent référencer le même modèle compatible.
- Les permissions restent propres aux profils.
- La mémoire et les conversations restent indépendantes des poids du modèle.
- Aucune nouvelle dépendance structurelle à Qwen n'a été introduite.

---

# 8. 11D — Indépendance des moteurs d'inférence

Actuellement, Léa utilise llama.cpp.

Nous conservons ce moteur.

L'objectif n'est pas de le remplacer maintenant, mais **d'éviter que toute l'application dépende directement de ses particularités**.

## Architecture recherchée

```text
Léa
  │
  ▼
Gestionnaire des profils
  │
  ▼
Configuration du modèle
  │
  ▼
Couche d'adaptation du moteur
  │
  ▼
llama.cpp
  │
  ▼
Qwen
```

Pour le futur :

```text
Couche d'adaptation du moteur
        │
        ├── llama.cpp
        │
        └── autre moteur, ultérieurement
```

La deuxième branche est une possibilité future, pas une implémentation à réaliser maintenant.

## Responsabilités

Examine les opérations suivantes :

- Préparation de la configuration du moteur.
- Construction de la commande de lancement.
- Gestion des processus.
- Chargement et disponibilité du modèle.
- Connexion à l'endpoint local.
- Envoi des requêtes.
- Réception des réponses.
- Gestion des erreurs.
- Arrêt du moteur.
- Nettoyage des ressources.

Détermine quelles opérations sont génériques et lesquelles sont réellement propres à llama.cpp.

Si nécessaire, introduis une interface ou un adaptateur léger.

Mais ne crée pas de classes abstraites, d'héritages multiples ou de systèmes de plugins simplement pour anticiper tous les moteurs possibles.

## Contraintes

- llama.cpp doit continuer à fonctionner.
- Les paramètres validés des deux Qwen doivent être préservés.
- Le lancement des modèles doit rester cohérent avec la configuration réelle.
- Aucun nouveau moteur ne doit être téléchargé ou lancé.
- Aucun adaptateur Colibrì fictif.
- Aucun changement inutile du protocole utilisé par le frontend.

## Tests 11D

Teste :

- Le moteur actuellement configuré est correctement résolu.
- Le modèle reçoit ses paramètres utiles.
- La construction des commandes reste correcte.
- Les erreurs de configuration sont gérées.
- Les processus peuvent être démarrés et arrêtés proprement.
- Le moteur non pris en charge est refusé clairement.
- Les autres composants n'ont pas besoin de connaître inutilement les détails internes de llama.cpp.

Ne déclare pas la compatibilité avec un futur moteur comme testée.

---

# 9. 11E — Cycle de vie et intégration OpenHands

Le fonctionnement actuel de Léa doit être conservé.

## Cycle de vie

```text
Utilisateur
    ↓
Frontend Léa
    ↓
Sélection Général / Programmation
    ↓
Bouton Démarrer
    ↓
Backend Léa
    ↓
Configuration du profil
    ↓
Résolution du modèle
    ↓
Démarrage du moteur
    ↓
Modèle prêt
```

Le fonctionnement concret doit être vérifié dans le code, notamment pour les composants déjà lancés ou arrêtés par le système existant.

## Règles obligatoires

- Ne pas charger inutilement plusieurs gros modèles.
- Ne pas permettre un changement de modèle pendant une génération active.
- Ne pas perturber un run OpenHands actif.
- Préserver le comportement actuel de commutation des profils.
- Préserver les vérifications de disponibilité réelle.
- Préserver la gestion des erreurs de démarrage.
- Préserver les mécanismes de récupération déjà présents.
- Arrêter proprement les processus appartenant à la session concernée.

Ne mets pas en place de remplacement à chaud.

Un changement de configuration suivi d'un redémarrage de l'IA est acceptable.

## OpenHands

Vérifie que son intégration utilise correctement le modèle associé au profil Programmation.

Évite les références codées en dur au modèle actuel lorsque ces références devraient provenir du registre.

Conserve :

- L'intégration Agent Server / SDK.
- Le protocole réellement utilisé.
- Les appels d'outils.
- Les restrictions de projets.
- Les règles de sécurité.
- La gestion des runs.
- La validation.
- Les checkpoints.
- L'acceptation.
- Le rollback.

Ne remplace pas OpenHands.

Ne reconstruis pas une boucle agentique maison.

Ne modifie pas le périmètre autorisé de `IA_WORKSPACE`.

## Tests 11E

Teste :

- Démarrage du profil Général.
- Arrêt du profil Général.
- Démarrage du profil Programmation.
- Disponibilité réelle des composants nécessaires.
- Résolution du modèle attendu par OpenHands.
- Commutation Général → Programmation → Général.
- Refus ou gestion sûre d'une commutation pendant une opération active.
- Gestion propre d'un échec de démarrage.
- Non-régression des contrôles de sécurité.

Lorsque les tests réels nécessitent Docker ou OpenHands, respecte l'état des services existants.

Ne démarre pas de gros composants sans tenir compte des ressources disponibles.

---

# 10. 11F — Validation architecturale et non-régression

Cette sous-étape doit démontrer que l'architecture fonctionne réellement.

Ne considère pas une simple compilation comme une validation complète.

## Test 1 — Profil Général

Valide :

- Démarrage.
- Réponse conversationnelle.
- Utilisation du modèle configuré.
- Fonctionnement de la mémoire.
- Historique des conversations.
- Conservation du comportement actuel `/no_think`.
- Arrêt propre.

## Test 2 — Profil Programmation

Valide :

- Démarrage du profil.
- Résolution du modèle Programmation.
- Connexion à OpenHands lorsque l'environnement le permet.
- Fonctionnement d'une requête technique simple.
- Conservation des permissions.
- Retour vers Général.
- Absence de régression dans les composants liés à la programmation.

Si un véritable run OpenHands peut être effectué sans danger, utilise un projet de test autorisé et temporaire.

Ne touche pas au dépôt principal à travers les outils agentiques de Léa.

## Test 3 — Remplacement du modèle par configuration

Avec une configuration temporaire ou un environnement de test :

- Change une association profil/modèle.
- Vérifie que la nouvelle association est correctement résolue.
- Vérifie que le code métier n'a pas besoin d'être modifié.
- Vérifie les erreurs si le modèle est absent ou incompatible.
- Restaure la configuration officielle.

Ne télécharge aucun modèle supplémentaire pour démontrer cette capacité.

Si un autre GGUF compatible déjà disponible permet une validation réelle sans risque, tu peux l'utiliser à condition de ne pas altérer la configuration officielle.

Sinon, distingue le test de résolution de configuration du test réel d'inférence.

## Test 4 — Sécurité

Vérifie :

- Configuration invalide refusée.
- Moteur inconnu refusé.
- Chemin modèle incorrect géré.
- Aucun élargissement des permissions OpenHands.
- Aucun accès non autorisé créé par la migration.
- Aucun modèle ou secret ajouté au dépôt Git.
- Aucun contournement des règles de confinement.

## Test 5 — Non-régression

Relance les suites pertinentes :

- Backend.
- Frontend.
- Build React / TypeScript.
- Conversations.
- Mémoire.
- Gestion des profils.
- Configuration.
- Commutation.
- OpenHands.
- Checkpoints et rollback.
- Scripts PowerShell concernés.
- Tests de sécurité concernés.

Puis :

```text
git diff --check
```

## Bilan des tests

Distingue clairement :

- Les tests réussis.
- Les tests échoués.
- Les tests non exécutés.
- Les simulations et mocks.
- Les véritables tests avec les modèles.
- Les tests de bout en bout.

Ne prétends jamais avoir testé une fonctionnalité qui n'a pas été réellement exécutée.

En cas de blocage, explique-le précisément.

---

# 11. 11G — Commentaires, qualité, nettoyage et documentation

Cette sous-étape est obligatoire.

L'objectif est de livrer du code propre, clair, professionnel et compréhensible par un développeur découvrant Projet Léa.

## Commentaires du code

Dans chaque fichier source créé ou substantiellement modifié pendant l'étape 11, **chaque fonction, méthode ou callback significatif doit posséder un commentaire ou une docstring réellement utile**.

Documente notamment :

- Le rôle des fonctions.
- Les entrées et sorties importantes.
- Les exceptions significatives.
- Les classes et interfaces.
- Les décisions architecturales particulières.
- Le fonctionnement du registre des modèles.
- La résolution profil/modèle.
- Les validations de configuration.
- Les frontières avec llama.cpp.
- La gestion des processus.
- La commutation des profils.
- L'intégration OpenHands.
- Les protections de sécurité.

Ajoute davantage de commentaires sur les passages complexes.

Lorsqu'un bloc semble difficile à comprendre immédiatement, explique pourquoi il est nécessaire et ce qu'il garantit.

Les commentaires doivent être :

- Sérieux.
- Techniques.
- Précis.
- Compréhensibles.
- Sans emojis.
- Sans formulations artificielles.
- Sans informations inventées.
- Sans répétitions inutiles.

Évite les commentaires qui ne font que traduire une ligne de code évidente.

Vérifie que les commentaires restent parfaitement cohérents avec le comportement réel.

## Lisibilité et aération

Je veux un code visuellement propre et respirant.

Applique les principes suivants :

- Lignes vides entre les blocs logiques.
- Séparation claire des fonctions.
- Indentation cohérente.
- Noms explicites.
- Fonctions de taille raisonnable.
- Conditions complexes présentées lisiblement.
- Paramètres longs répartis sur plusieurs lignes.
- Expressions difficiles séparées lorsque nécessaire.
- Commentaires placés près du code concerné.
- Regroupement logique des responsabilités.
- Respect du style existant du projet.

Évite les lignes inutilement longues et les blocs de code excessivement compacts.

Utilise les outils de formatage et de vérification déjà présents.

Ne reformate pas tout le dépôt simplement pour produire un diff plus volumineux.

## Nettoyage du code obsolète

Effectue une revue spécifique du code devenu inutile après l'étape 11.

Recherche :

- Anciennes références codées en dur devenues obsolètes.
- Anciennes configurations remplacées.
- Imports inutilisés.
- Fonctions devenues inutiles.
- Interfaces redondantes.
- Fichiers temporaires du développement.
- Duplications introduites pendant la migration.
- Code mort confirmé.
- Commentaires devenus incorrects.

Pour les composants concernés, détermine :

```text
KEEP
ADAPT
REMOVE
```

Ne supprime un fichier ou un composant qu'après avoir vérifié ses références et ses éventuels usages indirects.

Ne supprime pas :

- Les données utilisateur.
- Les conversations.
- La mémoire.
- Les modèles.
- Les checkpoints.
- Les journaux d'audit nécessaires.
- Les fichiers GLM/Colibrì.
- Les fichiers dont l'inutilité n'est pas établie.

En cas de doute, conserve le fichier et signale-le.

Ne laisse pas plusieurs anciennes et nouvelles architectures concurrentes sans nécessité.

## Documentation finale

Après validation, mets à jour les documents existants concernés :

- `README.md`
- `TODO.md`
- `CHANGELOG.md`
- `AGENTS.md`, uniquement si les instructions doivent être actualisées
- `docs/DECISIONS.md`, s'il existe
- La documentation technique pertinente.

Documente clairement :

```text
Léa = application et orchestrateur

Profil = comportement, outils et permissions

Modèle = cerveau interchangeable

Moteur = système d'inférence

Configuration centrale = association profil/modèle
```

Explique précisément :

- Où se trouve le registre.
- Comment remplacer un modèle Général.
- Comment remplacer un modèle Programmation.
- Comment définir le chemin d'un modèle.
- Comment associer un modèle à un profil.
- Quels paramètres peuvent être modifiés.
- Quelles capacités doivent être respectées.
- Comment arrêter et redémarrer correctement après un changement.
- Ce qu'il faudra faire pour ajouter plus tard un autre moteur.

## Roadmap

La roadmap validée est désormais :

```text
Étape 11 — Architecture indépendante des modèles
Étape 12 — Centre de paramètres de Léa
Étape 13 — Programmation avancée
Étape 14 — Entrées multimodales
Étape 15 — Veterinary
Étape 16 — Auxiliaire
Étape 17 — Génération d'images
Étape 18 — Web Gateway
Étape 19 — Speech-to-Speech
Étape 20 — Refonte visuelle
Étape 21 — Mémoire avancée
Étape 22 — Fine-tuning optionnel
Étape 23 — Sécurité finale
Étape 24 — Tests finaux
Étape 25 — Logiciel desktop final
```

Le périmètre précis de l'étape 13 sera rediscuté plus tard.

Ne modifie pas son contenu détaillé maintenant.

Ne change pas les autres décisions de roadmap.

Ne crée pas de numéro « bis ».

Ne commence pas l'étape 12.

---

# 12. Nettoyage final

À la fin du développement :

- Arrête les modèles lancés uniquement pour les tests.
- Arrête les processus de test encore actifs.
- Arrête les services FastAPI/Vite démarrés uniquement pour cette validation.
- Termine proprement les runs OpenHands de test.
- Nettoie uniquement les artefacts temporaires créés pour cette étape et confirmés inutiles.
- Préserve les données et volumes OpenHands nécessaires.
- Préserve les conversations et la mémoire.
- Préserve les véritables checkpoints.
- Ne ferme pas des services qui étaient déjà utilisés avant tes tests.
- Ne supprime aucun modèle.
- Ne modifie pas Docker Desktop au-delà de ce qui est strictement nécessaire aux tests autorisés.

Vérifie les processus et services encore actifs.

Puis exécute :

```text
git status

git diff --check
```

Confirme :

- Aucun modèle ajouté à Git.
- Aucun secret ajouté.
- Aucun fichier personnel supprimé.
- Aucun commit effectué.
- Aucun push effectué.
- Aucun changement non justifié hors périmètre.

Relance les tests concernés si la passe finale de nettoyage ou de lisibilité a modifié du code exécutable.

---

# 13. Critère final de réussite

L'étape 11 est terminée si, et seulement si :

> Léa fonctionne toujours avec ses deux modèles Qwen actuels, mais son architecture ne dépend plus structurellement de leur identité. Les profils restent indépendants, les modèles sont décrits dans une configuration centralisée, et le remplacement d'un modèle compatible ne nécessite plus de modifier toute la logique applicative.

Il faut également que :

- Le profil Général fonctionne toujours.
- Le profil Programmation fonctionne toujours.
- La mémoire et les conversations soient préservées.
- Les mécanismes OpenHands restent opérationnels.
- Les règles de sécurité soient maintenues.
- Le cycle de vie des modèles fonctionne correctement.
- Le registre soit lisible et documenté.
- Les erreurs de configuration soient explicites.
- L'ajout futur d'un moteur différent ne nécessite pas de refonte générale.
- Les tests pertinents soient réussis ou que leurs limites soient clairement signalées.
- Le code soit propre, documenté et correctement aéré.
- Les fichiers réellement obsolètes aient été supprimés prudemment.
- Les documents de référence soient cohérents avec le résultat.

Ce qui est reporté à l'étape 12 ou aux étapes ultérieures ne doit pas retarder inutilement l'étape 11.

---

# 14. Rapport final obligatoire

Fournis uniquement à la fin un rapport complet de clôture.

## Verdict

Si tous les critères essentiels sont validés, indique exactement :

```text
ETAPE_11_REUSSIE
```

Sinon :

```text
ETAPE_11_PARTIELLE
```

ou :

```text
ETAPE_11_BLOQUEE
```

Ne déclare pas la réussite si les critères essentiels ne sont pas atteints.

## 11A → 11G

Fournis un tableau :

```text
Sous-étape | Statut | Modifications | Tests
```

## Architecture

Explique :

- L'architecture initiale.
- Les dépendances identifiées.
- Les composants conservés.
- Les composants adaptés.
- Les composants supprimés.
- L'architecture finale.

## Registre des modèles

Indique :

- Son emplacement.
- Son fonctionnement.
- Les modèles actuels.
- Les associations profil/modèle.
- Les règles de validation.
- La méthode de modification.

## Moteurs d'inférence

Explique :

- Comment llama.cpp est maintenant intégré.
- Ce qui a été découplé.
- Comment un autre moteur pourrait être ajouté ultérieurement.
- Ce qui n'a volontairement pas été développé.

## Profils

Valide séparément :

- Général.
- Programmation.
- Contrats des profils.
- Permissions.
- Mémoire et conversations.
- Commutation.

## OpenHands

Indique :

- Les modifications éventuelles.
- Les mécanismes préservés.
- Les tests effectués.
- Les limitations constatées.

## Qualité du code

Précise :

- Les fichiers documentés.
- Les commentaires et docstrings ajoutés.
- Les améliorations de lisibilité.
- Les refactorisations réellement nécessaires.
- Les fichiers supprimés, avec justification.
- Les éléments conservés faute de preuve suffisante de leur inutilité.

## Tests finaux

Donne les résultats exacts pour :

- Backend.
- Frontend.
- Build.
- Configuration.
- Registre.
- Général.
- Programmation.
- OpenHands.
- Sécurité.
- Commutation.
- Non-régression.
- `git diff --check`.

Distingue les tests automatisés des véritables tests d'intégration.

Indique les tests non exécutés.

## Questions et problèmes

Signale explicitement :

- Les problèmes rencontrés.
- Les problèmes corrigés.
- Les problèmes non corrigés.
- Les limitations restantes.
- Les risques éventuels.
- Les décisions nécessitant mon avis.
- Les questions auxquelles je dois répondre.

S'il n'y a aucune question, indique-le clairement.

## Étape 12

Mentionne uniquement les points architecturaux utiles à la future page Paramètres.

Ne commence pas cette étape.

## Git

Fournis :

- La liste des fichiers modifiés.
- La liste des fichiers créés.
- La liste des fichiers supprimés.
- Le résultat de `git status`.
- Le résultat de `git diff --check`.
- La confirmation qu'aucun commit ni push n'a été effectué.

## État final

Précise :

- L'état des processus.
- L'état des modèles.
- L'état des services de test.
- L'état d'OpenHands.
- L'intégrité des données utilisateur.
- Les vérifications restant éventuellement à faire.

Après ce rapport, **ARRÊTE-TOI**.

Attends ma validation manuelle avant toute nouvelle étape.

---

# 15. Consigne finale

Je souhaite une architecture indépendante des modèles, mais pas une plateforme artificiellement compliquée.

**Réutilise au maximum l'architecture existante et modifie seulement ce qui est réellement nécessaire.**

La priorité est d'obtenir :

```text
Léa indépendante des modèles

+

Configuration centrale simple

+

Qwen actuels toujours fonctionnels

+

OpenHands préservé

+

Code propre, lisible et bien commenté

+

Tests sérieux

+

Aucune régression

+

Rapport final vérifiable
```

Ne cherche pas à ajouter des capacités non demandées.

Ne prétends jamais qu'une modification ou un test a réussi sans preuve.

Lorsque l'étape est réellement terminée, fournis le rapport final puis attends ma validation.