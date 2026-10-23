# PROJET LÉA — ÉTAPE 15 : PROFIL VÉTÉRINAIRE ET OPTIMISATION GÉNÉRALE DES CONTRATS

## 0. OBJECTIF ET CONTEXTE

Nous lançons officiellement l'étape 15 de Projet Léa.

L'étape 14 est terminée et validée manuellement. Léa dispose notamment des profils Général et Programmation, d'une architecture indépendante des modèles, d'un centre de paramètres, d'une mémoire SQLite, d'une gestion des conversations, d'un système vocal local, d'une surveillance des ressources et d'une intégration OpenHands sécurisée.

**Cette étape contient deux chantiers successifs :**

**Phase A — Créer et intégrer complètement le profil Vétérinaire.**

**Phase B — Une fois le nouveau profil fonctionnel, optimiser en profondeur l'ensemble des contrats d'instructions de Léa.**

La phase B est une amélioration incluse dans l'étape 15. Elle ne constitue PAS une nouvelle étape de la roadmap.

Le futur profil Vétérinaire doit accorder une importance égale à :

1. L'apprentissage et aux révisions en médecine vétérinaire.
2. L'analyse de cas et au raisonnement clinique vétérinaire.

Le nouveau modèle retenu est :

**Qwen3.5-9B — GGUF Q4_K_M**

Emplacement attendu :

`L:\Projet_Lea\models\veterinary\Qwen3.5-9B-Q4_K_M.gguf`

Le modèle a été choisi pour cette étape. Aucun laboratoire comparatif supplémentaire n'est demandé.

L'étape suivante sera :

**Étape 16 — Accès Web.**

Vision est suspendue à la suite du blocage rencontré dans son laboratoire Ovis. Auxiliaire est définitivement retiré de la roadmap.

Ne développe ni Vision ni Web pendant cette mission.

---

# 1. RÈGLES ABSOLUES DU PROJET

Travaille dans :

`L:\Projet_Lea`

Commence par lire attentivement :

- `AGENTS.md`
- `README.md`
- `TODO.md`
- `CHANGELOG.md`
- `docs/DECISIONS.md`
- `docs/ETAPE_14_VALIDATION.md`
- `config/models.json`
- Les modules du registre des modèles.
- Les modules du gestionnaire de profils.
- Les contrats globaux et spécifiques aux profils.
- Les services de génération et d'inférence.
- Les API utilisées par le frontend.
- Les paramètres persistants SQLite.
- Les composants du sélecteur de profils.
- Les composants des conversations.
- Les composants vocaux.
- Les tests existants.

Inspecte le code réel avant de décider où intervenir.

Exécute au début :

- `git status`
- `git diff --check`
- `git log -1 --oneline`

Préserve toutes les modifications existantes.

Si le dépôt contient des modifications non commitées importantes, identifie-les précisément et protège-les. Ne réinitialise rien.

**Interdictions :**

- Aucun commit.
- Aucun push.
- Aucun rebase.
- Aucun reset destructif.
- Aucun `git clean`.
- Aucun effacement de base SQLite utilisateur.
- Aucune suppression de conversations.
- Aucune suppression de mémoire.
- Aucune suppression de checkpoints.
- Aucune modification des projets `IA_WORKSPACE` sans nécessité autorisée.
- Aucune suppression de modèles existants.
- Aucun remplacement des modèles Général ou Programmation.
- Aucune réduction du contexte de Programmation.
- Aucune refonte CSS générale.
- Aucun changement non nécessaire de l'architecture.
- Aucun service cloud.
- Aucune nouvelle dépendance externe sans justification.
- Aucune modification du laboratoire GLM ou du laboratoire Ovis.
- Aucune implémentation de Web ou de Vision.

Réutilise l'infrastructure validée plutôt que de créer des solutions parallèles.

Ne fais jamais passer une fonctionnalité simulée pour une fonctionnalité opérationnelle.

---

# 2. PHASE A — INTÉGRATION DU PROFIL VÉTÉRINAIRE

## 2.1. Vérification du modèle

Vérifie la présence du fichier :

`L:\Projet_Lea\models\veterinary\Qwen3.5-9B-Q4_K_M.gguf`

Confirme :

- Que le fichier existe.
- Qu'il n'est pas vide ou manifestement incomplet.
- Qu'il s'agit d'un GGUF lisible.
- Qu'il correspond bien à Qwen3.5-9B Q4_K_M.
- Qu'il n'est pas suivi par Git.
- Que son SHA-256 peut être calculé et enregistré.
- Que son format est compatible avec le runtime utilisé.

Ne retélécharge pas automatiquement le modèle si le fichier est absent. Signale clairement le blocage et son chemin attendu.

Le moteur de production est `llama.cpp`.

Vérifie la prise en charge réelle de Qwen3.5 par la version installée et les éventuelles particularités du template de conversation.

Attention : **Qwen3 et Qwen3.5 ne possèdent pas nécessairement la même architecture ni les mêmes mécanismes de contrôle du raisonnement.**

Ne déduis pas automatiquement que toutes les options de Qwen3 fonctionneront à l'identique.

Si une mise à jour de `llama.cpp` est véritablement nécessaire, explique pourquoi et protège les deux profils existants. Évite de remplacer un runtime stable sans tests ciblés.

## 2.2. Configuration matérielle

Matériel cible :

- Windows 11.
- Environ 32 Go de RAM.
- NVIDIA RTX A1000 Laptop GPU.
- 6 Go de VRAM.

Nous utilisons déjà Qwen3-4B pour Général et Qwen2.5-Coder-7B Q6_K pour Programmation.

Le nouveau profil devra fonctionner dans la même logique :

- Un seul gros modèle conversationnel chargé à la fois.
- Chargement lors de l'activation du profil.
- Déchargement propre lors du changement de profil.
- Répartition GPU/CPU adaptée aux ressources.
- Aucun OOM.
- Pas de pagination excessive.
- Surveillance mémoire existante préservée.
- Annulation et arrêt propres.

Définis un contexte initial raisonnable pour Vétérinaire en fonction des mesures réelles, sans diminuer celui des autres profils.

La consommation et la vitesse doivent être mesurées, pas supposées.

N'optimise pas uniquement la vitesse au détriment de la stabilité.

---

# 3. REGISTRE CENTRAL DES MODÈLES

Léa possède déjà une architecture permettant d'associer des profils à des modèles.

Utilise cette architecture.

Dans `config/models.json`, ou dans les structures réellement utilisées par le projet :

- Ajoute le profil `veterinary`.
- Associe-le à Qwen3.5-9B Q4_K_M.
- Définis son nom affiché : `Vétérinaire`.
- Définis son chemin de modèle.
- Définis son moteur `llama.cpp`.
- Définis les capacités réellement disponibles.
- Définis un contexte adapté.
- Configure ses options de raisonnement compatibles.
- Ajoute le profil au système de démarrage/arrêt.
- Préserve les configurations existantes.

Le registre doit continuer à permettre de remplacer ultérieurement ce modèle par un autre.

**Évite tout code qui suppose que Vétérinaire fonctionnera éternellement avec Qwen3.5.**

Si une évolution du schéma est nécessaire, applique une migration explicite et rétrocompatible.

Ne casse pas les fichiers de configuration existants.

---

# 4. SÉLECTEUR FRONTEND

Le frontend doit désormais présenter trois profils :

1. Général.
2. Programmation.
3. Vétérinaire.

Le nouveau profil doit s'intégrer visuellement au sélecteur existant.

**Ne crée pas une nouvelle interface complète.**

Conserve :

- Les composants actuels.
- Les styles actuels.
- Les boutons Démarrer et Arrêter.
- Le comportement de chargement.
- Les états de disponibilité.
- Les erreurs explicites.
- Le fonctionnement des autres profils.

Lorsqu'un utilisateur sélectionne Vétérinaire et clique sur Démarrer :

1. Léa vérifie l'état actuel.
2. Le modèle précédent est arrêté si nécessaire.
3. Qwen3.5-9B est chargé.
4. La disponibilité réelle est vérifiée.
5. Le frontend indique que Vétérinaire est prêt.
6. L'utilisateur peut immédiatement converser.

Lorsqu'il quitte le profil :

- Le modèle doit être libéré proprement.
- Les conversations et mémoires doivent rester intactes.
- Aucun worker lourd inutile ne doit rester actif.

Les transitions suivantes doivent fonctionner :

- Général → Vétérinaire.
- Vétérinaire → Général.
- Programmation → Vétérinaire.
- Vétérinaire → Programmation.
- Vétérinaire → arrêt.
- Arrêt → Vétérinaire.

Conserve les barrières empêchant les changements dangereux pendant une génération ou un run OpenHands actif.

---

# 5. IDENTITÉ ET COMPORTEMENT DU PROFIL VÉTÉRINAIRE

Le profil doit devenir un assistant vétérinaire pédagogique et analytique de qualité.

Il s'agit d'un outil d'aide à l'apprentissage et au raisonnement, pas d'un vétérinaire autonome.

Il ne doit jamais prétendre :

- Avoir examiné un animal qu'il n'a pas examiné.
- Avoir consulté un dossier absent.
- Avoir effectué une analyse inexistante.
- Avoir confirmé un diagnostic sans preuve.
- Avoir vérifié une source qui n'a pas réellement été consultée.

## 5.1. Domaines à couvrir

Le profil doit pouvoir discuter de :

- Anatomie.
- Physiologie.
- Histologie.
- Physiopathologie.
- Pathologie.
- Anesthésie.
- Analgésie.
- Pharmacologie.
- Toxicologie.
- Parasitologie.
- Microbiologie.
- Immunologie.
- Médecine interne.
- Chirurgie.
- Médecine préventive.
- Nutrition.
- Comportement.
- Urgences.
- Reproduction.
- Analyses de laboratoire.
- Santé publique et zoonoses.

Espèces concernées :

- Chiens.
- Chats.
- Chevaux.
- Bovins.
- Ovins.
- Caprins.
- Porcs.
- Animaux de compagnie exotiques / NAC.
- Autres espèces lorsque les connaissances du modèle le permettent.

Le modèle ne doit pas transférer automatiquement des connaissances d'une espèce à une autre.

La précision et l'identification des particularités propres à l'espèce sont essentielles.

---

# 6. PREMIÈRE VOCATION — APPRENTISSAGE ET RÉVISIONS

Le profil doit être capable de servir de professeur particulier en médecine vétérinaire.

## 6.1. Explication des cours

Il doit pouvoir :

- Expliquer une notion scientifique.
- Reformuler un texte difficile.
- Produire des résumés structurés.
- Organiser les notions par difficulté.
- Décomposer des mécanismes physiologiques.
- Présenter des exemples cliniques pédagogiques.
- Faire des liens entre disciplines lorsque cela est pertinent.
- Adapter le vocabulaire au niveau de l'utilisateur.

Il doit éviter les explications volontairement trop courtes lorsque le sujet exige davantage de précision.

Inversement, il ne doit pas produire inutilement des pages de texte pour une question simple.

## 6.2. Méthode de révision

Lorsqu'une séance de révision est demandée :

- Identifier la matière concernée.
- Identifier le chapitre ou le thème.
- S'adapter au niveau de difficulté.
- Donner la possibilité de lire et d'apprendre avant de commencer les questions.
- Poser les questions une par une si l'utilisateur le souhaite.
- Attendre sa réponse avant de passer à la suite.
- Corriger précisément.
- Dire clairement si la réponse est correcte, partiellement correcte ou incorrecte.
- Expliquer ce qui manque.
- Reposer ultérieurement les notions mal comprises, lorsque pertinent.

Prévoir une progression pédagogique en trois niveaux lorsque demandée :

1. Fondamentaux.
2. Compréhension intermédiaire.
3. Raisonnement approfondi.

Le modèle doit soutenir une progression logique sans mélanger les matières en cours de révision.

## 6.3. Suivi des acquis

Lorsque des questions évaluées ont été posées, le profil peut fournir :

- Nombre de réponses correctes.
- Nombre de réponses partielles.
- Nombre de réponses incorrectes.
- Pourcentage de réussite fondé sur les réponses réellement évaluées.
- Sujets à retravailler.
- Bilan de fin de chapitre.

**Ne jamais inventer un pourcentage d'acquisition ou une progression pédagogique qui n'a pas été mesurée.**

Réutilise le contexte de conversation existant.

Ne crée pas de nouveau système de suivi permanent ou de nouvelles tables SQLite simplement pour afficher un pourcentage pendant une séance.

Si la précision d'un bilan n'est pas possible faute de données, le modèle doit le dire.

---

# 7. DEUXIÈME VOCATION — RAISONNEMENT CLINIQUE

Cette fonction a exactement la même importance que l'apprentissage.

Le modèle doit être capable de raisonner sur des situations cliniques théoriques ou présentées par l'utilisateur.

## 7.1. Structure du raisonnement

Lorsqu'un cas clinique est fourni, il doit pouvoir :

1. Identifier l'espèce.
2. Identifier les informations disponibles.
3. Identifier les informations manquantes.
4. Résumer les signes importants.
5. Repérer les facteurs de gravité.
6. Proposer des diagnostics différentiels pertinents, sans les présenter comme confirmés.
7. Expliquer les mécanismes physiopathologiques possibles.
8. Identifier les examens complémentaires pertinents.
9. Expliquer comment les résultats influenceraient les hypothèses.
10. Distinguer les certitudes des hypothèses.
11. Signaler les limites du raisonnement.

Ne rends pas ce plan obligatoire pour chaque petite question.

Il doit être utilisé lorsque le contexte clinique le justifie.

## 7.2. Pharmacologie et thérapeutique

Le profil doit pouvoir expliquer :

- Classes de médicaments.
- Mécanismes d'action.
- Indications.
- Contre-indications.
- Effets secondaires.
- Interactions.
- Différences entre espèces.
- Principes de calcul de doses à des fins pédagogiques.

Cependant, une posologie ou un protocole destiné à un animal réel ne doit jamais être présenté comme sûr sans les données nécessaires et une référence adaptée.

Le modèle doit notamment reconnaître l'importance de l'espèce, du poids, de l'âge, des antécédents, des fonctions rénale/hépatique et du contexte clinique.

Ne transforme pas cette précaution en refus général d'expliquer la pharmacologie vétérinaire.

La pédagogie scientifique doit rester possible.

## 7.3. Urgences

Le modèle doit reconnaître les situations potentiellement critiques.

Lorsqu'une urgence réelle est plausible :

- La signaler clairement.
- Ne pas minimiser la gravité.
- Conseiller une prise en charge vétérinaire appropriée sans délai.
- Éviter les gestes ou traitements risqués non vérifiés.
- Fournir des informations pratiques générales lorsque cela peut être fait de manière sûre.

Les instructions doivent rester proportionnées au risque.

## 7.4. Fiabilité scientifique

Le modèle ne doit pas :

- Inventer des références bibliographiques.
- Inventer des études.
- Inventer des recommandations professionnelles.
- Confondre hypothèse et preuve.
- Inventer des résultats d'examen.
- Fournir de faux seuils biologiques avec une certitude injustifiée.

Si le modèle connaît une notion générale mais pas une valeur précise, il doit le signaler.

L'accès Web n'est pas encore disponible : il ne doit pas prétendre avoir vérifié une source récente.

---

# 8. CONVERSATIONS, HISTORIQUE ET MÉMOIRE

Le nouveau profil doit utiliser les mécanismes existants.

## 8.1. Conversations

L'utilisateur doit pouvoir :

- Démarrer une conversation vétérinaire.
- Reprendre une conversation.
- Consulter l'historique.
- Supprimer une conversation.
- Obtenir les réponses du bon modèle.
- Changer de profil sans corrompre les données.

Les conversations existantes des autres profils doivent rester intactes.

Ne crée pas de système de conversations parallèle pour Vétérinaire.

Réutilise les conventions actuelles de profil et d'identification des conversations.

## 8.2. Mémoire

Le profil doit disposer des capacités habituelles de Léa :

- `Retiens que...`
- Consultation de mémoire pertinente.
- `Oublie que...`
- Persistance après redémarrage.

La mémoire appartient au système Léa, pas aux poids du modèle.

Évite les mélanges involontaires entre les informations d'un utilisateur, les cas fictifs, les exemples de cours et les données concernant un animal réel.

Un cas clinique fictif ne doit pas devenir automatiquement une donnée personnelle mémorisée.

N'enregistre pas automatiquement des données médicales sensibles simplement parce qu'elles ont été évoquées.

Préserve le mécanisme de suppression physique des conversations et de la mémoire corrigé à la fin de l'étape 14.

Aucune migration destructive.

---

# 9. PARAMÈTRES DU PROFIL

Le profil Vétérinaire doit être configurable via le centre de paramètres existant.

Réutilise les API et mécanismes du backend.

Prévoir au minimum :

- Affichage du modèle associé.
- Configuration de modèle conformément aux capacités déjà existantes.
- Réglages de raisonnement compatibles.
- Persistance SQLite si les réglages concernent l'utilisateur.
- Chargement correct des paramètres après redémarrage.
- Validation des valeurs côté backend.

## 9.1. Raisonnement Low / High

Vérifie la manière officiellement supportée par Qwen3.5-9B et par notre version de `llama.cpp` pour contrôler le raisonnement.

Ne copie pas mécaniquement les marqueurs Qwen3 si leur sémantique diffère.

N'expose pas un bouton Low/High qui n'a aucun effet réel.

Si le modèle possède une seule stratégie fiable, documente cette limite au lieu d'imiter artificiellement deux modes.

Si les deux modes fonctionnent réellement :

- Configure-les de manière reproductible.
- Préserve les paramètres indépendants des autres profils.
- Vérifie que leur sélection influence effectivement l'exécution.
- Évite d'exposer dans l'interface un raisonnement interne brut qui n'est pas destiné à l'utilisateur.

---

# 10. INTÉGRATION VOCALE

Le nouveau profil doit conserver les capacités vocales de Léa.

Moteurs existants :

- Whisper : reconnaissance de la parole.
- Pocket TTS : voix principale de Léa.
- Piper/SIWIS : voix alternative.

Ces moteurs doivent être utilisables avec Vétérinaire, selon les contrats réels de l'interface.

Vérifie :

- Dictée vocale.
- Transcription insérée dans le champ de saisie.
- Envoi manuel en mode dictée.
- Conversation vocale.
- Réponse produite par Qwen3.5-9B.
- Synthèse avec la voix actuellement sélectionnée.
- Interruption de lecture.
- Arrêt propre.
- Historique préservé.
- Mémoire préservée.

Ne crée pas un nouveau moteur STT ou TTS.

Ne télécharge aucun modèle vocal.

Ne modifie pas les voix validées.

Le vocabulaire vétérinaire comporte de nombreux termes scientifiques. Vérifie que le passage transcription → modèle → synthèse reste correct sans modifier arbitrairement les moteurs.

Les tests automatisés sur audio synthétique ne doivent pas être présentés comme des tests au microphone physique.

---

# 11. LIMITES FONCTIONNELLES DE CETTE ÉTAPE

Le profil Vétérinaire doit pour l'instant rester textuel, avec prise en charge du microphone via les fonctions vocales existantes.

**Ne développe pas encore :**

- Analyse d'images.
- Radiographies.
- Échographies.
- Analyse de photos d'animaux.
- Génération d'images.
- Recherche Internet.
- Téléchargement de documents scientifiques.
- Base RAG vétérinaire complète.
- Fine-tuning.
- Agents autonomes vétérinaires.
- Intégration d'équipements cliniques.
- Nouveau système de dossiers médicaux.
- Nouveau module de suivi scolaire permanent.

Même si Qwen3.5 possède des caractéristiques multimodales, leur présence dans le modèle n'autorise pas automatiquement à exposer une fonctionnalité Vision non validée.

L'accès Web sera traité à l'étape 16.

Le RAG pourra être envisagé ultérieurement si un besoin réel apparaît.

---

# 12. VALIDATION TECHNIQUE DE LA PHASE A

Avant de passer à l'optimisation générale des contrats, le profil Vétérinaire doit avoir réussi des tests techniques sérieux.

## 12.1. Chargement réel

Vérifie :

- Lecture du fichier GGUF.
- Démarrage réel avec `llama.cpp`.
- Réponse simple en français.
- Déchargement propre.
- Réutilisation après arrêt.
- Absence d'erreur GPU/RAM.
- Absence de processus orphelin.

Mesure la mémoire réellement consommée et le temps de réponse.

## 12.2. Commutation

Teste :

- Général → Vétérinaire → Général.
- Programmation → Vétérinaire → Programmation.
- Démarrage directement sur Vétérinaire.
- Arrêt depuis Vétérinaire.
- Erreurs de modèle absent.
- Erreurs de chargement.
- Annulation ou changement pendant une activité.

Ne réalise pas de commutation forcée pendant un run OpenHands actif.

## 12.3. Utilisation vétérinaire réelle

Fais répondre le vrai modèle à des questions variées :

- Anatomie et physiologie.
- Anesthésie et douleur.
- Pharmacologie.
- Parasitologie.
- Interprétation d'un bilan fictif.
- Différentiels cliniques.
- Espèces différentes.
- Cas présentant un signal d'urgence.
- Questions dont la réponse est inconnue ou incertaine.
- Révision avec correction d'une réponse partielle.

Vérifie la qualité réelle des réponses, pas uniquement l'absence d'erreur HTTP.

Pour les affirmations cliniques importantes, utilise des références vétérinaires indépendantes et identifiables lorsqu'elles sont disponibles.

Un modèle ne doit pas s'autoattribuer une note de fiabilité clinique.

## 12.4. Régressions

Vérifie le fonctionnement de :

- Général.
- Programmation.
- OpenHands.
- Low/High existants.
- SQLite.
- Mémoire.
- Historique.
- Paramètres.
- Surveillance des ressources.
- Dictée.
- Conversation vocale.
- Pocket TTS.
- Piper.
- Démarrage/arrêt.

La validation de cette phase constitue la barrière avant la phase B.

**Si Vétérinaire ne fonctionne pas réellement, n'engage pas l'optimisation globale des contrats comme si la phase A était terminée. Signale le blocage.**

---

# 13. PHASE B — OPTIMISATION APPROFONDIE DE TOUS LES CONTRATS

Cette phase commence uniquement lorsque la phase A est fonctionnelle et que ses tests automatisés pertinents réussissent.

Il ne s'agit PAS d'une étape 16 ou d'une étape « bis ».

C'est une amélioration importante de la qualité de Léa à la fin de l'étape 15.

## 13.1. Contrats concernés

Je veux que tu examines et optimises tous les contrats principaux :

1. Contrat global Léa.
2. Contrat du profil Général.
3. Contrat du profil Programmation.
4. Contrat du nouveau profil Vétérinaire.
5. Instructions complémentaires de fiabilité.
6. Instructions de mémoire et de contexte.
7. Instructions d'utilisation d'outils et de vérification.
8. Assemblage des prompts et stratégies de raisonnement.

Ne modifie pas arbitrairement les prompts internes obligatoires de llama.cpp ou OpenHands lorsque leur fonctionnement dépend d'un protocole officiel.

Conserve clairement la distinction entre :

- Règles générales.
- Identité du profil.
- Instructions propres à la tâche.
- Données de conversation.
- Mémoire.
- Résultats des outils.
- Contenu non fiable.

Ne multiplie pas les contrats parallèles et contradictoires.

---

# 14. AUDIT DES CONTRATS ACTUELS

Avant de réécrire les contrats, réalise une cartographie complète.

Identifie :

- Où chaque contrat est défini.
- Où il est injecté.
- À quel moment il est assemblé.
- S'il est appliqué avant ou après les messages utilisateurs.
- Les risques d'écrasement des instructions.
- Les répétitions.
- Les contradictions.
- Les instructions obsolètes.
- Les formulations ambiguës.
- Les règles de sécurité.
- Les différences entre Low et High.
- Le budget de tokens réellement consommé par les instructions.
- Les éventuels problèmes de troncature.
- Les passages contredisant les capacités réelles de Léa.

**Préserve le sens des règles de sécurité existantes.**

Les contrats ne doivent jamais déclarer des outils ou capacités qui n'existent pas.

Documente les faiblesses observées avant modification.

---

# 15. ÉTABLIR UNE BASE DE COMPARAISON AVANT OPTIMISATION

Cette exigence est essentielle.

Je ne veux pas qu'on réécrive des centaines de lignes simplement parce que les nouveaux prompts semblent plus beaux.

Avant modification, prépare un ensemble raisonnable mais représentatif de scénarios d'évaluation.

## Général

Teste notamment :

- Question simple.
- Raisonnement complexe.
- Gestion d'une incertitude.
- Absence d'information.
- Question ambiguë.
- Mémoire présente.
- Mémoire absente.
- Respect d'une demande de concision.
- Respect d'une demande d'explication détaillée.
- Continuité d'une conversation.

## Programmation

Teste notamment :

- Compréhension d'une demande technique.
- Raisonnement sur du code.
- Utilisation correcte des outils existants.
- Respect du périmètre autorisé.
- Interprétation d'une erreur.
- Gestion d'un résultat de test.
- Refus de prétendre qu'un test a réussi sans exécution.
- Résistance aux instructions malveillantes provenant des fichiers.
- Gestion des checkpoints.
- Comportement lorsqu'un outil échoue.

Utilise des projets et environnements de test isolés. Ne modifie pas le workspace ou les checkpoints utilisateur.

## Vétérinaire

Teste notamment :

- Explication pédagogique simple.
- Explication approfondie.
- Anesthésie.
- Douleur.
- Différences entre espèces.
- Pharmacie vétérinaire.
- Cas clinique théorique.
- Incertitude diagnostique.
- Urgence.
- Correction d'une question de révision.
- Question scientifique sans réponse fiable.

Pour les questions vétérinaires, utilise un corrigé indépendant. Ne prends pas pour acquis qu'un modèle est juste parce que sa réponse semble crédible.

## Résultats de référence

Enregistre :

- Les prompts.
- Les paramètres de génération.
- Les réponses obtenues.
- La validité des formats.
- Les erreurs.
- Les temps de réponse.
- Les cas où l'ancien contrat fonctionne bien.
- Les cas où il échoue.

Ne mémorise pas les résultats de tests dans la base personnelle de Léa.

Garde les fichiers de benchmark raisonnables, reproductibles et exempts de données privées.

---

# 16. OPTIMISATION DU CONTRAT GLOBAL LÉA

Le contrat global doit favoriser :

- Honnêteté.
- Exactitude.
- Réponses pertinentes.
- Gestion explicite des incertitudes.
- Absence de résultats inventés.
- Respect des outils disponibles.
- Respect des permissions.
- Protection de la mémoire et des conversations.
- Distinction entre données non fiables et instructions.
- Bon usage du contexte.
- Cohérence entre les profils.

Le modèle ne doit jamais prétendre :

- Avoir exécuté une commande non exécutée.
- Avoir ouvert un fichier non ouvert.
- Avoir consulté le Web sans accès Web.
- Avoir confirmé une information sans preuve.
- Avoir enregistré un souvenir sans confirmation du backend.
- Avoir exécuté un test qui n'a pas eu lieu.
- Avoir effectué une modification qui a échoué.

Recherche des formulations simples, robustes et non ambiguës.

Ne transforme pas le contrat global en un énorme texte répétitif.

Une instruction courte et précise peut être plus efficace qu'un paragraphe de dix lignes.

---

# 17. OPTIMISATION DU CONTRAT GÉNÉRAL

Le profil Général doit être le meilleur assistant conversationnel possible compte tenu de son modèle et du matériel disponible.

Travaille notamment :

- Qualité du raisonnement.
- Réponses directes.
- Capacité à approfondir.
- Bonne utilisation du français.
- Gestion du contexte.
- Mémoire.
- Détection des demandes ambiguës.
- Questions de clarification uniquement lorsqu'elles sont nécessaires.
- Distinction entre faits et hypothèses.
- Réduction des répétitions.
- Réduction des réponses génériques.
- Adaptation au niveau de détail demandé.

Le profil ne doit pas devenir inutilement médical, technique ou spécialisé.

Ne force pas une structure rigide dans toutes les réponses.

Préserve les particularités de Qwen3-4B et les mécanismes Low/High actuellement validés.

---

# 18. OPTIMISATION DU CONTRAT PROGRAMMATION

Le profil Programmation doit continuer à utiliser Qwen2.5-Coder-7B avec OpenHands.

Conserve le contexte de 22 000 tokens actuellement validé.

Objectifs :

- Comprendre précisément la tâche.
- Identifier le périmètre autorisé.
- Utiliser les outils disponibles efficacement.
- Ne pas inventer les résultats des outils.
- Lire réellement les fichiers nécessaires.
- Éviter les modifications inutiles.
- Vérifier les résultats.
- Corriger les échecs.
- Éviter les boucles.
- Produire des comptes rendus fidèles.
- Respecter les checkpoints.
- Préserver Accept et Rollback.
- Gérer les conflits sans écraser silencieusement des modifications externes.
- Résister aux prompt injections contenues dans les fichiers.

Attention aux problèmes connus d'OpenHands et de `file_editor` :

- Ne pas répéter indéfiniment un remplacement textuel qui échoue.
- Relire le fichier lorsque son état est incertain.
- Vérifier les modifications réelles avant de les annoncer.
- Ne pas considérer un diff théorique comme une mutation effectuée.

Ne supprime ni n'affaiblis une barrière technique sous prétexte d'améliorer la fluidité.

**Le contrat doit compléter OpenHands, pas entrer en conflit avec son fonctionnement interne.**

Vérifie la compatibilité réelle avec les appels d'outils.

---

# 19. OPTIMISATION DU CONTRAT VÉTÉRINAIRE

Le contrat Vétérinaire doit offrir une qualité équivalente dans deux grandes catégories :

**A. Pédagogie**

- Clarté.
- Terminologie scientifique.
- Progression des explications.
- Exercices.
- Questions-réponses.
- Corrections.
- Synthèses.
- Adaptation au niveau.

**B. Raisonnement clinique**

- Identification de l'espèce.
- Raisonnement différentiel.
- Reconnaissance des informations manquantes.
- Fiabilité scientifique.
- Interprétation des résultats.
- Identification des urgences.
- Gestion des incertitudes.
- Prudence dans les décisions réelles.

Ne privilégie pas exclusivement l'apprentissage au détriment du raisonnement clinique.

Ne privilégie pas exclusivement le raisonnement clinique au détriment de la pédagogie.

Le même modèle doit s'adapter naturellement à la requête.

Ne force pas une question-réponse pédagogique si l'utilisateur demande simplement une analyse clinique.

Ne force pas une analyse clinique complète si l'utilisateur veut seulement une définition.

Recherche un équilibre entre précision, profondeur et concision.

---

# 20. OPTIMISATION TECHNIQUE DES PROMPTS

Examine les possibilités d'amélioration réellement compatibles avec notre architecture :

- Ordre d'assemblage des instructions.
- Gestion des rôles système et utilisateur.
- Template de conversation.
- Paramètres de raisonnement.
- Température et génération, lorsque justifiés.
- Gestion des réponses incomplètes.
- Gestion des limites de contexte.
- Injection de mémoire.
- Instructions spécifiques aux outils.
- Détection d'une capacité indisponible.
- Réduction des instructions redondantes.
- Préservation de la priorité des règles.

Ne change pas dix paramètres simultanément sans pouvoir mesurer l'effet.

N'ajoute pas une couche supplémentaire de prompts si la structure actuelle suffit.

Ne reproduis pas inutilement les mêmes règles dans le contrat global et chaque profil.

Ne cherche pas à faire produire artificiellement de longues chaînes de raisonnement.

La qualité des réponses doit être vérifiée par le résultat, pas par le nombre de tokens générés.

---

# 21. COMPARAISON AVANT / APRÈS

Après optimisation, rejoue les scénarios de référence.

L'objectif est de comparer les contrats sur les mêmes tâches et, autant que possible, avec les mêmes réglages.

Compare :

- Exactitude.
- Pertinence.
- Respect des instructions.
- Gestion des incertitudes.
- Fiabilité des outils.
- Qualité du français.
- Profondeur lorsque nécessaire.
- Concision lorsque demandée.
- Temps de réponse.
- Nombre de tokens d'instructions.
- Risques et hallucinations.
- Comportement clinique prudent.
- Qualité des corrections pédagogiques.

Documente séparément les résultats des tests déterministes et les évaluations qualitatives.

Ne prétends pas que 100 % d'une série de tests automatisés prouve l'exactitude scientifique de tous les résultats.

Si un contrat optimisé produit de moins bons résultats sur un domaine important, corrige-le ou rétablis localement l'ancienne formulation.

**Ne conserve pas une modification simplement parce qu'elle est plus récente.**

Conserve les améliorations démontrées et les changements justifiés par une meilleure clarté, même si les gains qualitatifs ne peuvent pas être chiffrés parfaitement.

---

# 22. TESTS AUTOMATISÉS ET NON-RÉGRESSION

L'étape 15 doit préserver les quatorze étapes précédentes.

Exécute les tests pertinents du dépôt, notamment :

- Tests backend.
- Tests frontend.
- Build TypeScript/Vite.
- Validation du registre.
- Tests de configuration.
- Tests de profils.
- Tests de commutation.
- Tests SQLite.
- Tests mémoire.
- Tests de conversations.
- Tests de suppression de conversations.
- Tests de paramètres.
- Tests OpenHands.
- Tests de sécurité et permissions.
- Tests de checkpoints et rollback.
- Tests vocaux.
- Tests de surveillance.
- Tests de lancement et arrêt.
- `git diff --check`.

Ajoute des tests ciblés pour le troisième profil.

Vérifie le comportement lorsque :

- Le fichier GGUF manque.
- Un chemin de modèle est invalide.
- Le modèle ne démarre pas.
- Le contexte est invalide.
- Le GPU ne dispose pas d'assez de mémoire.
- Un profil est changé pendant une activité.
- Le backend est redémarré.
- Un paramètre est modifié puis rechargé.
- Une conversation vétérinaire est supprimée.

Les tests doivent correspondre aux contrats réels de l'application.

Ne masque pas un échec de test en modifiant l'assertion simplement pour obtenir du vert.

Corrige la cause.

---

# 23. TESTS RÉELS DE BOUT EN BOUT

Au-delà des mocks et tests isolés, vérifie au minimum un cycle réel du nouveau profil :

1. Démarrer Léa.
2. Sélectionner Vétérinaire.
3. Charger réellement Qwen3.5-9B.
4. Envoyer une question pédagogique.
5. Recevoir une réponse réelle.
6. Envoyer un cas clinique théorique.
7. Recevoir une réponse réelle.
8. Vérifier l'historique.
9. Tester une mémoire explicite dans un environnement de test isolé.
10. Vérifier les paramètres.
11. Passer à Général.
12. Revenir à Vétérinaire.
13. Arrêter Léa.
14. Vérifier la libération des ressources.

Teste également le fonctionnement conversationnel avec les moteurs de voix disponibles si l'environnement le permet.

N'utilise pas les conversations utilisateur pour les tests destructifs.

Lorsque des tests réels nécessitent la création de données temporaires, nettoie-les sans toucher aux données existantes.

Ne considère pas que la validation automatisée remplace les essais physiques de l'utilisateur.

---

# 24. DOCUMENTATION ET ROADMAP

Mets à jour les fichiers appropriés :

- `AGENTS.md`
- `README.md`
- `TODO.md`
- `CHANGELOG.md`
- `docs/DECISIONS.md`
- La documentation du registre.
- La documentation des profils.
- La documentation des contrats.
- Un rapport de validation dédié à l'étape 15.

Utilise les noms et emplacements réels du dépôt.

Documente :

- Le nouveau profil.
- Son modèle et sa quantification.
- Son contexte.
- Ses réglages de raisonnement.
- Son fonctionnement vocal.
- Ses limites cliniques.
- Les protections existantes.
- La stratégie d'optimisation des contrats.
- Les résultats comparatifs avant/après.
- Les performances.
- Les tests.
- Les limites connues.

Actualise la roadmap pour refléter les décisions confirmées :

- Étapes 1 à 14 terminées.
- Étape 15 : Vétérinaire et optimisation des contrats.
- Étape 16 : Accès Web.
- Vision suspendue et reportée.
- Auxiliaire supprimé définitivement.

Préserve les autres objectifs existants sans inventer une réorganisation supplémentaire.

N'ajoute aucune étape « bis ».

---

# 25. NETTOYAGE FINAL

Après les tests et les modifications :

- Supprime les caches régénérables créés par cette intervention.
- Supprime les fichiers temporaires de test inutiles.
- Préserve les environnements de production.
- Préserve les modèles.
- Préserve les fichiers de configuration.
- Préserve les preuves historiques utiles.
- Préserve les checkpoints.
- Préserve les conversations et mémoires.
- Préserve les ressources vocales.
- Préserve les laboratoires GLM et Ovis.
- Préserve les données OpenHands.

Ne supprime pas un fichier si son inutilité n'est pas démontrée.

Le modèle vétérinaire doit rester hors de Git.

Léa ne doit pas laisser inutilement des processus actifs ou de la VRAM occupée après l'arrêt.

---

# 26. RAPPORT FINAL OBLIGATOIRE

Présente un rapport détaillé avec l'un des verdicts suivants :

- `ETAPE_15_VALIDATION_MANUELLE_REQUISE`
- `ETAPE_15_PARTIELLE`
- `ETAPE_15_BLOQUEE`

Le premier verdict signifie que l'intégration et les tests réalisables par Codex ont réussi, mais qu'une validation physique par l'utilisateur est encore nécessaire.

Ne déclare pas l'étape complètement terminée à ma place.

## A — Intégration

- Modèle détecté.
- SHA-256.
- Chemin.
- Quantification.
- Runtime.
- Registre.
- Profil ajouté.
- Frontend.
- Backend.
- Paramètres.
- Voix.
- Conversations.
- Mémoire.

## B — Performances

- Temps de démarrage du modèle.
- RAM consommée.
- VRAM consommée.
- Vitesse de génération.
- Temps de réponse.
- Contexte utilisé.
- Comportement lors des changements de profil.
- Arrêt et libération des ressources.

## C — Vétérinaire

- Résultats pédagogiques.
- Résultats de raisonnement clinique.
- Qualité des réponses en français.
- Capacité à reconnaître les incertitudes.
- Limites identifiées.
- Erreurs scientifiques importantes détectées.
- Tests de sécurité.

## D — Optimisation des contrats

Pour chaque contrat :

- État initial.
- Problèmes détectés.
- Modifications effectuées.
- Justifications.
- Tokens avant/après lorsque mesurables.
- Résultats de comparaison.
- Régressions détectées.
- Régressions corrigées.
- Éventuelles limitations.

Explique pourquoi les nouveaux contrats sont meilleurs ou plus cohérents, et indique les cas où le gain n'est pas objectivement démontré.

## E — Non-régression

- Nombre de tests backend.
- Nombre de tests frontend.
- Build.
- PowerShell.
- Général.
- Programmation.
- Vétérinaire.
- OpenHands.
- Voix.
- Mémoire.
- SQLite.
- Paramètres.
- Surveillance.
- Sécurité.
- Démarrage/arrêt.

## F — État final

- Frontend.
- Backend.
- Modèles actifs ou arrêtés.
- Docker.
- OpenHands.
- Workers vocaux.
- Workspace.
- SQLite.
- Processus résiduels.
- Fichiers temporaires.

## G — Git

- Fichiers modifiés.
- Fichiers ajoutés.
- Fichiers supprimés.
- `git status`.
- `git diff --check`.
- Vérification des gros fichiers et secrets.
- Confirmation qu'aucun modèle GGUF n'est ajouté à Git.
- Confirmation qu'aucun commit ni push n'a été réalisé.

## H — Validation manuelle

Fournis une courte procédure de tests utilisateur, réalisable depuis le frontend dans Microsoft Edge autonome.

Propose des vérifications simples et successives :

- Présence du troisième profil.
- Chargement du modèle.
- Question pédagogique.
- Cas clinique.
- Changement de profil.
- Mémoire.
- Voix.
- Paramètres.

Ne demande pas à l'utilisateur de réaliser des tests techniques complexes si les vérifications peuvent être effectuées par Codex.

---

# 27. CRITÈRES DE RÉUSSITE

L'étape 15 sera prête pour ma validation manuelle lorsque :

1. Le profil Vétérinaire apparaît dans le frontend.
2. Il utilise réellement Qwen3.5-9B Q4_K_M.
3. Le modèle fonctionne localement.
4. Général et Programmation restent inchangés et fonctionnels.
5. Les transitions entre les trois profils sont fiables.
6. L'historique et la mémoire fonctionnent.
7. Le centre de paramètres prend en charge le nouveau profil.
8. Les options de raisonnement exposées ont un effet réel.
9. La dictée et la conversation vocale sont compatibles.
10. Le profil est utile à l'apprentissage vétérinaire.
11. Le profil est utile au raisonnement clinique théorique.
12. Il reconnaît ses incertitudes et ses limites.
13. Les contrats Général, Programmation et Vétérinaire ont été analysés et optimisés.
14. Le contrat global est cohérent et sans contradictions majeures.
15. Les optimisations ont été comparées aux comportements précédents.
16. Les protections existantes n'ont pas été affaiblies.
17. Tous les tests pertinents passent.
18. Le système démarre et s'arrête proprement.
19. Aucun fichier personnel, modèle, checkpoint ou donnée historique n'a été supprimé sans autorisation.
20. Aucun commit ni push n'a été fait.

**Rappel final :**

Nous cherchons une Léa plus performante, cohérente et fiable, pas simplement des contrats plus longs ou une accumulation de nouvelles fonctionnalités.

Priorise les résultats mesurables, la robustesse et la simplicité.

Effectue d'abord l'intégration vétérinaire, puis seulement l'optimisation générale des contrats.

N'entame pas l'étape 16 — Web.

À la fin, fournis ton rapport complet et arrête-toi pour ma validation.