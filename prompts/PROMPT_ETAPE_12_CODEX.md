# Prompt Codex — Étape 12 finale

## Centre de paramètres de Léa

Tu dois réaliser **uniquement l'étape 12**, de **12A à 12J**, dans :

```text
L:\Projet_Lea
```

L'étape 11 — Architecture indépendante des modèles — est terminée, testée manuellement et validée par l'utilisateur.

Le commit et le push de cette étape ont été effectués par l'utilisateur. Vérifie néanmoins l'état Git réel avant de travailler.

Tu connais déjà Projet Léa, son architecture et tout notre historique. Ne reprends pas le projet depuis le début.

Cette étape introduit une nouvelle fonctionnalité :

> Depuis l'interface de Léa, l'utilisateur doit pouvoir ouvrir une page Paramètres, consulter et modifier les réglages fonctionnels disponibles, sauvegarder ses choix et les retrouver après redémarrage.

Ce centre de paramètres doit être **indépendant de Qwen, de llama.cpp et des futurs modèles**.

Il sera enrichi au fur et à mesure des prochaines étapes, par exemple avec les réglages du microphone, de Docker Desktop, de la voix ou des futurs profils.

Pour l'instant, ne développe que les réglages réellement utilisables avec les fonctionnalités existantes.

L'objectif est volontairement simple :

**Une page Paramètres propre, fonctionnelle, persistante et facilement extensible, sans sur-ingénierie.**

---

# 1. Règles générales

Travaille de manière autonome, méthodique et rigoureuse.

Avant toute modification, lis obligatoirement :

- `AGENTS.md`
- `README.md`
- `TODO.md`
- `CHANGELOG.md`
- `docs/DECISIONS.md`, s'il existe
- les éventuelles instructions complémentaires du dépôt ;
- les composants frontend actuels ;
- les modules backend gérant les profils ;
- le registre central `config/models.json` ;
- les modules créés ou adaptés à l'étape 11 ;
- les mécanismes existants de configuration et de persistance ;
- les scripts de démarrage et d'arrêt concernés ;
- les tests frontend et backend existants.

Lis les documents de référence en entier lorsqu'ils constituent des instructions ou des décisions applicables.

Si un document n'existe pas, ne l'invente pas.

Puis exécute :

```text
git status
git diff --check
git log -1 --oneline
```

Ne suppose pas que le dépôt est dans le même état que lors de notre dernière conversation.

Ne repars pas de zéro.

Réutilise les composants, conventions et mécanismes existants lorsqu'ils sont adaptés.

Interdictions :

- Aucun commit.
- Aucun push.
- Aucun rebase.
- Aucun reset destructif.
- Aucun `git clean`.
- Aucune modification de l'historique Git.
- Aucune suppression non justifiée.
- Aucun téléchargement de nouveau modèle.
- Aucune modification du laboratoire GLM/Colibrì.
- Aucune refonte générale du frontend.
- Aucune réécriture de l'architecture indépendante des modèles.

Les profils Général et Programmation doivent rester fonctionnels.

Les données utilisateur, la mémoire, les conversations, les projets et les checkpoints doivent être préservés.

---

# 2. Architecture finale recherchée

Le centre de paramètres appartient à Léa.

Il ne doit pas être construit autour de Qwen, de llama.cpp, d'OpenHands ou d'une fonctionnalité spécifique.

Architecture conceptuelle :

```text
                         LÉA
                          │
                     Interface
                          │
               ┌──────────┴──────────┐
               │                     │
         Conversations           Paramètres
               │                     │
               │              Interface dédiée
               │                     │
               │              Validation des choix
               │                     │
               │              Backend / persistance
               │                     │
               └──────────┬──────────┘
                          │
                  Fonctionnalités Léa
                          │
              ┌───────────┴───────────┐
              │                       │
           Général               Programmation
              │                       │
          Modèle IA              Modèle IA
```

Ce schéma n'impose pas de nouveaux services.

Adapte-le au fonctionnement réel de l'application.

## Principes obligatoires

- Léa possède les paramètres.
- Chaque réglage a une valeur définie et validée.
- Les paramètres sont persistants.
- Les réglages des différents profils restent indépendants.
- L'interface ne modifie pas directement les fichiers du système.
- Le backend contrôle les changements nécessitant son intervention.
- Les fonctionnalités restent responsables de l'application de leurs propres réglages.
- Les paramètres ne modifient pas les permissions de sécurité des profils.
- Un réglage indisponible ne doit pas être présenté comme opérationnel.
- L'ajout de nouveaux paramètres doit rester simple.

Attention à ne pas créer une seconde source de vérité contradictoire avec l'étape 11.

Le registre central des modèles reste distinct des préférences fonctionnelles de l'utilisateur.

---

# 3. Ce qui est explicitement reporté

Ne réalise PAS maintenant :

- Un sélecteur graphique de modèles.
- Une API d'administration générale des modèles.
- L'ajout ou le téléchargement de modèles.
- L'intégration GLM/Colibrì.
- Une détection automatique universelle des capacités des modèles.
- Des niveaux Medium ou Ultra imposés aux modèles actuels.
- Le démarrage automatique de Docker Desktop.
- La fermeture automatique de Docker Desktop.
- Le développement avancé d'OpenHands.
- Les fonctionnalités Windows avancées.
- Le microphone.
- La reconnaissance vocale.
- La synthèse vocale.
- Le réglage du volume de la voix.
- La compréhension d'images.
- La génération d'images.
- Les nouveaux profils.
- La Web Gateway.
- La refonte visuelle complète.
- La mémoire avancée.
- Le fine-tuning.

Les paramètres liés à ces fonctionnalités seront ajoutés lorsqu'elles seront implémentées.

**Ne crée pas de boutons factices ni d'options qui ne font rien.**

En particulier, n'ajoute pas immédiatement des interrupteurs Docker Desktop si le démarrage ou l'arrêt automatique n'existe pas encore.

Le centre de paramètres doit être extensible, mais nous ne voulons pas construire aujourd'hui toutes les options futures.

---

# 4. Barrières strictes

Ordre obligatoire :

```text
12A — Audit des paramètres et du cycle de vie
12B — Gestion centrale et persistance des paramètres
12C — Bouton Paramètres et page dédiée
12D — Réglage Low / High du profil Général
12E — Réglage du profil Programmation
12F — Application, validation et gestion des erreurs
12G — Extensibilité et intégration aux profils
12H — Tests réels et non-régression
12I — Commentaires, nettoyage et documentation
12J — Validation finale et clôture
```

Après chaque sous-étape :

1. Exécute les tests ciblés.
2. Corrige les erreurs.
3. Relance les tests concernés.
4. Vérifie qu'aucune fonctionnalité existante n'est cassée.
5. Ne commence la sous-étape suivante que si les contrôles nécessaires sont satisfaits.

Si le dépôt possède déjà un système de suivi des sous-étapes, réutilise-le si pertinent.

Ne crée pas un nouveau gestionnaire de progression uniquement pour cette étape.

Si une décision majeure est nécessaire, explique les possibilités et demande mon avis.

---

# 5. 12A — Audit des paramètres et du cycle de vie

C'est la première véritable tâche.

Avant de développer la page Paramètres, examine les mécanismes existants.

Inspecte :

- L'organisation actuelle du frontend React.
- Les composants réutilisables.
- La navigation.
- Les routes éventuelles.
- Le fonctionnement du sélecteur de profils.
- Les mécanismes de communication frontend/backend.
- La persistance SQLite existante.
- Les éventuels fichiers de préférences.
- Le fonctionnement du bouton Démarrer.
- Le fonctionnement du bouton Arrêter.
- Le cycle de vie du backend.
- Le cycle de vie du modèle.
- La configuration du profil Général.
- La configuration du profil Programmation.
- L'intégration OpenHands.
- Les réglages actuellement codés en dur.

## Point architectural important

L'utilisateur lance actuellement Léa puis démarre les profils depuis son interface.

Il faut vérifier exactement quels services sont disponibles lorsque :

```text
Frontend ouvert
IA arrêtée
Modèle non chargé
```

**La page Paramètres doit idéalement rester utilisable lorsque l'IA est arrêtée.**

Cela comprend autant que possible :

- L'ouverture de la page.
- La consultation des réglages.
- Leur modification.
- Leur sauvegarde.
- Leur restauration lors du prochain lancement.

Ne lance pas automatiquement un modèle lourd simplement pour afficher ou sauvegarder les paramètres.

Réutilise si possible les mécanismes de communication et de persistance existants.

Si une modification du cycle de vie du backend est indispensable, propose la solution minimale et explique ses conséquences.

Ne crée pas un nouveau service permanent complexe sans justification.

Si le fonctionnement actuel rend impossible un centre de paramètres réellement utilisable à l'arrêt sans changement architectural important, signale-le avant de prendre cette décision.

## Résultat de 12A

Présente brièvement :

- Les mécanismes existants réutilisables.
- La manière dont les paramètres seront stockés.
- La manière dont le frontend communiquera avec la persistance.
- Les implications lorsque l'IA est arrêtée.
- Les modifications nécessaires.
- Les points de vigilance.

Puis poursuis si aucune décision majeure ne bloque l'implémentation.

---

# 6. 12B — Gestion centrale et persistance des paramètres

Crée ou adapte un mécanisme central de gestion des préférences fonctionnelles de Léa.

Il doit être indépendant du registre des modèles.

## Fonctions minimales

Le système doit permettre :

```text
Lire les paramètres
        ↓
Valider les valeurs
        ↓
Modifier un réglage
        ↓
Sauvegarder
        ↓
Relire
        ↓
Appliquer au bon composant
```

Il doit également :

- Fournir des valeurs par défaut cohérentes.
- Préserver les réglages enregistrés.
- Refuser les valeurs invalides.
- Gérer les erreurs de lecture.
- Gérer les erreurs d'écriture.
- Éviter les sauvegardes partielles incohérentes.
- Permettre l'ajout ultérieur de nouveaux réglages.
- Éviter de perdre les préférences existantes lors d'une évolution du format.

## Stockage

Examine les mécanismes existants avant de choisir.

Tu peux utiliser une solution simple adaptée au projet, par exemple un fichier local de préférences ou un stockage SQLite existant.

Ne crée pas une nouvelle base de données si ce n'est pas justifié.

Ne stocke pas les préférences personnelles dans un fichier de configuration Git qui serait écrasé à chaque mise à jour.

Si tu utilises un fichier de préférences, assure une écriture sûre.

Si tu utilises SQLite, préserve l'intégrité et la compatibilité des données existantes.

Évite toute migration risquée et inutile.

## Backend

La page Paramètres peut utiliser les mécanismes backend existants pour lire et enregistrer ses préférences.

Ajoute uniquement les opérations nécessaires.

Ne crée pas une grosse API universelle.

Ne crée pas d'API permettant de modifier arbitrairement les chemins du système, de lancer des commandes ou d'administrer les fichiers des modèles.

Le registre `config/models.json` ne doit pas être modifié directement par cette interface.

Si des endpoints sont nécessaires, ils doivent être locaux, validés et conformes aux protections actuelles du backend.

## Tests 12B

Teste :

- Lecture des valeurs par défaut.
- Sauvegarde d'une préférence valide.
- Relecture après redémarrage du composant concerné.
- Rejet d'une valeur inconnue.
- Rejet d'un type incorrect.
- Gestion d'une erreur de sauvegarde.
- Préservation des autres paramètres lorsqu'un seul est modifié.
- Préservation du registre des modèles.
- Absence de modification des données utilisateur sans rapport.

---

# 7. 12C — Bouton Paramètres et page dédiée

Ajoute un bouton clairement identifiable dans l'interface de Léa :

```text
Paramètres
```

Un pictogramme d'engrenage peut être utilisé si cohérent avec les composants existants.

Ce bouton ouvre une page ou une vue dédiée.

## Interface attendue

L'utilisateur doit pouvoir :

- Ouvrir les paramètres.
- Voir les catégories disponibles.
- Consulter les valeurs actuelles.
- Modifier les réglages proposés.
- Valider les changements.
- Recevoir une confirmation réelle de sauvegarde.
- Comprendre si un redémarrage est nécessaire.
- Revenir à l'interface principale.
- Retrouver ses choix après redémarrage.

## Présentation

Je souhaite une interface :

- Sobre.
- Moderne.
- Lisible.
- Cohérente avec le frontend actuel.
- Simple à utiliser.
- Correctement aérée.
- Accessible au clavier.
- Compréhensible sans documentation complexe.

Ne fais pas de refonte visuelle générale.

La refonte complète du frontend est prévue plus tard.

Il faut donc utiliser des composants simples et réutilisables.

## Organisation

Prévois une structure permettant de regrouper progressivement les réglages.

Les premières sections peuvent concerner :

```text
Paramètres de Léa

    Général
        Raisonnement

    Programmation
        Raisonnement, si réglage réellement disponible
```

Tu peux choisir une organisation plus naturelle si le frontend actuel le justifie.

Ne crée pas maintenant de catégories remplies d'options fictives.

## Sauvegarde

Je souhaite un bouton de validation lorsque cela est pertinent :

```text
Valider
```

Le comportement doit être clair :

1. L'utilisateur choisit une valeur.
2. La page indique la nouvelle sélection.
3. Il valide.
4. Le système sauvegarde.
5. La page confirme le succès réel.

En cas d'échec, ne présente pas le paramètre comme enregistré.

Évite d'exécuter plusieurs sauvegardes concurrentes.

## Tests 12C

Vérifie :

- Bouton visible.
- Ouverture de la page.
- Retour à la conversation.
- Affichage des valeurs actuelles.
- Modification d'un contrôle.
- Validation.
- Message d'erreur en cas d'échec.
- Persistance au rechargement.
- Absence de rechargement inutile de la conversation.
- Conservation du profil et des données de discussion.

---

# 8. 12D — Réglage Low / High du profil Général

Le profil Général utilise actuellement un modèle de la famille Qwen3.

Son comportement habituel utilise `/no_think`.

L'utilisateur a confirmé avoir testé ce comportement.

Nous voulons ajouter une option simple permettant de choisir :

```text
LOW
HIGH
```

## Comportement souhaité

```text
LOW
    ↓
/no_think
    ↓
Réponse directe
```

```text
HIGH
    ↓
/think
    ↓
Mode de réflexion activé
```

La valeur par défaut du profil Général doit être :

```text
LOW
```

## Interface

L'utilisateur doit pouvoir sélectionner Low ou High.

Un curseur à deux positions ou un contrôle segmenté peut convenir.

Choisis l'interface la plus claire.

Un bouton Valider doit permettre de sauvegarder le choix.

## Intégration technique

Examine d'abord comment `/no_think` est actuellement appliqué au modèle Général.

Réutilise ce mécanisme s'il est approprié.

Vérifie que `/think` est reconnu et réellement transmis de manière compatible avec le modèle actuel, son template de conversation et llama.cpp.

Ne te contente pas d'enregistrer une préférence en mémoire si celle-ci n'est jamais utilisée lors de l'inférence.

Le changement doit affecter les prochaines réponses du profil.

Si un redémarrage est nécessaire, informe l'utilisateur.

Sinon, applique le réglage de manière sûre à la requête suivante.

Ne perturbe pas une génération déjà en cours.

## Confidentialité du raisonnement

Le mode High ne doit pas exposer involontairement des marqueurs internes ou des traces de raisonnement dans l'interface.

Préserve les protections existantes et vérifie la manière dont les réponses du modèle sont traitées.

## Tests 12D

Teste :

- Low sélectionné par défaut.
- Low sauvegardé.
- High sauvegardé.
- Relecture correcte des valeurs.
- Passage Low → High.
- Passage High → Low.
- Transmission effective du mécanisme correspondant.
- Vérification réelle avec Qwen3.
- Absence de marqueurs internes indésirables dans la réponse affichée.
- Conversations et mémoire inchangées.
- Persistance après redémarrage.

Si `/think` ne fonctionne pas sur la variante réellement installée, signale-le précisément.

Ne prétends pas que High fonctionne uniquement parce qu'une préférence a été enregistrée.

---

# 9. 12E — Réglage du profil Programmation

Nous souhaitons également disposer, si techniquement réalisable, d'un réglage Low / High pour le profil Programmation.

La valeur par défaut souhaitée est :

```text
HIGH
```

Cependant, il existe une différence technique importante :

**Qwen2.5-Coder-7B ne possède pas nécessairement le mécanisme natif `/think` / `/no_think` des modèles Qwen3.**

Ne lui applique pas aveuglément ces commandes.

## Audit obligatoire

Avant de développer le réglage, examine :

- Les capacités réelles du Qwen2.5-Coder actuellement installé.
- Les possibilités du moteur llama.cpp utilisé.
- Le template de conversation.
- Les paramètres d'inférence pertinents.
- Les mécanismes supportés par OpenHands.
- Les instructions du profil Programmation.
- Les risques d'interférence avec les appels d'outils.
- Les protections et validations des tâches.

## Comportement souhaité

Nous voulons idéalement :

```text
LOW
    ↓
Comportement de traitement plus léger
```

```text
HIGH
    ↓
Comportement de traitement plus approfondi
```

Mais ce réglage doit produire une différence technique réelle.

Si un mécanisme natif compatible existe, utilise-le.

Si le seul mécanisme raisonnable repose sur les instructions de l'agent ou une stratégie de traitement, distingue explicitement ce comportement d'un véritable niveau de raisonnement interne du modèle.

Dans ce cas, le contrôle doit être nommé honnêtement et ses effets doivent être testés.

Ne réduis jamais les protections de sécurité, les validations de fichiers, les checkpoints ou les tests obligatoires pour obtenir un mode Low plus rapide.

Ne modifie pas profondément l'architecture OpenHands uniquement pour obtenir un curseur.

## Cas où le réglage n'est pas réalisable

Si aucune différence utile, suffisamment fiable et démontrable ne peut être implémentée sans risque ou complexité disproportionnée :

- Ne crée pas de réglage fictif.
- Ne prétends pas que `/think` fonctionne sur Qwen2.5-Coder.
- Présente les solutions possibles.
- Explique leurs compromis.
- Demande une décision à l'utilisateur si nécessaire.

Le centre de paramètres doit rester fonctionnel même si ce réglage précis nécessite une décision ultérieure.

## Tests 12E

Si le réglage est implémenté, vérifie :

- Valeur par défaut High.
- Sauvegarde.
- Relecture.
- Application effective au profil Programmation.
- Conservation des appels d'outils.
- Conservation des validations.
- Conservation des protections OpenHands.
- Aucun impact sur le profil Général.
- Aucun redémarrage dangereux pendant un run actif.

Ne présente pas un simple changement d'étiquette dans l'interface comme une modification prouvée du raisonnement du modèle.

---

# 10. 12F — Application et validation des paramètres

Cette sous-étape consolide le comportement de la page Paramètres.

## Règles générales

Chaque réglage doit avoir :

- Un identifiant stable.
- Une valeur par défaut.
- Des valeurs autorisées.
- Une validation appropriée.
- Un mécanisme de sauvegarde.
- Un mécanisme d'application.
- Un comportement d'erreur compréhensible.

Il ne faut pas nécessairement créer une grosse structure générique pour représenter ces informations.

Utilise l'organisation la plus simple qui convient à l'application.

## Application des changements

Certains paramètres peuvent être appliqués immédiatement.

D'autres peuvent demander :

- Une nouvelle requête.
- Un arrêt du modèle.
- Un redémarrage du modèle.
- Un redémarrage d'un service.

L'interface doit indiquer ce qui est réellement nécessaire.

Ne relance pas automatiquement un modèle lourd si cela n'est pas requis.

Ne coupe pas une génération active simplement parce qu'un paramètre a été modifié.

Ne modifie pas silencieusement le modèle utilisé par un run OpenHands en cours.

## Erreurs

En cas d'échec :

- Affiche une explication claire.
- Préserve le dernier réglage valide.
- Ne confirme pas faussement la réussite.
- Permets une nouvelle tentative lorsque cela a du sens.
- Évite les états contradictoires entre frontend et backend.

## Tests 12F

Teste notamment :

- Sauvegarde réussie.
- Sauvegarde refusée.
- Backend indisponible.
- Valeur invalide.
- Deux modifications successives.
- Retour sur la page.
- Redémarrage.
- Génération active.
- Run Programmation actif.
- Persistance de la dernière valeur valide.

---

# 11. 12G — Extensibilité du centre de paramètres

Nous allons ajouter de nouvelles fonctionnalités à Léa au cours des prochaines étapes.

Il faut que leurs paramètres puissent être ajoutés simplement.

Exemples futurs :

```text
Programmation avancée
    Démarrer Docker automatiquement
    Fermer Docker Desktop à l'arrêt

Microphone
    Sensibilité
    Périphérique d'entrée

Speech-to-Speech
    Volume de la voix
    Choix de la voix

Futurs profils
    Réglages spécifiques aux modèles
```

Ces exemples illustrent la direction du projet.

**Ils ne doivent pas être implémentés maintenant.**

## Architecture souhaitée

Lorsqu'une nouvelle fonctionnalité sera ajoutée, son développement devra pouvoir inclure :

1. La définition de ses réglages.
2. Leur validation.
3. Leur sauvegarde.
4. Leur application.
5. Leur affichage dans la page Paramètres.
6. Leurs tests.

Tout cela sans reconstruire le centre de paramètres.

## Limites

Ne construis pas maintenant :

- Un système de plugins complexe.
- Un moteur universel de formulaires.
- Une détection automatique de tous les futurs modèles.
- Un catalogue de centaines d'options.
- Un système de permissions administratif avancé.
- Un service séparé de configuration.

Une organisation simple par catégories ou composants suffit.

## Tests 12G

Démontre que l'ajout d'un paramètre supplémentaire serait localisé et documenté.

Un test utilisant une préférence fictive isolée peut être acceptable, mais ne laisse pas apparaître cette préférence dans l'interface utilisateur finale.

---

# 12. 12H — Validation réelle et non-régression

Nous voulons des tests réels, pas uniquement des tests simulés.

## Test 1 — Interface

Valide :

- Lancement normal de Léa.
- Présence du bouton Paramètres.
- Ouverture de la page.
- Affichage correct.
- Retour vers les conversations.
- Navigation sans perte de données.

## Test 2 — IA arrêtée

Vérifie le fonctionnement de la page Paramètres lorsque le modèle n'est pas chargé.

Valide autant que possible :

- Ouverture.
- Consultation.
- Modification.
- Sauvegarde.
- Relecture.

Ne lance pas un modèle uniquement pour faire fonctionner les paramètres.

Si une partie du fonctionnement dépend encore d'un service, documente précisément cette dépendance.

## Test 3 — Général Low

- Sélectionne Low.
- Valide.
- Démarre Général.
- Envoie une question simple.
- Vérifie le comportement `/no_think`.
- Vérifie la réponse.
- Vérifie l'absence de raisonnement interne affiché.

## Test 4 — Général High

- Sélectionne High.
- Valide.
- Exécute une question adaptée.
- Vérifie que le mécanisme `/think` est réellement appliqué.
- Vérifie la réponse.
- Vérifie qu'aucun marqueur interne non souhaité n'apparaît dans l'interface.

## Test 5 — Persistance

- Modifie une préférence.
- Enregistre-la.
- Ferme Léa.
- Relance Léa.
- Retourne dans Paramètres.
- Vérifie que la valeur est conservée.

## Test 6 — Programmation

- Démarre Programmation.
- Vérifie le comportement du modèle.
- Vérifie OpenHands.
- Vérifie les paramètres effectivement implémentés.
- Vérifie que le changement de préférences n'affaiblit pas les contrôles existants.
- Vérifie le retour vers Général.

Si des essais réels d'OpenHands sont nécessaires, utilise uniquement un projet de test autorisé.

Ne demande pas à l'agent intégré de modifier le dépôt principal directement.

## Test 7 — Sécurité et erreurs

Teste :

- Valeur inconnue.
- Valeur malformée.
- Échec de sauvegarde.
- Backend indisponible.
- Fichier de préférences absent.
- Préférences invalides au démarrage.
- Requête non autorisée ou malformée, selon les protections actuelles.
- Absence de possibilité de modifier arbitrairement des chemins système.
- Absence d'exécution de commandes provenant des préférences.

## Test 8 — Non-régression

Relance les suites pertinentes :

- Backend.
- Frontend.
- Build React/TypeScript.
- Modèles et profils.
- Mémoire.
- Conversations.
- Historique.
- Commutation.
- OpenHands.
- Checkpoints.
- Rollback.
- Scripts PowerShell concernés.
- Persistance.
- Sécurité.

Puis :

```text
git diff --check
```

Distingue :

- Tests automatisés.
- Tests d'intégration.
- Mocks.
- Tests réels avec Qwen.
- Tests réels avec OpenHands.
- Tests non exécutés.

Une simulation ne doit jamais être présentée comme une preuve complète de fonctionnement réel.

---

# 13. 12I — Commentaires, qualité et nettoyage

Conserve la règle de qualité utilisée lors des étapes précédentes.

## Commentaires obligatoires

Dans chaque fichier source créé ou substantiellement modifié, chaque fonction, méthode ou callback significatif doit posséder au moins un commentaire ou une docstring réellement utile.

Documente particulièrement :

- La gestion des paramètres.
- La validation des valeurs.
- La sauvegarde.
- La lecture.
- Les comportements par défaut.
- L'application au modèle.
- La communication frontend/backend.
- Les erreurs.
- Les protections.
- Les états de chargement.
- Les opérations nécessitant un redémarrage.

Ajoute des commentaires supplémentaires pour les blocs complexes.

Les commentaires doivent être :

- Professionnels.
- Précis.
- Techniques.
- Naturels.
- Sans emojis.
- Cohérents avec le fonctionnement réel.

N'ajoute pas de commentaires qui répètent simplement une opération évidente.

## Lisibilité

Je veux un code propre et respirant.

Applique :

- Lignes vides entre les blocs logiques.
- Fonctions clairement séparées.
- Paramètres longs répartis sur plusieurs lignes.
- Conditions complexes lisibles.
- Noms explicites.
- Indentation cohérente.
- Composants de taille raisonnable.
- Organisation claire des responsabilités.
- Conventions de formatage existantes.

Ne compacte pas le code pour économiser quelques lignes.

Mais ne reformate pas inutilement tout le dépôt.

## Nettoyage

Recherche :

- Imports inutilisés.
- Fonctions devenues obsolètes.
- Variables inutilisées.
- Duplications.
- Anciennes configurations remplacées.
- Composants temporaires.
- Fichiers sans consommateurs.
- Commentaires périmés.
- Code mort confirmé.

Pour les éléments concernés :

```text
KEEP
ADAPT
REMOVE
```

Supprime uniquement ce dont l'inutilité est démontrée.

Vérifie les références et les usages indirects avant une suppression.

Préserve absolument :

- Les poids des modèles.
- Les données utilisateur.
- Les conversations.
- La mémoire.
- Les checkpoints.
- Les journaux d'audit nécessaires.
- Les fichiers du laboratoire GLM.
- Les configurations encore utilisées.

En cas de doute, conserve et signale.

## Documentation finale

Mets à jour les documents pertinents :

- `README.md`
- `TODO.md`
- `CHANGELOG.md`
- `AGENTS.md`, si nécessaire
- `docs/DECISIONS.md`, s'il existe
- La documentation frontend/backend concernée.

Explique :

- Comment ouvrir la page Paramètres.
- Comment modifier une préférence.
- Comment sauvegarder.
- Où les préférences sont stockées.
- Quels réglages peuvent être appliqués immédiatement.
- Quels réglages nécessitent un redémarrage.
- Comment ajouter un futur paramètre.
- Les limites des réglages de raisonnement.
- La distinction entre le registre de modèles et les préférences utilisateur.

## Roadmap

Conserve la roadmap validée :

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

Le périmètre de l'étape 13 sera rediscuté avec l'utilisateur.

Ne le redéfinis pas maintenant.

---

# 14. 12J — Validation finale et clôture

L'étape 12 se termine ici.

Ne commence pas une nouvelle série de fonctionnalités après cette sous-étape.

## Vérification finale de l'interface

Valide :

- Bouton Paramètres visible.
- Page accessible.
- Navigation correcte.
- Réglages chargés.
- Sauvegarde fonctionnelle.
- Messages de confirmation et d'erreur corrects.
- Persistance après redémarrage.
- Absence de perte des conversations.

## Vérification finale des modèles

Valide :

- Général Low par défaut.
- Général High fonctionnel si le mécanisme est confirmé.
- Configuration Général conservée après redémarrage.
- Programmation toujours fonctionnel.
- Réglage Programmation correctement implémenté ou limitation clairement exposée, sans fonctionnalité fictive.
- Aucun changement du registre central des modèles depuis l'interface.
- Aucun modèle supplémentaire installé.

## Vérification de sécurité

Valide :

- Aucun accès arbitraire aux fichiers.
- Aucune exécution de commandes arbitraires.
- Aucune modification non contrôlée des processus.
- Aucune exposition réseau supplémentaire injustifiée.
- Aucun affaiblissement des protections existantes.
- Aucune donnée sensible ajoutée à Git.

## Tests finaux

Relance les suites complètes applicables.

Puis :

```text
git status
git diff --check
```

Ne considère pas l'étape validée si une régression majeure est encore présente.

---

# 15. Nettoyage final

À la fin :

- Arrête les modèles lancés uniquement pour les tests.
- Arrête les runs OpenHands de test.
- Arrête les services démarrés uniquement pour cette étape.
- Ferme les processus de test restants.
- Nettoie prudemment les artefacts temporaires inutiles.
- Préserve les véritables préférences utilisateur.
- Préserve la base SQLite.
- Préserve les conversations.
- Préserve les souvenirs.
- Préserve les checkpoints.
- Préserve les configurations des modèles.
- Préserve les volumes OpenHands nécessaires.
- Ne ferme pas un service qui était déjà utilisé avant tes tests.
- Ne supprime aucun modèle.
- N'ajoute aucun secret à Git.
- Ne réalise aucun commit.

Vérifie les processus et ports encore actifs.

Puis :

```text
git status

git diff --check
```

Relance les tests concernés si la passe finale de nettoyage ou de commentaires a modifié du code exécutable.

---

# 16. Critère final de réussite

L'étape 12 est terminée si, et seulement si :

> L'utilisateur peut ouvrir une page Paramètres depuis Léa, consulter les préférences disponibles, modifier et valider des réglages réellement fonctionnels, retrouver ses choix après redémarrage et continuer à utiliser Général et Programmation sans régression.

Critères complémentaires :

- La page Paramètres appartient à Léa, pas à Qwen.
- Le système de préférences est clairement séparé du registre des modèles.
- Le profil Général possède un véritable réglage Low / High validé.
- Le profil Programmation conserve son fonctionnement et n'affiche pas de réglage trompeur.
- Les paramètres persistent.
- La sauvegarde est vérifiée.
- Les erreurs sont correctement affichées.
- Les nouvelles fonctionnalités pourront ajouter leurs propres paramètres facilement.
- Aucune fonctionnalité future n'a été artificiellement implémentée.
- Les protections existantes sont préservées.
- Le code est propre, bien commenté et correctement aéré.
- Les fichiers réellement obsolètes sont supprimés prudemment.
- Les tests disponibles sont exécutés avec des résultats honnêtes.
- La documentation est à jour.

Un réglage futur non nécessaire à cette étape ne doit pas bloquer le développement.

---

# 17. Rapport final obligatoire

Fournis uniquement à la fin un rapport structuré.

## Verdict

Si tous les critères essentiels sont validés :

```text
ETAPE_12_REUSSIE
```

Sinon :

```text
ETAPE_12_PARTIELLE
```

ou :

```text
ETAPE_12_BLOQUEE
```

Ne déclare pas la réussite si un critère essentiel n'est pas respecté.

## 12A → 12J

Tableau :

```text
Sous-étape | Statut | Modifications | Tests
```

## Architecture

Explique :

- L'architecture initiale.
- Les mécanismes réutilisés.
- Les composants ajoutés.
- Le mécanisme de persistance.
- La communication frontend/backend.
- Le comportement de la page quand l'IA est arrêtée.
- Les choix techniques et leurs justifications.

## Interface Paramètres

Présente :

- L'emplacement du bouton.
- L'organisation de la page.
- Les contrôles disponibles.
- Le fonctionnement du bouton Valider.
- La gestion des erreurs.
- La navigation.
- Les limitations.

## Paramètres Général

Indique :

- Valeur par défaut.
- Fonctionnement Low.
- Fonctionnement High.
- Mécanisme réellement appliqué à Qwen3.
- Tests effectués avec le modèle réel.
- Comportement après redémarrage.

## Paramètres Programmation

Indique :

- Les capacités réellement constatées de Qwen2.5-Coder.
- Les mécanismes étudiés.
- Le réglage éventuellement implémenté.
- Ses effets vérifiés.
- Les limites.
- Les décisions qui restent éventuellement à prendre.

Ne confonds pas une stratégie d'instructions d'agent avec un mode de raisonnement natif.

## Extensibilité

Explique comment, à l'étape 13 ou aux étapes suivantes, nous pourrons ajouter un nouveau paramètre sans reconstruire la page.

Ne commence pas ces développements.

## Qualité du code

Indique :

- Les fichiers commentés.
- Les nouvelles docstrings.
- Les améliorations de lisibilité.
- Les composants nettoyés.
- Les fichiers supprimés, avec justification.
- Les éléments conservés faute de preuve suffisante de leur inutilité.

## Tests finaux

Donne les résultats exacts :

- Backend.
- Frontend.
- Build.
- Persistance.
- Général Low.
- Général High.
- Programmation.
- Navigation.
- Gestion des erreurs.
- Sécurité.
- Commutation.
- Conversations et mémoire.
- OpenHands.
- `git diff --check`.

Distingue les tests automatisés des essais réels.

Signale les tests qui n'ont pas pu être exécutés.

## Problèmes et questions

Présente clairement :

- Les problèmes rencontrés.
- Les problèmes corrigés.
- Les problèmes non résolus.
- Les limitations connues.
- Les décisions techniques prises.
- Les éventuelles questions à poser à l'utilisateur.

S'il n'y a aucune question, indique-le.

## Étape 13

Mentionne seulement les points utiles pour intégrer ultérieurement les paramètres de la programmation avancée.

Ne commence pas l'étape 13.

## Git

Fournis :

- Fichiers modifiés.
- Fichiers créés.
- Fichiers supprimés.
- Résultat de `git status`.
- Résultat de `git diff --check`.
- Confirmation d'absence de commit.
- Confirmation d'absence de push.

## État final

Indique :

- L'état des processus.
- L'état du backend/frontend.
- L'état des modèles.
- L'état d'OpenHands.
- L'intégrité des données utilisateur.
- Les validations éventuellement restantes.

Après ce rapport, **ARRÊTE-TOI**.

Attends ma validation manuelle.

---

# 18. Consigne finale

Je veux une vraie page Paramètres, simple à utiliser et facile à faire évoluer.

Ne crée pas une usine à gaz.

Ne développe pas des fonctions que nous n'utilisons pas encore.

Ne prétends jamais qu'une option fonctionne si elle ne fait qu'enregistrer une valeur sans aucun effet.

Privilégie :

```text
Centre de paramètres fonctionnel

+

Préférences persistantes

+

Réglages adaptés aux modèles actuels

+

Interface simple et claire

+

Ajout facile de futurs réglages

+

Général et Programmation préservés

+

Code propre, aéré et commenté

+

Tests réels

+

Aucune régression

+

Rapport final vérifiable
```

Lorsque l'étape 12 est réellement terminée, fournis le rapport complet puis attends ma validation.