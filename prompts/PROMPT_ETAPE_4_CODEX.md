# Prompt — Étape 4 du Projet Léa

Lis intégralement avant toute modification :

- `AGENTS.md`
- `README.md`
- `TODO.md`
- `docs/DECISIONS.md`
- `prompts/PROMPT_ETAPE_1_CODEX.md`
- `prompts/PROMPT_ETAPE_2_CODEX.md`
- `prompts/PROMPT_ETAPE_3_CODEX.md`

Nous commençons uniquement l’étape 4 du Projet Léa.

# Objectif

Installer et tester le premier vrai modèle local de Léa, séparément du frontend et du backend.

À la fin de cette étape, le modèle doit pouvoir recevoir une question dans le terminal et produire une réponse locale cohérente.

NE PAS connecter le modèle au backend FastAPI.
NE PAS modifier le frontend.
NE PAS commencer l’étape 5.

---

# Matériel cible

Machine actuelle :

- Windows
- Intel Core i7 13e génération
- 32 Go de RAM
- NVIDIA RTX A1000 Laptop GPU
- 6 Go de VRAM
- Projet stocké sur le SSD externe `L:`
- Python 3.12.2

Tout ce qui concerne Léa doit rester autant que possible sur :

`L:\Projet_Lea`

Ne place pas volontairement plusieurs gigaoctets de modèle ou de cache sur le disque système `C:`.

---

# Modèle imposé pour cette étape

Utilise le modèle officiel :

- Dépôt : `Qwen/Qwen3-4B-GGUF`
- Fichier : `Qwen3-4B-Q4_K_M.gguf`
- Format : GGUF
- Quantification : Q4_K_M
- Taille attendue : environ 2,5 Go
- SHA256 attendu :

`7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`

Stocke le modèle ici :

```text
models/
└── general/
    └── Qwen3-4B-Q4_K_M.gguf
```

Le fichier `.gguf` ne doit jamais être ajouté au dépôt Git.

---

# Moteur d’inférence

Utilise `llama.cpp`.

Pour cette étape :

- préfère les binaires officiels précompilés Windows x64 ;
- utilise une version avec prise en charge NVIDIA CUDA compatible avec la machine ;
- ne compile pas `llama.cpp` depuis les sources sauf impossibilité réelle ;
- n’installe pas Ollama ;
- n’installe pas Docker ;
- n’installe pas un gros environnement Python pour exécuter le modèle.

Range le runtime local dans une structure propre sous le projet, par exemple :

```text
runtime/
└── llama.cpp/
```

Les exécutables, DLL, archives téléchargées et autres binaires lourds ne doivent pas être versionnés dans Git.

---

# Vérification GPU avant installation

Avant de télécharger le runtime :

1. exécute `nvidia-smi` ;
2. confirme que la RTX A1000 est détectée ;
3. relève la version du pilote et la version CUDA indiquée ;
4. choisis le binaire officiel `llama.cpp` Windows CUDA compatible.

Si `nvidia-smi` ne fonctionne pas ou si la carte NVIDIA n’est pas détectée, ARRÊTE-TOI et explique le problème avant de télécharger quoi que ce soit.

Ne modifie pas les pilotes NVIDIA dans cette étape.

---

# Téléchargement du modèle

Télécharge directement :

`Qwen3-4B-Q4_K_M.gguf`

dans :

`models/general/`

Évite une méthode qui laisserait par défaut une seconde copie complète du modèle dans un cache situé sur `C:`.

En particulier, n’utilise pas simplement `llama-cli -hf ...` si cela entraîne un cache de plusieurs Go hors du projet.

Après téléchargement :

1. confirme que le fichier existe ;
2. indique sa taille ;
3. calcule son SHA256 ;
4. vérifie qu’il correspond exactement au SHA256 attendu.

Si le SHA256 ne correspond pas, ARRÊTE-TOI et ne lance pas le modèle.

---

# Git

Mets à jour `.gitignore` uniquement si nécessaire afin d’empêcher le versionnement :

- des fichiers `.gguf` ;
- des binaires/DLL de `llama.cpp` ;
- des archives de téléchargement temporaires ;
- des éventuels caches locaux lourds créés pour cette étape.

Ne masque pas inutilement les fichiers source du projet.

Vérifie avec `git status` qu’aucun fichier de plusieurs Go n’est prêt à être ajouté au commit.

---

# Test du modèle

Le test doit être effectué directement avec `llama.cpp`, dans le terminal.

Utilise le GPU NVIDIA avec un offload aussi complet que raisonnablement possible pour ce modèle.

Pour le premier test, reste volontairement modeste :

- contexte autour de 4096 tokens ;
- génération courte ;
- mode conversation/chat approprié au template Qwen ;
- `/no_think` pour éviter un long raisonnement pendant ce simple test.

Le test peut utiliser une question proche de :

`Réponds en français et en une seule phrase : quelle est la capitale de la France ? /no_think`

Le résultat doit être une réponse cohérente indiquant Paris.

Ne cherche pas à optimiser tous les paramètres de génération pendant cette étape.

---

# Vérification de l’utilisation GPU

Pendant ou après le test, vérifie dans la sortie de `llama.cpp` que les couches sont bien déchargées vers le GPU CUDA.

Si utile, vérifie également avec `nvidia-smi` que de la VRAM est utilisée pendant l’exécution.

Rapporte :

- si CUDA est effectivement utilisé ;
- le nombre de couches offloadées si `llama.cpp` l’indique ;
- la VRAM approximative utilisée si elle est facilement observable ;
- le temps approximatif de chargement ;
- la vitesse de génération en tokens/seconde si `llama.cpp` l’affiche.

Ces mesures sont informatives : ne lance pas de benchmark complexe.

---

# Tests minimaux supplémentaires

Si le premier test fonctionne, effectue au maximum deux petits tests supplémentaires :

1. une question simple en français ;
2. une instruction courte permettant de vérifier que le modèle suit correctement une consigne.

Pas de benchmark complet.
Pas de longue conversation.
Pas d’évaluation spécialisée.

---

# Frontend et backend

L’étape 4 doit rester indépendante.

Ne modifie PAS :

- la logique React du frontend ;
- la communication frontend/backend ;
- la route `/test-response` pour appeler le modèle ;
- la route `/health`.

Le frontend et FastAPI doivent rester dans l’état validé à l’étape 3.

---

# AGENTS.md

Si `AGENTS.md` contient encore une mention disant que « l’étape actuelle » est l’étape 1 ou une autre étape passée, tu peux mettre à jour uniquement cette information afin qu’elle reflète l’étape 4.

Préserve toutes les règles générales du fichier, notamment le principe de travailler une seule brique à la fois.

Les interdictions spécifiques à une ancienne étape ne doivent pas empêcher l’exécution de cette étape 4 explicitement demandée.

---

# Avant d’agir

Explique brièvement :

1. ce que tu vas installer ;
2. où chaque élément sera stocké ;
3. comment tu vas vérifier CUDA ;
4. comment tu vas télécharger le modèle sans remplir inutilement `C:`;
5. comment tu vas vérifier le SHA256 ;
6. la commande prévue pour le premier test.

Ensuite, réalise uniquement l’étape 4.

---

# Interdictions absolues

Ne fais PAS :

- de connexion du modèle à FastAPI ;
- de modification fonctionnelle du frontend ;
- de mémoire ;
- de SQLite ;
- de base de données ;
- de RAG ;
- d’accès à `IA_WORKSPACE` ;
- de recherche Web intégrée à Léa ;
- de système de profils ;
- de modèle de développement ;
- de modèle santé animale ;
- de modèle vision ;
- de Tauri ;
- de Docker ;
- d’Ollama ;
- d’authentification ;
- de télémétrie ;
- de fine-tuning ;
- de LoRA ;
- de serveur `llama-server` permanent ;
- de système de démarrage automatique ;
- de fonctionnalité de l’étape 5 ou ultérieure.

---

# Critères de validation

L’étape 4 est terminée uniquement si :

- la RTX A1000 est correctement détectée ;
- `llama.cpp` fonctionne avec CUDA ;
- `Qwen3-4B-Q4_K_M.gguf` est stocké sous `models/general/` ;
- le SHA256 du modèle est correct ;
- le modèle se charge correctement ;
- une question envoyée dans le terminal produit une réponse locale cohérente ;
- le GPU est effectivement utilisé ;
- les gros fichiers téléchargés sont ignorés par Git ;
- le frontend et le backend n’ont pas été connectés au modèle ;
- aucune fonctionnalité future n’a été ajoutée.

À la fin, fournis un compte rendu concis avec :

- fichiers créés/modifiés ;
- emplacement exact du modèle ;
- version/build de `llama.cpp` ;
- résultat de `nvidia-smi` utile ;
- résultat du SHA256 ;
- commande de test utilisée ;
- exemple de réponse produite ;
- utilisation GPU observée ;
- éventuels avertissements ou erreurs.

Puis ARRÊTE-TOI et attends la validation de l’utilisateur.
