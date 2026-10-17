# Prompt Codex — Étape 13 finale

## Programmation avancée de Léa

Tu dois réaliser **uniquement l'étape 13**, de **13A à 13L**, dans :

```text
L:\Projet_Lea
```

Les étapes 10, 11 et 12 ont été développées et validées manuellement par l'utilisateur.

Tu connais déjà Projet Léa, son architecture et notre historique. Ne repars pas de zéro.

L'étape 10 a établi le profil Programmation avec OpenHands, les checkpoints, la validation, l'acceptation et le rollback.

L'étape 11 a rendu l'architecture indépendante des modèles.

L'étape 12 a ajouté un centre de paramètres fonctionnel avec préférences persistantes.

Nous voulons maintenant améliorer la fiabilité, l'intégration locale et la gestion opérationnelle du profil Programmation.

**Objectif principal :**

> Rendre le profil Programmation de Léa plus autonome, plus robuste et mieux intégré à son environnement Windows local, sans affaiblir les protections existantes et sans transformer Léa en infrastructure disproportionnée.

Les axes retenus sont :

- Fiabilité de l'agent et gestion des erreurs.
- Détection et récupération après interruption.
- Surveillance légère des ressources.
- Avertissements et seuils critiques.
- Petit diagramme RAM/CPU/VRAM facultatif dans l'interface.
- Automatisation Docker Desktop/OpenHands si elle est fiable.
- Intégration Windows limitée et sécurisée.
- Automatisation Edge exclusivement locale.
- Maintenance prudente des ressources Docker.

L'objectif n'est pas d'obtenir une autonomie totale sur Windows ni d'accorder des permissions générales au modèle.

Toute nouvelle fonctionnalité doit réellement fonctionner, être testée et rester compatible avec les ressources de l'ordinateur actuel.

---

# 1. Règles générales

Travaille de manière autonome, méthodique et rigoureuse.

**Avant toute modification**, lis obligatoirement :

- `AGENTS.md`
- `README.md`
- `TODO.md`
- `CHANGELOG.md`
- `docs/DECISIONS.md`, s'il existe
- les éventuelles instructions supplémentaires du dépôt ;
- le registre des modèles/profils et son adaptateur actuel ;
- les composants backend du profil Programmation ;
- les modules OpenHands ;
- les composants de validation, checkpoint, acceptation et rollback ;
- les gestionnaires de processus et scripts PowerShell ;
- les composants frontend du profil Programmation ;
- le centre de paramètres de l'étape 12 ;
- les tests et scénarios Edge déjà présents ;
- les fichiers existants de gestion de ressources, si disponibles.

Lis intégralement les documents de référence pertinents.

Puis exécute :

```text
git status
git diff --check
git log -1 --oneline
```

Ne suppose pas qu'un commit récent a été effectué sans le vérifier.

Si des modifications locales inattendues sont présentes, protège-les et signale-les avant de toucher aux fichiers concernés.

## Interdictions générales

- Aucun commit.
- Aucun push.
- Aucun rebase.
- Aucun reset destructif.
- Aucun `git clean`.
- Aucune modification de l'historique Git.
- Aucun effacement de données utilisateur.
- Aucune suppression de checkpoints persistants.
- Aucun téléchargement de nouveau modèle.
- Aucune intégration GLM/Colibrì.
- Aucune réécriture d'OpenHands.
- Aucune modification du modèle Programmation actuel.
- Aucune nouvelle boucle agentique maison.
- Aucune refonte visuelle générale.
- Aucun outil Web public.
- Aucun accès Windows arbitraire accordé à l'agent.
- Aucune réduction des protections existantes.

Réutilise les mécanismes validés aux étapes précédentes.

**Ne transforme pas cette étape en chantier d'infrastructure générale.**

---

# 2. Architecture recherchée

Léa reste l'orchestrateur.

OpenHands reste le moteur agentique du profil Programmation.

Le modèle actuellement sélectionné reste le cerveau local.

L'architecture conceptuelle est :

```text
                         LÉA
                          │
                 Profil Programmation
                          │
          ┌───────────────┼────────────────┐
          │               │                │
       Modèle IA      Supervision       Paramètres
          │               │                │
          └───────────────┼────────────────┘
                          │
                    Orchestration
                          │
                      OpenHands
                          │
                Projet IA_WORKSPACE
                          │
                Outils déjà autorisés
                          │
                 Tests et validation
                          │
                  Accept / Rollback
```

Les nouveaux services de surveillance, d'automatisation locale et de gestion des ressources doivent s'intégrer à cette structure.

Ils ne doivent pas contourner les permissions existantes.

## Principes obligatoires

- Un agent ne doit pas obtenir davantage de permissions simplement parce qu'un outil a été ajouté.
- Les données d'une tâche restent rattachées à son projet autorisé.
- Une tâche active conserve son modèle, ses outils et ses permissions.
- Une interruption ne doit pas produire une fausse réussite.
- La surveillance ne doit pas arrêter arbitrairement des processus.
- L'automatisation Windows doit rester limitée aux opérations explicitement autorisées.
- Edge ne doit jamais devenir un navigateur Internet pour l'agent à cette étape.
- Les paramètres doivent passer par le centre de paramètres existant.
- Les fonctionnalités lourdes ou facultatives ne doivent pas ralentir inutilement le profil Général.

---

# 3. Ce qui est explicitement hors périmètre

Ne réalise PAS :

- Un nouveau profil IA.
- Un nouveau moteur d'inférence.
- Un nouveau modèle de programmation.
- Le fine-tuning.
- Une nouvelle mémoire avancée.
- Le RAG.
- La Web Gateway.
- Des recherches Internet autonomes.
- L'automatisation de sites publics.
- L'automatisation de comptes personnels.
- Un navigateur distant ou cloud.
- La génération d'images.
- La reconnaissance vocale.
- La synthèse vocale.
- Un système multi-agents général.
- Une refonte complète de l'interface.
- Un système de permissions administrateur Windows pour l'IA.
- Un service permanent supplémentaire sans justification.

**L'automatisation Edge est exclusivement locale.**

Elle doit servir aux applications et interfaces de développement locales, pas à la navigation Internet.

Aucune exception implicite à cette règle.

---

# 4. Barrières strictes

Ordre prévu :

```text
13A — Audit, état initial et périmètre réel
13B — Fiabilité de l'agent et gestion des échecs
13C — Interruption et récupération après plantage
13D — Surveillance légère des ressources
13E — Alertes et diagramme facultatif
13F — Automatisation Docker/OpenHands
13G — Automatisation Edge strictement locale
13H — Intégration Windows limitée et sécurisée
13I — Maintenance prudente de Docker
13J — Validation réelle et non-régression
13K — Commentaires, nettoyage et documentation
13L — Clôture finale
```

Après chaque sous-étape :

1. Exécute les tests ciblés.
2. Corrige les problèmes.
3. Relance les tests concernés.
4. Vérifie les effets sur les autres composants.
5. Documente les limites découvertes.
6. Ne commence la suite que lorsque les contrôles nécessaires sont satisfaits.

**13F, 13G et 13H comportent des conditions de faisabilité et de sécurité.**

Si leur réalisation impose une architecture disproportionnée, des permissions excessives ou une isolation réseau impossible à démontrer, ne force pas leur intégration.

Dans ce cas, présente le blocage, les solutions envisageables et les compromis. Demande mon accord avant une modification architecturale majeure.

Ne déclare pas une capacité disponible lorsqu'elle a été uniquement conçue ou simulée.

---

# 5. 13A — Audit et préparation

Avant de développer, examine l'état réel du profil Programmation.

## Vérifications

Inspecte notamment :

- Le cycle de démarrage et d'arrêt.
- La disponibilité de Docker Desktop.
- Le lancement et la connexion d'OpenHands.
- Les processus llama.cpp.
- Les composants de supervision éventuellement existants.
- Les limites de ressources.
- Les mécanismes d'annulation.
- La persistance des runs.
- La gestion des erreurs.
- Les timeouts existants.
- Les protections contre les boucles.
- La gestion des checkpoints.
- Les cas de plantage et leur traitement.
- Les scénarios de test existants.
- L'automatisation Edge déjà utilisée pour les tests de l'étape 12.
- Le centre de paramètres et son mécanisme de persistance.

## Éviter les doublons

Pour les composants concernés, classe les besoins :

```text
KEEP
IMPROVE
ADD
REMOVE
```

- `KEEP` : mécanisme existant satisfaisant.
- `IMPROVE` : amélioration ciblée.
- `ADD` : capacité réellement absente.
- `REMOVE` : code confirmé obsolète.

N'ajoute pas une deuxième surveillance de processus si la première remplit déjà les besoins.

Ne reconstruis pas une gestion de sessions OpenHands existante.

## Résultat attendu

Présente brièvement :

- Les mécanismes existants.
- Les problèmes ou lacunes réellement identifiés.
- Les fonctionnalités déjà couvertes.
- Les modifications nécessaires.
- Les fonctionnalités facultatives qui pourraient être techniquement difficiles.
- Ton plan d'implémentation.

Si une fonctionnalité est déjà suffisamment couverte, préserve-la plutôt que de la refaire.

---

# 6. 13B — Fiabilité du profil Programmation

L'objectif est d'améliorer la fiabilité des tâches sans modifier artificiellement le raisonnement du modèle.

## Points à examiner

- Erreurs d'outils.
- Réponses invalides d'OpenHands.
- Boucles répétitives.
- Timeouts.
- Runs bloqués.
- Annulations incomplètes.
- États incohérents.
- Échecs de validation.
- Perte de communication avec un service.
- Affichage d'une réussite sans preuve suffisante.

## Règles

Préserve le fonctionnement actuel de :

- `completed`
- `validated`
- `failed`
- `cancelled`
- acceptation ;
- rollback ;
- checkpoints ;
- preuves de validation.

Ne modifie pas ces états sans nécessité et sans migration cohérente de leurs consommateurs.

## Améliorations

Privilégie :

- Une classification claire des erreurs.
- Une meilleure distinction entre erreur du modèle et erreur de l'infrastructure.
- Des messages compréhensibles dans le frontend.
- Une détection correcte des processus ou services indisponibles.
- Une gestion des timeouts adaptée.
- Une annulation réellement confirmée.
- Des journaux techniques proportionnés.

Ne crée pas de nouvelles heuristiques compliquées destinées à forcer Qwen2.5-Coder à réussir des tâches qu'il ne maîtrise pas.

N'ajoute pas de retry automatique aveugle sur des opérations susceptibles de modifier des fichiers.

Un échec correctement détecté est préférable à une fausse réussite.

## Tests 13B

Teste :

- Erreur d'outil.
- Erreur de modèle.
- Erreur de connexion.
- Timeout.
- Annulation.
- Boucle détectée.
- Échec de validation.
- Confirmation d'état final.
- Préservation du checkpoint.
- Rollback.
- Absence de fausse réussite.

Ne répète pas inutilement tous les benchmarks difficiles historiques.

---

# 7. 13C — Interruption et récupération après plantage

Je veux que Léa réagisse correctement lorsqu'un composant tombe en panne pendant une tâche.

L'objectif n'est pas de reprendre magiquement une tâche interrompue à l'endroit exact où elle s'est arrêtée.

## Scénarios à couvrir

- Backend interrompu.
- Agent Server indisponible.
- Processus modèle arrêté.
- Déconnexion pendant un run.
- Redémarrage de Léa après une interruption.
- Run enregistré comme actif alors qu'aucun processus correspondant n'existe.
- Checkpoint conservé après échec.

## Comportement attendu

Après une interruption, Léa doit pouvoir :

1. Identifier qu'une tâche était en cours.
2. Vérifier si elle fonctionne réellement encore.
3. Éviter de déclarer une tâche terminée sans preuve.
4. Signaler son état exact ou incertain.
5. Préserver le checkpoint.
6. Permettre une récupération sûre lorsque les mécanismes existants le permettent.
7. Permettre un rollback lorsque c'est approprié.
8. Éviter de relancer automatiquement des modifications de fichiers non idempotentes.

## Limites

Ne reconstruis pas un système complet de reprise distribuée.

Ne crée pas une nouvelle base de persistance parallèle.

Ne relance pas automatiquement une tâche à risque après crash si ses effets précédents sont incertains.

Ne restaure pas silencieusement des fichiers pouvant avoir été modifiés extérieurement.

## Tests 13C

Teste des pannes contrôlées sur un projet temporaire autorisé.

Vérifie :

- L'état persistant.
- Les processus encore présents.
- La reprise de visibilité du run.
- Les erreurs affichées.
- La conservation des checkpoints.
- La gestion des conflits.
- L'absence de double exécution.
- L'absence de perte de données.

Ne simule pas une coupure destructrice sur un véritable projet utilisateur.

---

# 8. 13D — Surveillance légère des ressources

Nous voulons une surveillance discrète du fonctionnement de Léa pendant le profil Programmation.

**Elle doit fonctionner en arrière-plan sans consommer beaucoup de ressources.**

Elle ne doit pas ajouter un gros service de monitoring.

## Ressources à surveiller

Minimum souhaité :

```text
RAM système
CPU système
VRAM NVIDIA, si disponible
État du processus du modèle
État du backend concerné
État Docker/OpenHands
```

La surveillance doit distinguer :

- Les ressources réellement disponibles.
- Les ressources utilisées.
- Les ressources indisponibles à mesurer.
- Les processus en fonctionnement.
- Les processus arrêtés.
- Les situations critiques.

## RAM

Sous Windows, distingue correctement mémoire disponible et mémoire simplement libre.

Ne déclenche pas des alertes uniquement parce que Windows utilise sa mémoire comme cache.

## CPU

Un pic d'utilisation CPU n'est pas nécessairement une erreur.

Une surcharge doit être évaluée sur une durée suffisante.

## GPU / VRAM

Utilise les mécanismes NVIDIA existants si disponibles et suffisamment légers.

Si la mesure GPU est indisponible, affiche un état inconnu ou indisponible.

Ne présente pas une valeur fictive ou zéro comme une mesure réelle.

## Fréquence

Je recommande initialement :

- Ressources système : environ toutes les 10 secondes.
- GPU et Docker : fréquence éventuellement plus faible selon le coût réel.
- État des processus : fréquence proportionnée aux besoins.

Mesure le coût du mécanisme retenu.

Évite de lancer continuellement de nouveaux processus PowerShell ou `nvidia-smi` si cela provoque une surcharge inutile.

Réutilise les compteurs Windows, les bibliothèques ou les outils déjà disponibles lorsqu'ils sont adaptés.

## Durée de vie

La surveillance doit être principalement active lorsque Programmation fonctionne ou démarre.

Elle doit libérer ses ressources lorsque la session se termine.

Ne lance pas plusieurs boucles de supervision concurrentes.

Évite les threads ou tâches périodiques orphelins.

## Stockage

Aucune base de données de télémétrie permanente n'est demandée.

Une petite mémoire tampon en RAM peut être utilisée si nécessaire pour détecter les tendances.

Évite d'enregistrer chaque mesure dans SQLite.

## Tests 13D

Teste :

- Démarrage de la surveillance.
- Arrêt propre.
- Absence de double boucle.
- Mesures cohérentes.
- Indisponibilité de NVIDIA.
- Indisponibilité de Docker.
- Valeurs temporairement invalides.
- Coût CPU/RAM du mécanisme.
- Absence d'impact notable sur la génération et OpenHands.

---

# 9. 13E — Alertes et diagramme facultatif

Nous voulons des avertissements lorsque Léa rencontre un problème ou un niveau de ressources critique.

Nous voulons également un petit diagramme que l'utilisateur pourra afficher depuis la page Paramètres.

## Trois états

```text
NORMAL
WARNING
CRITICAL
```

### NORMAL

Ressources suffisantes.

Aucun avertissement nécessaire.

### WARNING

Exemples :

- RAM disponible anormalement faible.
- Surcharge persistante.
- Ressources approchant une limite.
- Service présentant des anomalies non fatales.

### CRITICAL

Exemples :

- Ressources très proches de l'épuisement.
- Processus indispensable arrêté pendant un run.
- Service requis devenu indisponible.
- Risque sérieux pour la stabilité de la session.

## Seuils

Ne choisis pas des seuils arbitraires uniquement à partir de pourcentages.

Examine les ressources réellement disponibles sur ce PC et les consommations du profil Programmation.

Utilise des seuils raisonnables, expliqués et testables.

Prévois une hystérésis ou un mécanisme équivalent afin d'éviter les alertes qui apparaissent et disparaissent à chaque mesure.

Évite les notifications répétées pour la même anomalie.

Un seuil critique doit produire une alerte visible et compréhensible.

**La surveillance ne doit pas interrompre automatiquement un run, tuer Qwen ou fermer Docker en réaction à un seuil.**

## Intégration dans le centre de paramètres

Ajoute une préférence :

```text
Afficher le diagramme des ressources
```

Valeur par défaut :

```text
false
```

Lorsque cette option est désactivée :

- Aucun diagramme n'est affiché.
- La surveillance peut continuer en arrière-plan pendant Programmation.
- Les avertissements critiques restent visibles.

Lorsque cette option est activée :

- Un petit panneau apparaît en bas de la page principale de Léa.
- Il contient les mesures RAM, CPU et VRAM disponibles.
- Les valeurs sont actualisées périodiquement.
- La présentation reste discrète et lisible.
- Le panneau ne gêne pas la conversation.

## Diagramme attendu

Présentation conceptuelle :

```text
Ressources

RAM    19 / 32 Go    [████████░░░░]
CPU    35 %          [████░░░░░░░░]
VRAM   4 / 6 Go      [████████░░░░]
```

Ces valeurs sont seulement des exemples.

Le diagramme final doit afficher de vraies mesures.

Ne construis pas un tableau de bord complexe.

Une présentation simple avec trois barres de progression et quelques valeurs suffit.

## Persistance

La préférence d'affichage doit être enregistrée avec le mécanisme de l'étape 12.

Elle doit être conservée après redémarrage.

## Tests 13E

Teste :

- Diagramme masqué par défaut.
- Activation.
- Désactivation.
- Sauvegarde.
- Persistance.
- Affichage des mesures réelles.
- Mesure indisponible.
- Avertissement en mode masqué.
- Alerte critique.
- Absence de spam.
- Absence d'arrêt automatique d'une tâche.

---

# 10. 13F — Automatisation Docker Desktop / OpenHands

Cette amélioration est **souhaitée, mais facultative** si sa réalisation fiable impose une complexité disproportionnée.

Le fonctionnement actuel de Léa doit rester utilisable.

## Fonctionnement souhaité

Lorsque l'utilisateur sélectionne Programmation puis clique sur Démarrer :

```text
Profil Programmation
        ↓
Démarrer
        ↓
Vérifier Docker Desktop
        ↓
Démarrer Docker si nécessaire
        ↓
Préparer OpenHands
        ↓
Démarrer le modèle
        ↓
Vérifier readiness
        ↓
Profil prêt
```

L'ordre technique exact doit être adapté aux dépendances réelles du projet.

Ne déclare pas Programmation prêt tant que les composants indispensables ne le sont pas.

## Arrêt souhaité

Lorsque l'utilisateur clique sur Arrêter :

```text
Arrêter la session active
        ↓
Terminer les runs concernés
        ↓
Arrêter OpenHands proprement
        ↓
Arrêter le modèle
        ↓
Libérer les ressources
        ↓
Fermer Docker Desktop si autorisé
```

L'utilisateur n'a actuellement aucun autre projet Docker et souhaite pouvoir fermer complètement Docker Desktop lorsqu'il arrête Léa.

Cependant, ce comportement doit être configurable et sûr.

## Paramètres à ajouter si l'automatisation est implémentée

Dans le Centre de paramètres :

```text
Démarrer Docker automatiquement
Fermer Docker Desktop à l'arrêt
```

Ces deux options doivent pouvoir être activées ou désactivées indépendamment, dans la mesure où leur comportement est cohérent.

Leur valeur initiale doit être sûre, documentée et ne doit pas surprendre l'utilisateur.

Il doit être possible de désactiver la fermeture complète de Docker Desktop si l'utilisateur ajoute d'autres projets Docker dans le futur.

N'affiche pas un interrupteur qui ne fait rien.

## Sécurité

- Ne supprime aucun volume Docker persistant.
- Ne supprime aucune image nécessaire.
- Ne supprime pas de données OpenHands.
- Ne termine pas arbitrairement les projets Docker sans rapport avec Léa.
- Vérifie les runs actifs avant l'arrêt.
- Conserve les checkpoints.
- Gère les échecs de démarrage.
- Gère les timeouts.
- Évite les doubles démarrages.
- Ne déclare pas Docker arrêté avant confirmation.
- Ne force pas la fermeture de Docker Desktop si cela risque d'interrompre un travail non lié à Léa.

Si la fermeture complète de Docker est demandée alors que des conteneurs non liés à Léa sont actifs, adopte un comportement prudent et explicite plutôt qu'un arrêt silencieux.

## Fonctionnement manuel

Si l'automatisation échoue ou est désactivée :

- Le démarrage manuel doit rester possible.
- Léa doit afficher une erreur utile.
- Les données ne doivent pas être compromises.
- Le frontend ne doit pas rester indéfiniment en chargement.

## Tests 13F

Si l'automatisation est réalisée, teste :

- Docker déjà ouvert.
- Docker fermé.
- Démarrage automatique activé.
- Démarrage automatique désactivé.
- Fermeture complète activée.
- Fermeture complète désactivée.
- Double clic sur Démarrer.
- Démarrage en échec.
- Arrêt en échec.
- Run actif.
- Arrêt propre.
- Conservation des données.
- Aucun conteneur utilisateur étranger arrêté.

Si cette fonctionnalité ne peut pas être livrée proprement, conserve le comportement existant et explique précisément pourquoi.

Ne bloque pas l'ensemble de l'étape pour une automatisation facultative impossible à sécuriser raisonnablement.

---

# 11. 13G — Automatisation Edge exclusivement locale

Cette fonctionnalité doit permettre à Léa d'utiliser Edge pour vérifier ou tester des applications locales.

**Aucune navigation Internet n'est autorisée.**

C'est une exigence stricte de l'utilisateur.

## Usages autorisés

Exemples :

- Ouvrir une application React locale.
- Tester les boutons d'une interface.
- Vérifier un formulaire.
- Vérifier une page servie par Vite.
- Tester une application locale créée dans un projet autorisé.
- Capturer des erreurs d'interface.
- Observer le résultat d'une action utilisateur simulée.
- Effectuer des tests de navigation locaux.

Les applications visées doivent être des applications de développement autorisées ou l'interface locale de Léa.

## Usages interdits

- Recherches Google, Bing ou autres moteurs.
- Navigation sur des sites publics.
- Connexion à des comptes Internet.
- Automatisation de réseaux sociaux.
- Lecture des sessions personnelles Edge.
- Utilisation du profil personnel du navigateur.
- Téléchargements arbitraires.
- Ouverture de pages externes.
- Utilisation du navigateur comme passerelle Internet.
- Contournement des restrictions de réseau via redirections ou ressources intégrées.

Le Web public sera traité ultérieurement dans l'étape Web Gateway, avec ses propres règles.

## Isolation obligatoire

Étudie les mécanismes Edge/Chromium déjà utilisés dans les tests existants.

Privilégie la réutilisation de ces mécanismes.

L'automatisation doit utiliser un profil de navigateur isolé et temporaire, sans cookies, sessions ni identifiants personnels.

Restreins les destinations accessibles aux adresses locales explicitement autorisées, idéalement aux services de développement sur interface loopback.

Ne considère pas une URL autorisée au départ comme suffisante : prends également en compte les redirections et les requêtes secondaires.

Les sous-ressources, requêtes réseau, WebSockets et autres canaux pertinents doivent être étudiés.

Une page locale pouvant contenir du JavaScript arbitraire, une simple vérification de l'URL initiale n'est pas une garantie d'isolation.

**Ne prétends pas qu'Edge est isolé d'Internet sans validation technique du mécanisme retenu.**

Si tu ne peux pas garantir raisonnablement cette restriction avec l'architecture existante, ne livre pas une automatisation réseau non maîtrisée.

Présente les limites et les options possibles, puis demande une décision.

## Accès aux fichiers

L'automatisation Edge ne doit pas élargir les droits de l'agent aux fichiers de l'ordinateur.

Ne donne pas à OpenHands un accès direct illimité au profil Windows, au disque système ou au dépôt principal de Léa.

Ne transforme pas un outil de test navigateur en outil général d'exécution de commandes.

## Tests 13G

Utilise une application locale temporaire.

Teste :

- Ouverture d'une page locale autorisée.
- Clic sur un bouton.
- Saisie dans un formulaire.
- Lecture d'un résultat.
- Fermeture du navigateur.
- Nettoyage du profil temporaire.
- Refus d'une URL externe.
- Refus d'une redirection externe.
- Refus ou interception des ressources externes.
- Refus d'un accès à un fichier local non autorisé.
- Absence de cookies/sessions personnels.
- Respect du workspace autorisé.
- Absence de connexions Internet provenant des tests d'automatisation, dans la mesure vérifiable.

N'utilise pas de véritable site Internet comme cible des tests.

Ne considère pas une simulation seule comme preuve d'isolation complète.

---

# 12. 13H — Intégration Windows limitée et sécurisée

Nous voulons examiner la possibilité d'améliorer certaines interactions locales entre le profil Programmation et Windows.

Cette capacité est intéressante, mais elle présente davantage de risques.

## Première tâche

Identifie des besoins réels que les mécanismes actuels ne couvrent pas.

Par exemple :

- Vérifier l'état d'un processus autorisé.
- Lire des informations système nécessaires au fonctionnement.
- Contrôler l'état d'un service propre à Léa.
- Faciliter les tests locaux.
- Recueillir des diagnostics ciblés.

Ne suppose pas que tous ces besoins nécessitent un nouveau pont Windows.

## Principe de sécurité

**Aucun terminal Windows arbitraire ne doit être exposé à OpenHands.**

Ne crée pas un endpoint permettant à l'agent d'exécuter librement du PowerShell sur le système hôte.

Ne crée pas d'accès administrateur général.

Ne donne pas accès à tous les fichiers de Windows.

Si un pont sécurisé est véritablement nécessaire, il doit être limité à des opérations explicitement autorisées et validées côté hôte.

Les chemins, actions et arguments doivent être contrôlés.

Les opérations sensibles doivent être refusées ou demander une autorisation appropriée.

Les journaux doivent permettre d'identifier les actions réellement exécutées.

## Périmètre

Privilégie les opérations en lecture seule et les contrôles des services appartenant à Léa.

N'ajoute pas des capacités Windows simplement parce qu'elles pourraient être utiles un jour.

Si les outils existants répondent déjà aux besoins, conserve-les.

## Tests 13H

Si un composant est créé :

- Opération autorisée.
- Opération interdite.
- Arguments invalides.
- Chemin non autorisé.
- Tentative de traversée de répertoires.
- Commande arbitraire refusée.
- Erreur Windows.
- Journalisation correcte.
- Absence d'élévation de privilèges.
- Absence d'accès non autorisé au dépôt principal et aux données personnelles.

Si aucune nouvelle intégration n'est justifiée, documente l'audit et conserve l'architecture actuelle.

---

# 13. 13I — Maintenance prudente de Docker

Nous voulons éviter l'accumulation inutile de ressources temporaires sans mettre en danger les données.

## Objectifs

Vérifier notamment :

- Les conteneurs temporaires créés pour des tests.
- Les sessions OpenHands terminées.
- Les processus orphelins appartenant à Léa.
- Les ressources créées exclusivement pour un run.
- Les fichiers temporaires confirmés inutiles.
- Les montages et volumes nécessaires.

## Interdictions

Ne lance pas automatiquement :

```text
docker system prune
docker volume prune
docker image prune
```

Ne supprime pas arbitrairement des images ou conteneurs inconnus.

Ne purge pas les volumes OpenHands persistants.

Ne supprime pas les checkpoints ni les journaux utiles.

Ne nettoie pas les ressources d'un run encore actif.

## Gestion souhaitée

- Identifier les ressources réellement détenues par Léa.
- Déterminer leur état.
- Distinguer ressources persistantes et temporaires.
- Nettoyer seulement ce qui appartient à une opération terminée et dont l'inutilité est confirmée.
- Éviter les nettoyages concurrents.
- Éviter les suppressions à partir d'identifiants insuffisamment vérifiés.

Ne crée pas un grand système de maintenance autonome si les mécanismes existants suffisent.

## Tests 13I

Teste :

- Conteneur appartenant à une session terminée.
- Ressource encore active.
- Volume persistant.
- Ressource inconnue.
- Opération de nettoyage déjà exécutée.
- Erreur Docker.
- Répétition sans double suppression.
- Préservation des données.
- Absence d'impact sur les projets externes.

---

# 14. 13J — Validation réelle et non-régression

Cette phase doit démontrer que les améliorations fonctionnent réellement.

## Test 1 — Général

Valide :

- Démarrage.
- Conversation.
- Mémoire.
- Historique.
- Paramètres Low/High.
- Arrêt.
- Absence de ralentissement notable lié aux nouveaux services de Programmation.

## Test 2 — Programmation

Valide :

- Démarrage.
- Readiness.
- Projet autorisé.
- Exécution d'une tâche simple.
- OpenHands.
- Résultat.
- Validation.
- Checkpoint.
- Acceptation ou rollback.
- Arrêt.

## Test 3 — Surveillance

Valide :

- Mesures réelles.
- Coût raisonnable.
- Diagramme masqué par défaut.
- Activation dans Paramètres.
- Persistance.
- Alertes sans diagramme.
- Gestion des mesures indisponibles.
- Arrêt du mécanisme.

## Test 4 — Pannes contrôlées

Valide :

- Composant indisponible.
- Timeout.
- Run interrompu.
- Redémarrage.
- État conservé.
- Absence de fausse réussite.
- Checkpoint récupérable.

## Test 5 — Docker

Si l'automatisation a été livrée :

- Démarrage.
- Arrêt.
- Paramètres.
- Readiness.
- Gestion des erreurs.
- Préservation des volumes.
- Aucun arrêt intempestif d'autres projets.

Sinon, valide le fonctionnement manuel historique.

## Test 6 — Edge local

Si l'automatisation a été livrée :

- Scénario local réel.
- Actions navigateur.
- Isolation du profil.
- Blocage des destinations externes.
- Absence d'accès non autorisé aux fichiers.
- Nettoyage.

Sinon, indique exactement quelle barrière a empêché sa livraison.

## Test 7 — Sécurité

Vérifie :

- Confinement workspace.
- Refus des chemins interdits.
- Refus des actions hôte non autorisées.
- Permissions des profils.
- Checkpoints.
- Rollback.
- Pas de contournement par Edge.
- Pas de Web public.
- Pas de secrets exposés.
- Pas de suppression Docker dangereuse.

## Test 8 — Non-régression

Relance les suites pertinentes :

- Backend.
- Frontend.
- Build React/TypeScript.
- Configuration des modèles.
- Profils.
- Mémoire.
- Conversations.
- Paramètres.
- OpenHands.
- Persistance des runs.
- Checkpoints.
- Acceptation.
- Rollback.
- Gestion des processus.
- Scripts PowerShell.
- Sécurité.

Puis :

```text
git diff --check
```

Distingue :

- Tests unitaires.
- Tests d'intégration.
- Tests simulés.
- Tests réellement effectués avec Qwen.
- Tests réellement effectués avec OpenHands.
- Tests Edge réels.
- Tests non exécutés.

N'annonce pas une réussite sans preuve.

---

# 15. 13K — Commentaires, qualité, nettoyage et documentation

Conserve les exigences de qualité déjà établies dans les étapes précédentes.

## Commentaires

Dans chaque fichier source créé ou substantiellement modifié, chaque fonction, méthode ou callback significatif doit posséder au moins un commentaire ou une docstring réellement utile.

Commente particulièrement :

- La supervision des ressources.
- Les seuils et avertissements.
- Les décisions d'état.
- Les mécanismes de récupération.
- Les timeouts.
- Les opérations Docker.
- Les restrictions réseau Edge.
- Les validations des chemins.
- Le cycle de vie des processus.
- L'intégration Windows.
- Les mécanismes de sécurité.
- Les opérations susceptibles de modifier des fichiers.

Les commentaires doivent être :

- Techniques.
- Sérieux.
- Précis.
- Professionnels.
- Sans emojis.
- Sans répétitions artificielles.
- Cohérents avec le code réel.

Un futur développeur doit comprendre rapidement le rôle d'une fonction et les raisons d'une opération complexe.

## Code aéré

Je veux :

- Des fonctions clairement séparées.
- Des lignes vides entre les blocs logiques.
- Des noms explicites.
- Des expressions longues réparties sur plusieurs lignes.
- Une indentation cohérente.
- Des composants lisibles.
- Des responsabilités clairement séparées.
- Des modules de taille raisonnable.
- Des commentaires correctement placés.

Ne compacte pas artificiellement le code.

Ne reformate pas des fichiers sans rapport avec cette étape.

## Nettoyage

Recherche :

- Imports inutilisés.
- Fonctions obsolètes.
- Variables inutilisées.
- Doublons.
- Anciens chemins de code devenus inutiles.
- Fichiers temporaires.
- Composants remplacés.
- Commentaires périmés.
- Ressources générées inutiles.

Classe les éléments concernés :

```text
KEEP
ADAPT
REMOVE
```

Ne supprime qu'après vérification des références et usages indirects.

Ne supprime jamais arbitrairement :

- Les données utilisateur.
- Les conversations.
- La mémoire.
- Les poids des modèles.
- Les checkpoints.
- Les journaux d'audit.
- Les volumes persistants.
- Le laboratoire GLM/Colibrì.
- Les configurations encore utilisées.

En cas de doute, conserve et signale.

## Documentation

Mets à jour les documents concernés :

- `README.md`
- `TODO.md`
- `CHANGELOG.md`
- `AGENTS.md`, si nécessaire
- `docs/DECISIONS.md`, s'il existe
- La documentation frontend/backend pertinente
- La documentation des scripts et outils concernés.

Documente :

- Les nouvelles capacités de Programmation.
- Le fonctionnement de la surveillance.
- Les métriques disponibles.
- Les seuils et leurs limites.
- Les avertissements.
- Le diagramme.
- Les nouveaux paramètres.
- L'automatisation Docker si implémentée.
- Le comportement d'arrêt.
- L'isolation Edge et ses limites réelles.
- Les opérations Windows éventuellement ajoutées.
- Les protections de sécurité.
- Les fonctionnalités reportées.

Ne change pas le reste de la roadmap.

L'étape 14 demeure consacrée aux entrées multimodales.

---

# 16. 13L — Clôture technique

À la fin :

1. Vérifie le fonctionnement final de Léa.
2. Relance les tests concernés après les derniers nettoyages.
3. Vérifie les documents.
4. Vérifie les fichiers Git.
5. Arrête proprement les composants lancés uniquement pour les tests.
6. Vérifie que les données persistantes sont intactes.
7. Fournis le rapport final.

## Nettoyage final

- Arrête les runs OpenHands de test.
- Arrête les modèles démarrés uniquement pour les tests.
- Arrête les processus de surveillance temporaires.
- Ferme les navigateurs Edge de test.
- Supprime uniquement les profils Edge temporaires identifiés.
- Arrête les serveurs locaux de test.
- Arrête les composants Docker lancés exclusivement pour les essais, en préservant les ressources persistantes.
- Ne ferme pas les services qui étaient déjà utilisés avant les essais.
- Préserve les modèles.
- Préserve les préférences.
- Préserve les conversations.
- Préserve la mémoire.
- Préserve les checkpoints.
- Préserve les données OpenHands.

Puis :

```text
git status
git diff --check
```

Aucun commit.

Aucun push.

Aucun fichier sensible ajouté intentionnellement au dépôt.

---

# 17. Critère final de réussite

L'étape 13 est techniquement réussie si :

> Le profil Programmation de Léa reste opérationnel et sécurisé, les erreurs et interruptions sont mieux gérées, la surveillance légère des ressources fonctionne réellement, les avertissements critiques sont fiables et le diagramme facultatif est accessible depuis le centre de paramètres sans ralentissement disproportionné.

Les intégrations supplémentaires doivent respecter leurs barrières respectives.

En particulier :

- Docker peut rester manuel si l'automatisation complète n'est pas réalisable proprement.
- Edge ne doit être considéré fonctionnel que si l'automatisation locale et ses restrictions sont réellement validées.
- Le pont Windows ne doit être ajouté que pour des besoins justifiés et avec des permissions strictes.
- La maintenance Docker ne doit jamais mettre en danger les données persistantes.

Un composant facultatif non réalisé ne doit pas être présenté comme terminé.

Ne sacrifie pas la sécurité pour afficher une fonctionnalité supplémentaire.

Ne sacrifie pas la stabilité pour optimiser quelques secondes.

Les fonctionnalités réellement livrées doivent être testées.

La fiabilité, la surveillance, la gestion des erreurs et la non-régression restent les priorités centrales.

---

# 18. Rapport final obligatoire

Fournis uniquement à la fin un rapport structuré.

## Verdict

Si tous les critères obligatoires sont atteints :

```text
ETAPE_13_REUSSIE
```

Sinon :

```text
ETAPE_13_PARTIELLE
```

ou :

```text
ETAPE_13_BLOQUEE
```

Une étape peut être réussie avec des intégrations facultatives reportées, à condition que cela soit clairement indiqué et que les objectifs obligatoires soient atteints.

## 13A → 13L

Fournis un tableau :

```text
Sous-étape | Statut | Modifications | Tests | Limitations
```

## Fiabilité

- Problèmes identifiés.
- Protections existantes conservées.
- Améliorations apportées.
- Gestion des erreurs.
- Tests de pannes.
- Limitations restantes.

## Récupération

- Comportement après interruption.
- États persistants.
- Gestion des runs incertains.
- Checkpoints.
- Rollback.
- Tests effectués.

## Surveillance des ressources

- Sources des mesures.
- Fréquence de collecte.
- Impact CPU/RAM.
- RAM disponible.
- CPU.
- VRAM.
- Processus surveillés.
- Seuils retenus et justification.
- Avertissements.
- Limitations matérielles.

## Interface des ressources

- Préférence d'affichage.
- Valeur par défaut.
- Emplacement du diagramme.
- Mesures affichées.
- Comportement lorsqu'une mesure est indisponible.
- Persistance.
- Tests frontend et réels.

## Docker/OpenHands

- Automatisation réalisée ou reportée.
- Fonctionnement du démarrage.
- Fonctionnement de l'arrêt.
- Gestion de Docker Desktop.
- Paramètres ajoutés.
- Échecs et solutions.
- Données préservées.

## Edge

- Architecture retenue.
- Cas d'usage locaux disponibles.
- Restrictions réseau effectives.
- Vérifications des redirections et ressources externes.
- Gestion du profil isolé.
- Tests réellement effectués.
- Limitations ou blocages.

Ne prétends pas garantir une isolation réseau si elle n'a pas été vérifiée.

## Windows

- Besoins réellement identifiés.
- Outils existants réutilisés.
- Éventuel composant ajouté.
- Permissions.
- Restrictions.
- Tests de sécurité.
- Fonctionnalités non réalisées.

## Maintenance

- Nettoyages ajoutés ou améliorés.
- Ressources concernées.
- Protections.
- Données conservées.
- Tests.

## Qualité du code

- Fichiers commentés.
- Docstrings ajoutées.
- Améliorations de lisibilité.
- Code obsolète supprimé.
- Fichiers supprimés, avec justification.
- Éléments conservés faute de preuve de leur inutilité.

## Tests finaux

Indique les résultats exacts :

- Backend.
- Frontend.
- Build.
- Général.
- Programmation.
- OpenHands.
- Surveillance.
- Alertes.
- Diagramme.
- Docker.
- Edge.
- Windows, si concerné.
- Sécurité.
- Checkpoints.
- Rollback.
- Persistance.
- `git diff --check`.

Distingue les tests simulés, réels et non exécutés.

## Problèmes et questions

Présente :

- Problèmes rencontrés.
- Problèmes corrigés.
- Problèmes non résolus.
- Composants facultatifs reportés.
- Risques résiduels.
- Décisions nécessitant mon avis.
- Questions éventuelles.

S'il n'y a aucune question, indique-le.

## Git

- Fichiers modifiés.
- Fichiers créés.
- Fichiers supprimés.
- `git status`.
- `git diff --check`.
- Confirmation qu'aucun commit/push n'a été effectué.
- Signalement des fichiers générés non ignorés qui pourraient être ajoutés par un `git add .`.

## État final

- Backend.
- Frontend.
- Qwen.
- OpenHands.
- Docker Desktop.
- Edge.
- Processus de surveillance.
- Ports de test.
- Données utilisateur.
- Checkpoints.
- Étape 14 non commencée.

Après le rapport, **ARRÊTE-TOI**.

Attends ma validation manuelle avant toute nouvelle étape.

---

# 19. Consigne finale

Je veux que Projet Léa progresse vers une application locale fiable, sécurisée et réellement fonctionnelle.

Je ne veux pas de fonctionnalités décoratives ou fictives.

Je ne veux pas d'une nouvelle infrastructure complexe simplement pour couvrir des besoins hypothétiques.

Je veux :

```text
Programmation plus fiable

+

Récupération sûre après les interruptions

+

Surveillance légère en arrière-plan

+

Alertes pertinentes

+

Diagramme RAM/CPU/VRAM masqué par défaut

+

Automatisation Docker si fiable

+

Automatisation Edge strictement locale

+

Permissions Windows contrôlées

+

Maintenance prudente

+

Code lisible, aéré et abondamment commenté

+

Tests réels

+

Aucune régression

+

Rapport final vérifiable
```

Privilégie les améliorations réellement utiles au projet.

Chaque nouvelle capacité doit être accompagnée des contrôles de sécurité correspondants.

**Lorsque l'étape 13 est terminée, fournis le rapport complet puis attends ma validation.**