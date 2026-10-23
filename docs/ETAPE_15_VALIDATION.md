# Étape 15 — Profil Vétérinaire et optimisation des contrats

Date technique : 21–22 octobre 2026  
Verdict technique : `ETAPE_15_VALIDATION_MANUELLE_REQUISE`

Ce rapport distingue les vérifications déterministes des évaluations qualitatives.
Un modèle qui produit une réponse fluide n'est pas, pour autant, une source
scientifique validée. Aucune conversation, mémoire ou base personnelle n'a été
utilisée pour les essais destructifs.

## A — Intégration

Le troisième profil `veterinary` est déclaré dans l'unique registre
`config/models.json`. Il est conversationnel, sans outil, sans workspace, sans
Web, sans vision et sans RAG. Il réutilise le backend, SQLite, l'historique, la
mémoire explicite, la surveillance et les deux moteurs vocaux déjà validés.

| Élément | Valeur vérifiée |
| --- | --- |
| Fichier | `models/veterinary/Qwen3.5-9B-Q4_K_M.gguf` |
| Taille | 5 680 522 464 octets |
| SHA-256 | `03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8` |
| Métadonnées | GGUF V3, Qwen3.5-9B, environ 8,95 milliards de paramètres |
| Quantification | Q4_K_M |
| Runtime | llama.cpp b10516 (`b95502ba9`), Jinja, mmap, GPU auto |
| Contexte Léa | 16 384 tokens, un slot, KV Q8_0, sortie maximale 4 096 tokens |
| Raisonnement | argument natif `chat_template_kwargs.enable_thinking` |
| Préférence initiale | High, indépendante du choix Général |

Le fichier reste ignoré par Git. Le modèle Qwen2.5-Coder-14B obsolète, non
référencé par le registre et ignoré par Git, a été supprimé sur demande :
10 508 873 152 octets libérés. Le Qwen2.5-Coder-7B de Programmation est conservé.

La migration SQLite 12 ajoute seulement `veterinary_reasoning`, avec contrainte
Low/High et valeur initiale High. Les mises à jour partielles, révisions,
conflits et erreurs restent communs aux autres préférences. L'écran Paramètres
affiche les modèles réellement configurés et propose deux réglages indépendants
pour Général et Vétérinaire ; Programmation ne reçoit aucun faux réglage.

Les commutations utilisent les propriétaires de processus existants. Deux
profils directs passent par le `switch-model` atomique de `lea.ps1`. Une
transition depuis ou vers Programmation arrête uniquement le propriétaire
précédent vérifié et restaure exactement ce profil si la cible échoue. Docker
Desktop et l'interface OpenHands ne sont jamais ouverts par Léa ; un conteneur
Agent Server n'apparaît qu'au lancement explicite d'un run.

## B — Performances mesurées

Les mesures sont locales et indicatives ; elles dépendent de la charge Windows
et du contenu demandé.

- chargement direct du GGUF : environ 4,2 à 6,5 s lors des essais moteur ;
- commutations Général → Vétérinaire observées : 11,83 à 27,8 s selon l'état
  chaud ou froid du runtime ; dernier aller chaud : 12,32 s ;
- dernier retour Vétérinaire → Général : 6,68 s ;
- Vétérinaire → Programmation : 26,58 s ;
- Programmation → Vétérinaire : 16,9 s ;
- démarrage complet à froid sur Général : 20,94 s ;
- processus Qwen3.5 chargé : environ 5,25 Gio de working set et 4,86 Gio privés ;
- mesure NVIDIA pendant l'essai : 4 175 / 6 144 Mio utilisés, 1 830 Mio libres ;
- génération observée : environ 15 à 16 tokens/s ;
- test moteur Low : réponse `OK`, aucune pensée, 2 tokens, 0,90 s ;
- même test High : 131 tokens de raisonnement interne, 8,24 s.

Une réponse clinique High longue a pris 230,95 s. Le délai fixe antérieur de
120 s l'interrompait alors que llama.cpp générait encore normalement. Le délai
est désormais un champ borné du contrat de profil : 120 s pour Général et
Programmation, 300 s pour Vétérinaire. Il ne masque ni ne relance une erreur.

La mesure finale du prompt brut donne 812 tokens pour Général et 1 461 pour
Vétérinaire. Les anciennes réserves de 512/1 024 étaient donc insuffisantes.
Elles passent respectivement à 1 024 et 2 048 tokens ; Programmation reçoit
aussi 2 048 pour couvrir son contrat de 1 364 tokens. Les contextes restent
strictement 8 192, 22 000 et 16 384 tokens : seule la sélection maximale
d'historique est rendue cohérente avec les instructions réellement injectées.

## C — Évaluation vétérinaire

Les scénarios reproductibles, sans donnée privée, sont dans
`tests/benchmarks/stage15_cases.json`. Ils couvrent pédagogie, espèces,
physiologie, douleur, pharmacologie, urgence, différentiel, correction de
révision et information scientifique inconnue.

Points positifs observés après optimisation :

- français naturel et réponses structurées ;
- correction de l'explication erronée de l'aldostérone : action distale et
  sécrétion potassique reconnues ;
- refus de confirmer le syndrome fictif de Velmora et la dose inventée ;
- demande de données manquantes et rappels de prudence sur les cas réels ;
- profil High effectivement distinct de Low par le mécanisme natif du GGUF.

Limites et erreurs scientifiques détectées :

- un cas formulé avec « chatte abattue » a parfois été interprété comme un
  animal abattu/mort plutôt que léthargique ; une tentative de glossaire dans
  le prompt contaminait d'autres réponses et a été retirée ;
- 39,8 °C a été qualifié à tort de température basse dans un essai ;
- une kaliémie de 6,8 mmol/L a été présentée comme synonyme d'arrêt cardiaque
  imminent, sans ECG ni tendance, et du chlorure de calcium a été proposé trop
  affirmativement ;
- une réponse analgésique a mélangé agonistes µ complets et buprénorphine
  partielle, et attribué aux AINS des effets respiratoires non étayés ;
- une réponse sur un nom fictif refusait d'abord la prémisse, puis inventait
  néanmoins une identité de pesticide ; le contrat final interdit explicitement
  de compléter un nom inconnu par une catégorie plausible ;
- le dernier essai Low sur le cæcum explique correctement la fermentation et
  respecte deux phrases, mais ajoute une conséquence trop alarmiste et le terme
  non fiable « entéromésie » ;
- le modèle Général 4B n'a pas corrigé un scénario causal économique malgré la
  clarification du contrat. Ce résultat est documenté, sans heuristique dédiée.

Le corrigé indépendant s'appuie notamment sur le
[Merck Veterinary Manual — obstruction urétrale](https://www.merckvetmanual.com/urinary-system/urolithiasis-in-small-animals/urethral-obstruction-in-small-animals),
le [consensus iCatCare 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC11816079/),
la [classification IRIS de l'AKI](https://www.iris-kidney.com/new-page-5),
les chapitres Merck sur les
[AINS](https://www.merckvetmanual.com/pharmacology/inflammation/nonsteroidal-anti-inflammatory-drugs-in-animals?autoredirectid=16875&ruleredirectid=477)
et les [analgésiques](https://www.merckvetmanual.com/therapeutics/pain-assessment-and-management/analgesics-used-in-animals?mredirectid=2810&mredirectid=310),
ainsi que les [actes AAEP sur les coliques](https://aaep.org/wp-content/uploads/2024/02/Proceedings-61st-Annual-Convention-2015.pdf).

Conclusion clinique : le profil est utile pour apprendre, organiser un cas
théorique et révéler des données manquantes, mais il ne garantit ni diagnostic,
ni posologie, ni conduite thérapeutique. Toute décision réelle exige un
vétérinaire et des sources adaptées à l'espèce, au pays et au patient. La
validation manuelle doit donc juger l'ergonomie et l'utilité, pas certifier une
exactitude médicale universelle.

## D — Audit et comparaison des contrats

L'assemblage reste unique : fiabilité commune, identité du profil, mémoire JSON
explicitement non fiable, historique SQLite, puis demande utilisateur. Aucun
prompt parallèle, parseur ou protocole OpenHands n'a été ajouté.

| Contrat | Faiblesse initiale | État final et comparaison |
| --- | --- | --- |
| Fiabilité | long mais explicite | la simplification supprimait des formulations de sécurité protégées par les tests de l'étape 10 ; contrat 1.0 entièrement rétabli |
| Général | peu explicite sur ambiguïté, causalité et niveau de détail | consignes clarifiées ; gains visibles sur concision/ambiguïté, mais aucun gain démontré sur le scénario causal complexe |
| Programmation | robuste mais redondant | la version raccourcie a échoué deux fois sur le petit run `file_editor`, contre une réussite avant modification ; elle a été entièrement rétablie |
| Vétérinaire | premier contrat fonctionnel encore trop permissif | calibration scientifique, séparation pédagogie/clinique, urgence, pharmacologie, inconnus et limites réelles renforcés |
| Mémoire | pertinence implicite | bloc à ignorer et à ne pas mentionner lorsqu'il est hors sujet ; le petit Général peut encore désobéir |

Mesures initiales du texte système avec le tokenizer des modèles : Général,
646 tokens ; Programmation, 1 364 ; Vétérinaire, 1 331. Une première passe avait
porté Général à environ 719 et Vétérinaire à environ 1 384. Les contrats commun
et Programmation ayant ensuite été rétablis, les mesures finales sont : Général
812 tokens, Programmation 1 364 et Vétérinaire 1 461. Il s'agit du prompt brut,
pas du coût du template complet de conversation.

Le run Programmation de référence, sur un projet isolé de trois fichiers, a lu
les sources, corrigé uniquement `pricing.py`, exécuté deux tests verts et fini
`completed`/`validated` en 1 min 44 s. Après raccourcissement du contrat, deux
runs ont fini `failed`/validation échouée en 86 et 97 s, la protection ayant
détecté `repetitive_file_editor_cycle`. Les deux checkpoints ont restauré les
défauts initiaux. Il n'a été ajouté aucune récupération spécialisée pour Qwen.

Limitation conservée :

> Qwen2.5-Coder-7B peut échouer sur des tâches agentiques multi-fichiers longues lorsque file_editor exige des remplacements textuels exacts. Léa détecte ces boucles, refuse les mutations invalides, valide les changements par des tests et peut restaurer le checkpoint.

## E — Non-régression

Résultats de la passe de clôture :

- backend : 261 tests réussis ;
- frontend : 41 tests réussis ;
- build TypeScript/Vite : réussi, 40 modules transformés avec Vite 7.3.6 ;
- PowerShell : les 15 scripts analysés par `Parser.ParseFile` ne contiennent
  aucune erreur de syntaxe ;
- registre : schéma, chemins, tailles, SHA-256, prompts, voix et contraintes des
  trois modèles validés par le contrôleur de configuration ;
- SQLite : migration 12, mise à jour partielle, révision optimiste, persistance
  Low/High indépendante et accès Paramètres avec l'IA arrêtée validés ;
- mémoire et conversations : création, reprise, suppression physique, mémoire
  explicite, oubli et persistance après redémarrage validés sur base isolée ;
- surveillance et voix : chemins génériques des profils conservés, tests
  automatisés réussis ; aucun nouvel essai de microphone physique revendiqué ;
- OpenHands : run réel vert `completed`/`validated`, deux régressions de prompt
  arrêtées en `failed`, puis trois rollbacks exacts ; aucun Agent Server créé à
  l'activation seule et aucun conteneur actif après les essais ;
- démarrage/arrêt : démarrage complet, commutations entre les trois profils,
  libération des ports et de la VRAM confirmés ;
- `git diff --check` : réussi après les changements fonctionnels, puis rejoué
  une dernière fois après la documentation et le nettoyage.

Les essais réels déjà accomplis confirment les trois profils, les transitions,
les préférences Low/High après redémarrage, une mémoire explicite puis son oubli,
l'historique isolé, le vrai Qwen3.5, le Qwen Coder/OpenHands, un test vert et
des rollbacks exacts. La voix partage les routes génériques existantes ; les
tests automatisés sont rejoués, mais aucun nouveau test de microphone physique
n'est revendiqué.

## F — Nettoyage et état final

Léa est arrêtée : aucun port 5173, 8000, 8080 ou 8081 n'écoute et aucun
frontend, backend, llama.cpp, worker vocal, Agent Server ou conteneur de run
n'est actif. Les caches Python créés par les tests, `dist`, la base SQLite
isolée et le projet `L:\IA_WORKSPACE\Lea_Stage15_ContractTest` ont été supprimés
après vérification de leur contenu exact. Ces suppressions sont définitives ;
elles ne concernent aucune donnée personnelle ni ressource de production.

Les deux enveloppes de conteneurs arrêtés propres aux essais échoués de l'étape
15 ont été retirées sans `-v` et sans force. Le volume persistant, l'image
épinglée, les journaux de runs sous `data/openhands-runs`, les checkpoints et
les preuves SQLite restent conservés. Les 12 anciens conteneurs arrêtés dont
l'utilité reste ambiguë sont également conservés. Aucun prune global n'a été
utilisé. Docker Desktop, ouvert manuellement par l'utilisateur, reste ouvert ;
Léa ne l'arrête pas et aucun conteneur n'y est actif.

## G — Git

Le GGUF vétérinaire et tous les autres poids restent hors Git. Le diff ne
contient ni secret détecté ni audio privé. Le prompt utilisateur de l'étape 15
est conservé comme document non suivi. Le seul fichier lourd supprimé est le
Qwen2.5-Coder-14B ignoré et explicitement retiré à la demande de l'utilisateur ;
aucun fichier suivi n'a été supprimé. `git diff --check` passe. Aucun commit ni
push n'a été réalisé.

## H — Validation manuelle dans Edge autonome

1. Démarrer Léa avec `./lea.ps1 start`, puis ouvrir `http://127.0.0.1:5173`
   dans Microsoft Edge autonome.
2. Vérifier la présence de Général, Programmation et Vétérinaire.
3. Choisir Vétérinaire et attendre l'état prêt.
4. Demander une explication pédagogique courte, par exemple le rôle du cæcum
   chez le cheval et le chien.
5. Donner un cas clinique explicitement théorique, vérifier que Léa sépare les
   données, les hypothèses, les urgences et les informations manquantes.
6. Dans Paramètres, passer Vétérinaire de High à Low, valider, poser une nouvelle
   question, puis remettre le choix désiré.
7. Enregistrer puis oublier un souvenir de test avec les commandes explicites.
8. Essayer dictée et lecture avec le microphone et la voix déjà validés.
9. Passer à Général puis revenir à Vétérinaire ; vérifier l'historique.
10. Arrêter Léa depuis l'interface ou avec `./lea.ps1 stop`.

La validation physique de la voix et l'appréciation des réponses vétérinaires
restent à l'utilisateur. L'étape 16 — Web — n'est pas commencée ; la vision
reste suspendue et le profil Auxiliaire est supprimé de la roadmap.
