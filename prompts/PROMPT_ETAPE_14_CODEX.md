# PROMPT CODEX — ÉTAPE 14 : MICROPHONE ET CONVERSATION VOCALE

## Objectif général

Tu dois réaliser **l'étape 14 de Projet Léa : Microphone, transcription vocale locale et conversation vocale avec réponses orales**.

Projet principal :

`L:\Projet_Lea`

Les étapes 1 à 13 ont déjà été développées. L'étape 13 a été validée manuellement, puis finalisée par l'utilisateur.

Tu connais déjà l'architecture, le fonctionnement de Léa et les conventions du projet. Ne reconstruis pas son historique et ne recommence pas les étapes précédentes.

**L'objectif est de permettre à l'utilisateur de parler à Léa grâce à deux boutons distincts :**

1. **Microphone de dictée** : enregistrer la voix et insérer une transcription modifiable dans le champ de question habituel.
2. **Conversation vocale** : ouvrir une interface dédiée, sans afficher les messages écrits, permettant de parler à Léa et d'entendre ses réponses.

Les deux fonctionnalités doivent fonctionner entièrement en local, sans API distante, et être utilisables avec les profils Général et Programmation.

La priorité est d'obtenir un système **complet, réellement utilisable, stable, suffisamment rapide et peu gourmand en ressources**.

---

# 1. CONSIGNES OBLIGATOIRES AVANT MODIFICATION

Lis et examine les fichiers pertinents du dépôt, notamment :

- `AGENTS.md`
- `README.md`
- `TODO.md`
- `CHANGELOG.md`
- `docs/DECISIONS.md`
- Le rapport de validation de l'étape 13.
- L'architecture frontend React/Vite.
- Les composants de conversation et de saisie des messages.
- Le centre de paramètres de l'étape 12.
- Le registre central des modèles et les profils.
- Le fonctionnement du backend FastAPI et des contrôleurs locaux.
- Le système de démarrage/arrêt de Léa.
- La persistance des conversations et des messages.
- La surveillance des ressources de l'étape 13.
- Les mécanismes de sécurité et d'autorisation du profil Programmation.
- Les tests frontend et backend existants.

Vérifie également l'état Git :

```powershell
git status
git diff --check
git log -1 --oneline
```

Protège les modifications locales éventuelles.

## Interdictions

- Aucun commit.
- Aucun push.
- Aucun reset destructif.
- Aucun rebase.
- Aucun `git clean`.
- Aucune suppression de données utilisateur.
- Aucune suppression de checkpoints.
- Aucune modification des poids Qwen existants.
- Aucun remplacement des modèles Général et Programmation.
- Aucune refonte générale de l'interface.
- Aucun service de transcription ou de synthèse vocale sur Internet.
- Aucune télémétrie externe.
- Aucun microphone actif en permanence.
- Aucun contournement des mécanismes de sécurité d'OpenHands.
- Aucun nouveau moteur de conversation.
- Aucune nouvelle base de données de conversation indépendante.

Les autres fonctionnalités existantes de Léa doivent rester intactes.

---

# 2. PÉRIMÈTRE EXACT DE L'ÉTAPE 14

L'étape comprend :

- Capture du microphone.
- Dictée vocale avec transcription.
- Reconnaissance du français.
- Interface dédiée de conversation vocale.
- Transcription des demandes vocales.
- Génération d'une réponse avec le modèle actif.
- Synthèse vocale locale des réponses.
- Lecture sonore.
- Interruption de la lecture.
- Paramètres microphone et audio.
- Gestion des erreurs.
- Gestion de la mémoire et des processus vocaux.
- Intégration à l'historique existant.
- Compatibilité Général et Programmation.
- Tests réels sur Windows.

## Hors périmètre

Ne réalise PAS :

- Vision ou compréhension d'images.
- Génération d'images.
- Modification des modèles pour devenir multimodaux.
- Navigation Internet.
- Reconnaissance vidéo.
- Conversation vocale permanente et mains libres.
- Détection automatique de la fin de parole.
- Activation par mot-clé, par exemple « Hé Léa ».
- Microphone toujours à l'écoute.
- Détection permanente de l'environnement sonore.
- Clonage de voix.
- Conversation simultanée où l'utilisateur et Léa peuvent parler en même temps.
- Nouveau système agentique.
- Refonte complète de l'interface.

**La détection automatique de fin de parole et la conversation mains libres seront traitées plus tard, notamment à l'étape 19.**

---

# 3. ARCHITECTURE VOCALE

Léa doit conserver son architecture indépendante des modèles.

Schéma attendu :

```text
                      LÉA
                       │
             ┌─────────┴──────────┐
             │                    │
        Dictée vocale        Mode conversation
             │                    │
         Microphone            Microphone
             │                    │
           STT local           STT local
             │                    │
       Champ de saisie       Message utilisateur
             │                    │
      Envoi traditionnel      Modèle actif
                                  │
                             Réponse texte
                                  │
                               TTS local
                                  │
                              Haut-parleurs
```

Le moteur STT doit être partagé logiquement entre les deux fonctionnalités.

Le moteur TTS ne doit pas nécessiter de modification structurelle des modèles Qwen.

Les moteurs vocaux doivent être remplaçables, à l'image des modèles conversationnels.

Évite cependant de construire un système universel de plugins vocaux si cela n'est pas nécessaire.

Privilégie des interfaces simples, clairement séparées :

- Capture audio.
- Transcription STT.
- Génération de réponse existante.
- Synthèse TTS.
- Lecture sonore.
- Gestion du cycle de vie.

Ne crée pas de services lourds supplémentaires sans justification.

---

# 4. 14A — AUDIT TECHNIQUE ET CHOIX DES MOTEURS

Avant de développer, examine les contraintes réelles de l'ordinateur et du projet.

## Environnement

- Windows 11.
- Application React/Vite avec backend Python.
- Modèles locaux utilisant llama.cpp.
- Profil Général.
- Profil Programmation avec OpenHands.
- Docker Desktop éventuellement actif.
- Surveillance des ressources déjà implémentée.
- Ressources RAM/VRAM limitées.

Pendant un précédent run Programmation, environ 26 Gio de RAM sur 31,7 Gio étaient utilisés.

**Il est interdit de réduire automatiquement le contexte de Programmation pour faire fonctionner les moteurs vocaux.**

## Moteur STT

Évalue les solutions locales pertinentes, notamment celles de la famille Whisper :

- whisper.cpp ;
- faster-whisper ;
- autre moteur local si réellement mieux adapté.

Compare :

- Qualité de transcription en français.
- Précision sur des mots techniques.
- Utilisation CPU.
- Utilisation RAM.
- Utilisation VRAM.
- Temps de chargement.
- Latence de transcription.
- Facilité d'intégration.
- Maintenance.
- Licence.
- Taille des poids.
- Fonctionnement entièrement hors ligne.

Ne sélectionne pas automatiquement le modèle le plus gros.

## Moteur TTS

Évalue les solutions locales pertinentes, notamment :

- Piper ;
- Kokoro, si une voix française compatible est disponible ;
- autre moteur local approprié.

Compare :

- Qualité réelle de la voix française.
- Prononciation du français.
- Naturel de la voix.
- Consommation CPU/RAM/VRAM.
- Temps de génération.
- Taille des modèles.
- Fiabilité sous Windows.
- Licence.
- Simplicité d'intégration.

Une voix française claire, naturelle et fiable est préférable à un système techniquement impressionnant mais lourd.

## Téléchargement des modèles vocaux

Les poids vocaux ne sont pas les poids Qwen.

Tu peux proposer l'installation des moteurs et modèles vocaux nécessaires à cette étape, mais :

- Identifie les fichiers exacts.
- Vérifie leur provenance et leur licence.
- Indique leur taille approximative.
- Ne remplace aucun modèle existant.
- N'ajoute pas de gros fichiers binaires au dépôt Git.
- N'effectue pas de téléchargement volumineux sans présenter le choix à l'utilisateur et obtenir son accord.
- Vérifie que l'installation initiale peut être suivie d'un fonctionnement entièrement hors ligne.

Le fonctionnement normal de Léa ne doit jamais dépendre du téléchargement automatique de poids vocaux.

## Résultat attendu

Choisis une solution STT et une solution TTS adaptées au PC actuel.

Explique techniquement les choix.

Si plusieurs options sont proches, privilégie la moins coûteuse en ressources à qualité acceptable.

Si un choix nécessite un téléchargement important ou une nouvelle dépendance lourde, présente-le avant installation.

---

# 5. 14B — CAPTURE DU MICROPHONE

Intègre la capture du microphone à l'application frontend existante.

## Exigences

- Utiliser les API de capture audio adaptées au navigateur local.
- Demander l'autorisation microphone uniquement lorsque nécessaire.
- Ne pas enregistrer avant une action explicite.
- Ne pas activer le microphone au lancement de Léa.
- Arrêter réellement la capture lorsque l'utilisateur termine.
- Libérer les pistes audio et les ressources.
- Gérer les changements de périphérique.
- Gérer les permissions refusées.
- Gérer l'absence de microphone.
- Gérer les enregistrements vides.
- Gérer les périphériques déconnectés.
- Gérer les erreurs d'encodage.
- Éviter les enregistrements excessivement longs.

Léa est actuellement une application locale. La capture doit fonctionner correctement avec son adresse et son mécanisme de lancement actuels.

Ne contourne pas les permissions normales du navigateur.

## États recommandés

```text
IDLE
RECORDING
TRANSCRIBING
READY
ERROR
```

Adapte cette liste si le code existant justifie une structure différente.

Les changements d'état doivent être explicites et correctement gérés.

## Confidentialité

L'enregistrement doit rester local.

Ne conserve pas les fichiers audio bruts par défaut.

Utilise des données temporaires en mémoire ou des fichiers temporaires maîtrisés si nécessaire.

Nettoie-les après traitement, annulation ou erreur.

Ne conserve pas des enregistrements privés simplement pour faciliter le débogage.

---

# 6. 14C — PREMIER BOUTON : DICTÉE VOCALE

Dans l'interface habituelle des conversations, ajoute un bouton microphone près de la saisie du message.

Visuellement, inspire-toi du principe du microphone de ChatGPT, sans reproduire nécessairement toute son interface.

## Fonctionnement exact

**Premier clic :**

- Demander l'accès au microphone si nécessaire.
- Commencer l'enregistrement.
- Afficher clairement que Léa écoute.

**Deuxième clic :**

- Arrêter l'enregistrement.
- Transmettre l'audio au moteur STT local.
- Attendre la transcription.
- Insérer le texte transcrit dans la zone « Votre question ».

Après transcription :

- L'utilisateur peut corriger le texte.
- L'utilisateur peut ajouter du texte.
- L'utilisateur clique sur Envoyer normalement.
- Aucun envoi automatique.

**Dans ce mode, Léa ne répond pas oralement.**

Il s'agit uniquement d'un moyen plus pratique de rédiger une question.

## Texte préexistant

Si le champ contient déjà du texte avant la dictée, ne l'efface pas.

Ajoute la transcription de manière prévisible, avec un espacement approprié, en préservant les modifications manuelles.

Évite de remplacer silencieusement le contenu du champ.

## Annulation

Prévois un moyen simple d'annuler l'enregistrement ou une transcription en cours.

Une annulation ne doit pas envoyer de message ni modifier les fichiers du projet.

## Cas d'erreur

- Microphone indisponible.
- Permission refusée.
- Enregistrement vide.
- Transcription échouée.
- Modèle STT indisponible.
- Interruption utilisateur.
- Enregistrement trop long.

Affiche un message compréhensible.

Ne fabrique jamais une transcription lorsque le moteur a échoué.

---

# 7. 14D — DEUXIÈME BOUTON : CONVERSATION VOCALE

Ajoute un deuxième bouton, distinct du microphone de dictée.

Ce bouton doit être facilement identifiable et visuellement différent.

Le principe voulu est similaire aux deux boutons vocaux de ChatGPT :

- Microphone simple pour dicter.
- Bouton de conversation vocale pour ouvrir un mode dédié.

Ne confonds jamais les deux actions.

## Nouvelle interface

Lorsque l'utilisateur clique sur le bouton de conversation vocale :

**Ouvre une interface vocale dédiée, séparée de la page de conversation habituelle.**

Cette interface ne doit afficher :

- Ni les messages de l'utilisateur.
- Ni les réponses textuelles de Léa.
- Ni la transcription.
- Ni un champ de saisie textuel.
- Ni les blocs de messages habituels.

L'interface doit être centrée sur la voix.

## Présentation souhaitée

Utilise le style actuel de Léa, avec une interface sobre, propre et cohérente.

Éléments souhaités :

- Titre « Conversation vocale ».
- Animation visuelle simple ou indicateur central.
- État actuel du système.
- Bouton microphone.
- Bouton pour arrêter ou interrompre la lecture.
- Bouton pour quitter le mode vocal.

États visibles possibles :

```text
Léa est prête
Écoute en cours
Transcription
Léa réfléchit
Léa parle
Erreur
```

Les indications d'état sont autorisées.

**Le contenu textuel des conversations ne doit pas être affiché dans cette interface.**

Évite une animation complexe qui consomme inutilement CPU ou GPU.

Aucune refonte de l'interface normale de Léa n'est demandée.

---

# 8. 14E — FONCTIONNEMENT DE LA CONVERSATION VOCALE

Le fonctionnement doit être exactement le suivant.

## Démarrage

L'utilisateur ouvre l'interface vocale.

Léa attend une action.

Elle n'écoute pas automatiquement.

## Premier clic

L'utilisateur clique sur le microphone.

Léa commence à enregistrer.

Elle affiche un état d'écoute.

## Deuxième clic

L'utilisateur clique à nouveau.

Léa :

1. Arrête l'enregistrement.
2. Transcrit localement.
3. Crée le message utilisateur.
4. Transmet ce message au profil actif.
5. Attend la réponse.
6. Produit la réponse textuelle normalement.
7. Convertit la réponse en audio avec le TTS.
8. Lit l'audio.
9. Revient à l'état prêt pour la prochaine intervention.

**Il ne doit pas être nécessaire d'appuyer sur Envoyer dans ce mode.**

Le deuxième clic déclenche automatiquement le traitement du message.

## Après la réponse

Lorsque Léa a terminé de parler :

- Le microphone n'est pas réactivé automatiquement.
- Elle attend un nouveau clic.
- L'utilisateur peut démarrer une nouvelle intervention.

## Ce qui est explicitement interdit

- Enregistrement permanent.
- Détection automatique de fin de parole.
- Réponse déclenchée simplement par quelques secondes de silence.
- Conversation totalement mains libres.
- Microphone activé pendant que Léa parle, sauf nécessité technique explicitement validée.
- Plusieurs traitements concurrents pour la même intervention.

La conversation reste **tour par tour**.

Le mode mains libres sera ajouté plus tard.

---

# 9. 14F — SYNTHÈSE VOCALE ET LECTURE AUDIO

La conversation vocale doit utiliser un moteur TTS **réellement local**.

## Exigences

- Lire oralement les réponses du modèle actif.
- Produire une voix française intelligible.
- Gérer les caractères français.
- Gérer correctement la ponctuation.
- Éviter les lectures aberrantes de Markdown.
- Gérer raisonnablement les réponses longues.
- Pouvoir interrompre la lecture.
- Libérer les ressources audio ensuite.

## Réponses mixtes et techniques

Les réponses de Programmation peuvent contenir :

- Code.
- Chemins Windows.
- Logs.
- Commandes.
- Markdown.
- Messages de validation.
- Erreurs.
- Longs résultats techniques.

Le TTS ne doit pas réciter inutilement des centaines de lignes de code ou de logs.

Prévois une préparation prudente du texte destiné à la lecture, sans falsifier le contenu ni supprimer une information critique.

Le texte complet doit rester disponible dans l'historique normal de la conversation.

Si une réponse ne peut pas être lue utilement, informe l'utilisateur clairement plutôt que de prétendre l'avoir restituée intégralement.

## Interruptions

Pendant que Léa parle :

- L'utilisateur peut arrêter la lecture.
- L'arrêt doit être immédiat ou suffisamment réactif.
- Le son doit réellement s'arrêter.
- La session vocale doit rester utilisable ensuite.

Quitter le mode vocal doit arrêter la lecture et libérer les ressources audio.

Une interruption TTS ne doit pas supprimer la réponse textuelle déjà enregistrée.

---

# 10. 14G — HISTORIQUE ET PERSISTANCE

Le mode vocal ne doit pas créer un système de conversations parallèle.

## Principe

Le microphone change la manière de saisir un message.

Le TTS change la manière de restituer une réponse.

**La conversation continue d'utiliser les mécanismes existants de Léa.**

## Mode dictée

Après transcription, le message est envoyé et sauvegardé exactement comme une question saisie au clavier.

## Mode conversation vocale

Les transcriptions des demandes et les réponses textuelles doivent être enregistrées dans l'historique normal, lorsque la conversation est enregistrable selon les règles actuelles.

L'interface vocale masque ces textes pendant la session, mais ils restent consultables dans l'interface classique.

Réutilise les identifiants, sessions, conversations et mécanismes de persistance existants.

Ne double pas les messages si une génération échoue ou si l'utilisateur quitte l'interface.

Ne crée pas une base de données vocale séparée.

## Audio

Ne conserve pas automatiquement les enregistrements originaux ni les fichiers audio générés.

Ils peuvent être temporaires et supprimés après utilisation.

Ne stocke pas des données audio lourdes dans SQLite sans nécessité.

---

# 11. 14H — COMPATIBILITÉ DES PROFILS ET SÉCURITÉ

Les deux modes doivent fonctionner avec :

- Général.
- Programmation.

Et rester compatibles avec le remplacement futur des modèles.

## Général

La transcription passe au modèle Général normalement.

La réponse peut être lue oralement dans le mode de conversation vocale.

Les préférences de raisonnement Low/High existantes doivent être conservées.

## Programmation

Les messages vocaux passent par les mécanismes normaux du profil Programmation.

**Il est interdit de contourner les protections existantes simplement parce que la demande provient du microphone.**

Conserve notamment :

- Autorisations de workspace.
- Exécution via OpenHands.
- Limites d'accès aux fichiers.
- Checkpoints.
- Validation.
- Acceptation.
- Rollback.
- Gestion des erreurs.
- États des runs.
- Confirmation des opérations sensibles.

## Point de sécurité essentiel

Certaines actions du profil Programmation peuvent nécessiter une confirmation ou une vérification visuelle.

Le mode vocal ne doit pas accepter silencieusement une modification dangereuse pour éviter d'afficher du texte.

Si une action nécessite une approbation explicite, prévois un mécanisme sûr :

- Une notification vocale compréhensible.
- Et, si des détails techniques doivent être examinés, une transition explicite vers l'interface de validation existante.

Ne déclenche jamais automatiquement une acceptation ou un rollback non autorisé.

Ne masque pas un état d'échec à l'utilisateur.

Le mode vocal peut cacher les messages écrits, mais il ne doit jamais cacher une décision de sécurité obligatoire.

## Modèle non démarré

Si aucun profil n'est prêt à répondre :

- La dictée doit fonctionner si son moteur STT local est disponible.
- Le mode conversation vocale doit expliquer qu'un profil doit être démarré.
- Aucun démarrage implicite d'un profil lourd n'est demandé.

## Changements de profil

Gère correctement :

- Changement de profil pendant une session.
- Arrêt d'un modèle.
- Déconnexion du backend.
- Fermeture de l'interface vocale.
- Run OpenHands encore actif.

Évite les sessions incohérentes et les réponses envoyées au mauvais profil.

---

# 12. 14I — PARAMÈTRES DU MICROPHONE ET DE LA VOIX

L'étape 12 a établi un centre de paramètres centralisé et persistant.

Réutilise cette architecture.

## Paramètres souhaités

### Microphone

- Choix du microphone si plusieurs périphériques sont disponibles et si cela peut être fait de manière fiable.
- Sensibilité ou niveau d'entrée, uniquement si le réglage a un effet réel.
- Langue de transcription, avec français par défaut.
- Éventuellement autodétection si correctement prise en charge.

### Synthèse vocale

- Activation du moteur vocal dans le mode conversation.
- Choix de la voix parmi les voix réellement installées.
- Volume.
- Vitesse de lecture, si prise en charge sans compromettre la qualité.

### Moteurs

Afficher les moteurs STT/TTS sélectionnés et leur état si cela est utile.

Ne crée pas de faux sélecteurs pour des modèles ou des voix indisponibles.

## Persistance

Les réglages applicables doivent être conservés après redémarrage.

Ne modifie pas directement `config/models.json` pour stocker des préférences utilisateur.

Réutilise le mécanisme approprié déjà établi à l'étape 12.

## Principes

- Valeurs initiales raisonnables.
- Pas de réglage qui ne fonctionne pas.
- Pas de dépendance inutile au modèle Général.
- Pas de dépendance inutile au profil Programmation.
- Validation backend des réglages.
- Gestion explicite des valeurs indisponibles.

---

# 13. 14J — PERFORMANCES ET GESTION DES RESSOURCES

C'est une exigence majeure de cette étape.

## Contexte

Le profil Programmation utilise déjà beaucoup de RAM.

Il ne faut pas sacrifier les capacités du modèle principal simplement pour ajouter la voix.

## Exigences

- Éviter de garder un gros modèle STT chargé inutilement en permanence.
- Éviter de garder plusieurs moteurs TTS concurrents.
- Réutiliser les moteurs chargés lorsque cela améliore réellement la latence sans surcharge excessive.
- Libérer les ressources lors d'un arrêt complet.
- Éviter les processus orphelins.
- Éviter les doubles chargements.
- Éviter les threads bloqués.
- Éviter les fuites mémoire.
- Éviter les fichiers audio temporaires abandonnés.
- Ne pas faire tourner une analyse audio lorsque le microphone est inactif.

## CPU et GPU

Privilégie une configuration qui fonctionne correctement sur la machine actuelle.

Si le GPU est déjà utilisé par Qwen, évalue si le STT/TTS doit fonctionner principalement sur CPU.

Ne force pas le GPU si cela provoque une saturation de VRAM ou une instabilité.

## Mesures obligatoires

Mesure au minimum :

- RAM supplémentaire au repos.
- RAM pendant transcription.
- RAM pendant synthèse.
- VRAM supplémentaire.
- CPU.
- Temps de chargement STT.
- Temps de transcription pour plusieurs durées d'enregistrement.
- Temps de démarrage TTS.
- Temps avant le début de la lecture vocale.
- Temps total d'un échange vocal.

Réalise les essais avec Général et Programmation lorsque c'est techniquement possible.

## Surveillance des ressources

Le mécanisme de l'étape 13 doit rester opérationnel.

Les moteurs vocaux ne doivent pas nécessiter une seconde surveillance générale indépendante.

Réutilise l'architecture existante pour les diagnostics appropriés.

## Critère de performance

Je ne fixe pas de seuil arbitraire à l'avance.

Je veux des résultats mesurés et un compromis réellement utilisable entre qualité, rapidité et consommation.

Si le moteur choisi est trop lourd, teste une alternative adaptée avant de conclure.

---

# 14. 14K — TESTS, QUALITÉ ET DOCUMENTATION

Cette phase doit démontrer que les deux modes fonctionnent réellement.

## Tests du microphone

- Autorisation accordée.
- Autorisation refusée.
- Microphone absent.
- Microphone déconnecté.
- Démarrage.
- Arrêt.
- Annulation.
- Enregistrement vide.
- Enregistrement long.
- Nettoyage des ressources.

## Tests de dictée

- Premier clic : enregistrement.
- Deuxième clic : arrêt.
- Transcription française réelle.
- Texte correctement inséré.
- Texte préexistant préservé.
- Modification manuelle.
- Envoi traditionnel.
- Aucun envoi automatique.
- Gestion des erreurs.

## Tests du mode vocal

- Ouverture de l'interface dédiée.
- Absence des messages écrits dans cette interface.
- Premier clic : écoute.
- Deuxième clic : transcription et traitement.
- Réponse réelle du modèle.
- Génération audio locale.
- Lecture dans les haut-parleurs.
- Interruption de lecture.
- Nouvelle intervention.
- Fermeture du mode.
- Arrêt du microphone.
- Nettoyage.

## Tests de conversation

- Utilisation avec Général.
- Utilisation avec Programmation.
- Historique préservé.
- Conversation rechargée.
- Absence de messages dupliqués.
- Aucun changement de modèle involontaire.
- Arrêt/redémarrage.
- Gestion d'un backend indisponible.

## Tests de sécurité

- Aucun envoi audio sur Internet.
- Aucune API vocale distante.
- Aucun téléchargement pendant le fonctionnement normal.
- Aucun microphone permanent.
- Aucun enregistrement conservé sans raison.
- Aucun accès arbitraire au système hôte.
- Aucune acceptation automatique de modifications sensibles.
- Aucun contournement d'OpenHands.
- Aucune dégradation des protections des projets.

## Tests de non-régression

Conserve le fonctionnement de :

- Général.
- Programmation.
- OpenHands.
- Mémoire.
- Historique.
- Paramètres.
- Surveillance des ressources.
- Alertes.
- Diagramme RAM/CPU/VRAM.
- Checkpoints.
- Acceptation.
- Rollback.
- Gestion Docker.
- Gestion des modèles.
- Lancement et arrêt de Léa.

Exécute les suites backend/frontend pertinentes, le build et les validations PowerShell nécessaires.

Les tests simulés doivent être clairement distingués des essais réels de microphone et de haut-parleurs.

Si le microphone physique ou la sortie sonore ne peut pas être vérifié automatiquement dans ton environnement, ne prétends pas l'avoir testé : prépare une procédure de validation manuelle simple pour l'utilisateur.

## Qualité du code

Conserve les standards des étapes précédentes :

- Code lisible.
- Fonctions clairement séparées.
- Espacement et indentation cohérents.
- Commentaires techniques utiles.
- Docstrings pour les fonctions significatives.
- Gestion explicite des erreurs.
- Aucun code mort.
- Aucun doublon inutile.
- Aucun service superflu.
- Aucune abstraction disproportionnée.

Les composants React doivent rester cohérents avec les composants et styles existants.

Ne commence pas la refonte visuelle générale prévue plus tard.

## Documentation

Mets à jour les documents concernés :

- `README.md`
- `TODO.md`
- `CHANGELOG.md`
- `AGENTS.md`, si nécessaire.
- `docs/DECISIONS.md`, si présent.
- Documentation backend/frontend pertinente.

Documente :

- Les deux modes vocaux.
- Le fonctionnement du microphone.
- Les moteurs STT/TTS retenus.
- Leur installation.
- Leurs licences.
- Leur consommation.
- Les paramètres.
- Les limitations.
- Le comportement hors ligne.
- La conservation des conversations.
- Les protections du profil Programmation.
- Les essais réalisés.

Ne change pas la numérotation des prochaines étapes sans demande de l'utilisateur.

---

# 15. 14L — VALIDATION FINALE ET ARRÊT

Une fois l'implémentation terminée :

1. Relis les modifications.
2. Vérifie qu'aucune fonctionnalité antérieure n'est cassée.
3. Exécute les tests finaux.
4. Vérifie les nouveaux paramètres.
5. Vérifie les processus vocaux.
6. Vérifie le nettoyage des fichiers temporaires.
7. Vérifie l'état des données utilisateur.
8. Vérifie les artefacts et fichiers Git.
9. Arrête les services lancés exclusivement pour les tests.
10. Fournis un rapport final.

N'arrête pas arbitrairement des services étrangers au projet.

Ne supprime pas les modèles, historiques, checkpoints ou préférences.

Exécute :

```powershell
git status
git diff --check
```

Aucun commit ni push.

---

# 16. CONDITIONS DE RÉUSSITE

L'étape 14 est réussie lorsque les conditions suivantes sont remplies :

**Dictée**

- Le microphone fonctionne.
- L'utilisateur peut enregistrer par deux clics.
- La voix est transcrite localement.
- Le texte apparaît dans la zone de question.
- Le texte reste modifiable.
- L'envoi reste manuel.

**Conversation vocale**

- Un deuxième bouton ouvre une nouvelle interface.
- Aucun message écrit n'est affiché dans cette interface.
- L'utilisateur parle avec deux clics.
- Sa voix est transcrite localement.
- Le modèle actif produit une réponse.
- Cette réponse est lue oralement par un moteur TTS local.
- La lecture peut être interrompue.
- Une nouvelle intervention peut commencer.
- Les conversations restent intégrées à l'historique existant.

**Architecture et sécurité**

- Compatible Général et Programmation.
- Modèles Qwen inchangés.
- Aucune API externe.
- Aucune écoute permanente.
- Ressources correctement libérées.
- Protections OpenHands préservées.
- Aucune régression significative.
- Tests réels documentés.

Si une capacité centrale n'est pas terminée, ne déclare pas l'étape réussie.

---

# 17. RAPPORT FINAL OBLIGATOIRE

À la fin, fournis le rapport suivant.

## Verdict

Une seule valeur :

`ETAPE_14_REUSSIE`

ou

`ETAPE_14_PARTIELLE`

ou

`ETAPE_14_BLOQUEE`

## Tableau 14A à 14L

Pour chaque sous-étape :

- Statut.
- Modifications.
- Tests.
- Limitations.

## Moteurs choisis

- STT.
- Modèle STT.
- TTS.
- Voix française.
- Licences.
- Emplacement d'installation.
- Poids ou ressources téléchargés.
- Justification des choix.

## Dictée

- Fonctionnement.
- Emplacement du bouton.
- Capture.
- Transcription.
- Insertion du texte.
- Annulation.
- Tests.

## Conversation vocale

- Interface créée.
- États.
- Enregistrement.
- Transcription.
- Réponse du modèle.
- Synthèse vocale.
- Lecture.
- Interruption.
- Historique.
- Tests.

## Paramètres

- Options ajoutées.
- Valeurs par défaut.
- Persistance.
- Options réellement prises en charge.

## Performances

Présente les mesures réelles :

- RAM.
- VRAM.
- CPU.
- Temps de chargement.
- Temps de transcription.
- Temps de synthèse.
- Latence d'un échange.
- Résultats Général.
- Résultats Programmation.
- Compromis retenus.

## Sécurité

- Audio conservé ou non.
- Données temporaires.
- Fonctionnement hors ligne.
- Protection du microphone.
- Permissions OpenHands.
- Actions sensibles.
- Limitations.

## Tests

- Nombre exact de tests backend.
- Nombre exact de tests frontend.
- Résultat du build.
- Tests PowerShell.
- Tests STT réels.
- Tests TTS réels.
- Tests sur microphone physique, si possibles.
- Tests de sortie audio, si possibles.
- Tests Général.
- Tests Programmation.
- Historique.
- Paramètres.
- Non-régression.

Distingue les essais réels, les tests simulés et les vérifications restant à effectuer manuellement.

## Qualité

- Commentaires.
- Docstrings.
- Nettoyage.
- Documentation.
- Fichiers créés.
- Fichiers modifiés.
- Fichiers supprimés et justification.

## État final

- Frontend.
- Backend.
- Général.
- Programmation.
- STT.
- TTS.
- Microphone.
- Lecture audio.
- OpenHands.
- Docker.
- Ressources.
- Données utilisateur.
- Checkpoints.

## Git

- `git status`.
- `git diff --check`.
- Aucun commit.
- Aucun push.
- Aucun artefact lourd ou fichier sensible non ignoré qui pourrait être ajouté par `git add .`.

## Questions et problèmes

- Problèmes rencontrés.
- Problèmes corrigés.
- Risques résiduels.
- Fonctionnalités non terminées.
- Décisions nécessitant une validation utilisateur.

---

# 18. CONSIGNE FINALE

Je veux que Léa puisse réellement :

**1. Recevoir ma voix dans une conversation écrite, transcrire ce que j'ai dit et me laisser modifier mon message avant l'envoi.**

**2. Ouvrir une interface vocale dédiée, m'écouter lorsque j'appuie sur un bouton, traiter automatiquement mon message lorsque j'arrête l'enregistrement, puis me répondre à voix haute.**

Le tout doit fonctionner localement, préserver les modèles actuels, rester raisonnable en consommation mémoire et respecter les règles de sécurité de Léa.

Je privilégie une solution stable et naturelle à utiliser plutôt qu'une accumulation de technologies vocales complexes.

N'implémente pas encore la conversation mains libres ni la détection automatique de fin de parole.

**Termine uniquement l'étape 14, fournis ton rapport complet, puis arrête-toi pour attendre ma validation manuelle.**