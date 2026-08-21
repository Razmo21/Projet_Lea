from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "config" / "models.json"
PROFILE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_CPU_PRIORITIES = {"idle", "below_normal", "normal"}


class RegistryError(RuntimeError):
    """Signale une configuration de modèles invalide ou dangereuse."""


class StrictRegistryModel(BaseModel):
    """Refuse les champs inconnus et les conversions implicites dans le registre."""

    model_config = ConfigDict(extra="forbid", strict=True)


class RuntimeServerConfig(StrictRegistryModel):
    """Décrit l’unique serveur llama.cpp local partagé par les profils chat."""

    executable: str
    host: str
    port: int = Field(ge=1, le=65535)
    chat_completions_path: str
    models_path: str

    @model_validator(mode="after")
    def validate_local_server(self) -> RuntimeServerConfig:
        """Interdit toute écoute non locale et exige des routes absolues locales."""

        if self.host != "127.0.0.1":
            raise ValueError("Le runtime doit écouter exclusivement sur 127.0.0.1.")
        if not self.chat_completions_path.startswith("/") or not self.models_path.startswith("/"):
            raise ValueError("Les routes llama.cpp doivent commencer par '/'.")
        return self


class GenerationConfig(StrictRegistryModel):
    """Centralise les budgets de sortie et de gabarit d’un profil."""

    max_tokens: int = Field(gt=0, le=8192)
    system_template_reserve_tokens: int = Field(gt=0, le=8192)


class ProfileRuntimeConfig(StrictRegistryModel):
    """Contient uniquement les paramètres llama.cpp autorisés par le lanceur."""

    alias: str
    gpu_layers: int | Literal["auto"]
    parallel_slots: int = Field(ge=1, le=8)
    jinja: bool
    mmap: bool
    fit: bool
    fit_target_mib: int = Field(ge=0, le=16384)
    fit_context_min_tokens: int = Field(ge=0, le=131072)
    threads: int = Field(ge=1, le=64)
    batch_size: int = Field(ge=32, le=4096)
    ubatch_size: int = Field(ge=16, le=4096)
    cache_type_k: str
    cache_type_v: str
    priority: int = Field(ge=-1, le=3)

    @model_validator(mode="after")
    def validate_runtime_relationships(self) -> ProfileRuntimeConfig:
        """Garantit un slot unique et des batches compatibles avec llama.cpp."""

        if self.parallel_slots != 1:
            raise ValueError("Chaque profil conversationnel doit utiliser un seul slot.")
        if self.ubatch_size > self.batch_size:
            raise ValueError("ubatch_size ne peut pas dépasser batch_size.")
        if self.fit and self.fit_target_mib < 800:
            raise ValueError("Un profil avec --fit doit conserver au moins 800 MiB de marge.")
        if self.gpu_layers == "auto" and not self.fit:
            raise ValueError("gpu_layers='auto' exige --fit pour borner la VRAM.")
        if self.cache_type_k not in {"f16", "q8_0", "q4_0"} or self.cache_type_v not in {
            "f16",
            "q8_0",
            "q4_0",
        }:
            raise ValueError("Type de cache KV non validé par Léa.")
        if not self.alias.strip():
            raise ValueError("L’alias llama.cpp ne peut pas être vide.")
        return self


class PromptConfig(StrictRegistryModel):
    """Référence les prompts versionnés et la stratégie d’injection interne."""

    reliability_path: str
    profile_path: str
    memory_path: str
    strategy: str
    append_no_think: bool
    filter_thinking: bool

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, value: str) -> str:
        """Refuse une stratégie vide qui rendrait le comportement ambigu."""

        if not value.strip():
            raise ValueError("La stratégie de prompt ne peut pas être vide.")
        return value


class ResourcePolicy(StrictRegistryModel):
    """Définit les seuils de sécurité RAM, VRAM et CPU d’un runtime IA."""

    runtime_warning_bytes: int = Field(gt=0)
    runtime_hard_limit_bytes: int = Field(gt=0)
    system_available_warning_bytes: int = Field(gt=0)
    system_available_critical_bytes: int = Field(gt=0)
    vram_target_free_mib: int = Field(ge=800, le=1024)
    cpu_priority: str
    max_threads: int = Field(ge=1, le=64)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> ResourcePolicy:
        """Vérifie que les seuils d’avertissement précèdent les seuils critiques."""

        if self.runtime_warning_bytes >= self.runtime_hard_limit_bytes:
            raise ValueError("La limite RAM dure doit dépasser le seuil d’avertissement.")
        if self.system_available_critical_bytes >= self.system_available_warning_bytes:
            raise ValueError("Le seuil RAM système critique doit être inférieur à l’avertissement.")
        if self.cpu_priority not in ALLOWED_CPU_PRIORITIES:
            raise ValueError(f"Priorité CPU inconnue : {self.cpu_priority}")
        return self


class WorkspacePermission(StrictRegistryModel):
    """Décrit les droits abstraits sans exposer de chemin fourni par le modèle."""

    project_required: bool
    read: bool
    write: bool
    execute: bool

    @model_validator(mode="after")
    def validate_permission_relationships(self) -> WorkspacePermission:
        """Empêche l’écriture ou l’exécution sans droit de lecture du projet."""

        if (self.write or self.execute) and not self.read:
            raise ValueError("L’écriture et l’exécution exigent le droit de lecture.")
        if self.project_required and not self.read:
            raise ValueError("Une permission de projet doit autoriser sa lecture.")
        return self


class AgentPolicy(StrictRegistryModel):
    """Borne une boucle agentique indépendamment des décisions du modèle."""

    max_actions: int = Field(ge=1, le=100)
    max_duration_seconds: int = Field(ge=30, le=7200)
    max_identical_failures: int = Field(ge=1, le=10)
    max_cumulative_output_bytes: int = Field(ge=16_384, le=4_194_304)
    max_context_input_tokens: int = Field(ge=1024, le=131072)
    max_tool_result_to_model_bytes: int = Field(ge=1024, le=65_536)


class ModelProfile(StrictRegistryModel):
    """Représente un cerveau, ses capacités, son modèle et ses limites."""

    id: str
    display_name: str
    model_type: str
    role: str
    enabled: bool
    display_order: int = Field(ge=0)
    model_path: str
    expected_size_bytes: int = Field(gt=0)
    expected_sha256: str
    context_tokens: int = Field(gt=0, le=131072)
    generation: GenerationConfig
    runtime: ProfileRuntimeConfig
    prompt: PromptConfig
    capabilities: list[str]
    tools: list[str]
    workspace_permission: str
    resource_policy: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        """Impose un identifiant stable utilisable dans l’API et SQLite."""

        if PROFILE_ID_PATTERN.fullmatch(value) is None:
            raise ValueError(f"Identifiant de profil invalide : {value!r}")
        return value

    @field_validator("display_name", "role", "workspace_permission", "resource_policy")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        """Refuse les libellés et références vides ou composés d’espaces."""

        if not value.strip():
            raise ValueError("Une valeur textuelle du profil ne peut pas être vide.")
        return value

    @field_validator("expected_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        """Exige un SHA-256 canonique en minuscules sur 64 caractères."""

        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("Le SHA-256 attendu doit contenir 64 caractères hexadécimaux.")
        return value

    @model_validator(mode="after")
    def validate_profile_lists_and_budget(self) -> ModelProfile:
        """Refuse les doublons et les budgets qui ne laissent aucun contexte d’entrée."""

        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError(f"Capacités dupliquées pour {self.id}.")
        if len(self.tools) != len(set(self.tools)):
            raise ValueError(f"Outils dupliqués pour {self.id}.")
        reserved = self.generation.max_tokens + self.generation.system_template_reserve_tokens
        if reserved >= self.context_tokens:
            raise ValueError(f"Le profil {self.id} ne conserve aucun budget d’entrée.")
        if self.runtime.fit and self.runtime.fit_context_min_tokens != self.context_tokens:
            raise ValueError(
                f"Le profil {self.id} doit interdire à --fit de réduire son contexte."
            )
        if not self.runtime.fit and self.runtime.fit_context_min_tokens != 0:
            raise ValueError(
                f"Le profil {self.id} ne doit pas définir fit_context_min_tokens sans --fit."
            )
        return self


class RegistryDocument(StrictRegistryModel):
    """Valide les catalogues et toutes les références croisées du registre."""

    schema_version: int = Field(ge=1)
    default_profile_id: str
    workspace_root: str
    runtime: RuntimeServerConfig
    model_types: list[str]
    capability_catalog: dict[str, str]
    tool_catalog: list[str]
    workspace_permissions: dict[str, WorkspacePermission]
    resource_policies: dict[str, ResourcePolicy]
    agent_policy: AgentPolicy
    profiles: list[ModelProfile]

    @model_validator(mode="after")
    def validate_cross_references(self) -> RegistryDocument:
        """Garantit l’unicité et l’existence de chaque référence du registre."""

        profile_ids = [profile.id for profile in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("Les identifiants de profils doivent être uniques.")
        required_profile_ids = {"general", "development"}
        missing_profile_ids = required_profile_ids - set(profile_ids)
        if missing_profile_ids:
            raise ValueError(
                f"Profils obligatoires absents : {sorted(missing_profile_ids)}"
            )
        aliases = [profile.runtime.alias for profile in self.profiles]
        if len(aliases) != len(set(aliases)):
            raise ValueError("Les alias llama.cpp doivent être uniques.")
        if self.default_profile_id not in profile_ids:
            raise ValueError("Le profil par défaut est introuvable.")
        default_profile = next(profile for profile in self.profiles if profile.id == self.default_profile_id)
        if not default_profile.enabled:
            raise ValueError("Le profil par défaut doit être activé.")
        if len(self.model_types) != len(set(self.model_types)) or not self.model_types:
            raise ValueError("Le catalogue des types de modèles est vide ou dupliqué.")
        if len(self.tool_catalog) != len(set(self.tool_catalog)):
            raise ValueError("Le catalogue des outils contient des doublons.")
        if not self.capability_catalog or not self.workspace_permissions or not self.resource_policies:
            raise ValueError("Les catalogues de capacités, permissions et ressources sont requis.")

        for profile in self.profiles:
            if profile.model_type not in self.model_types:
                raise ValueError(f"Type de modèle inconnu pour {profile.id}: {profile.model_type}")
            unknown_capabilities = set(profile.capabilities) - set(self.capability_catalog)
            if unknown_capabilities:
                raise ValueError(f"Capacités inconnues pour {profile.id}: {sorted(unknown_capabilities)}")
            unknown_tools = set(profile.tools) - set(self.tool_catalog)
            if unknown_tools:
                raise ValueError(f"Outils inconnus pour {profile.id}: {sorted(unknown_tools)}")
            if profile.workspace_permission not in self.workspace_permissions:
                raise ValueError(f"Permission workspace inconnue pour {profile.id}.")
            if profile.resource_policy not in self.resource_policies:
                raise ValueError(f"Politique de ressources inconnue pour {profile.id}.")
            resource_policy = self.resource_policies[profile.resource_policy]
            if profile.runtime.threads > resource_policy.max_threads:
                raise ValueError(
                    f"Le profil {profile.id} dépasse le nombre de threads autorisé."
                )
            if "agent_runs" in profile.capabilities:
                available_input = (
                    profile.context_tokens
                    - profile.generation.max_tokens
                    - profile.generation.system_template_reserve_tokens
                )
                if self.agent_policy.max_context_input_tokens > available_input:
                    raise ValueError(
                        f"La boucle agent dépasse le budget d'entrée du profil {profile.id}."
                    )
        return self


def _resolve_relative_path(project_root: Path, value: str, label: str) -> Path:
    """Résout un chemin de registre sans accepter lecteur, UNC ou remontée parent."""

    windows_path = PureWindowsPath(value)
    if not value or windows_path.is_absolute() or windows_path.drive or value.startswith(("/", "\\")):
        raise RegistryError(f"{label} doit être un chemin relatif au projet.")
    if ".." in windows_path.parts:
        raise RegistryError(f"{label} ne peut pas contenir '..'.")
    candidate = (project_root / Path(*windows_path.parts)).resolve(strict=False)
    try:
        candidate.relative_to(project_root.resolve())
    except ValueError as error:
        raise RegistryError(f"{label} sort de la racine du projet.") from error
    return candidate


def _require_file_within(project_root: Path, relative_path: str, allowed_root: Path, label: str) -> Path:
    """Vérifie qu’un fichier existe sous la racine spécifique attendue."""

    resolved = _resolve_relative_path(project_root, relative_path, label)
    try:
        resolved.relative_to(allowed_root.resolve())
    except ValueError as error:
        raise RegistryError(f"{label} n’est pas situé sous {allowed_root}.") from error
    if not resolved.is_file():
        raise RegistryError(f"{label} est introuvable : {resolved}")
    return resolved


@dataclass(frozen=True)
class LoadedModelRegistry:
    """Associe le document validé à ses chemins et prompts déjà contrôlés."""

    document: RegistryDocument
    project_root: Path
    registry_path: Path
    prompt_texts: dict[str, str]

    def profile(self, profile_id: str) -> ModelProfile:
        """Retourne un profil connu ou une erreur explicite sans fallback silencieux."""

        for profile in self.document.profiles:
            if profile.id == profile_id:
                return profile
        raise RegistryError(f"Profil de modèle inconnu : {profile_id}")

    def model_path(self, profile_id: str) -> Path:
        """Résout le GGUF d’un profil sous le dossier models du projet."""

        profile = self.profile(profile_id)
        return _require_file_within(
            self.project_root,
            profile.model_path,
            self.project_root / "models",
            f"Modèle du profil {profile_id}",
        )

    def runtime_executable(self) -> Path:
        """Résout l’exécutable llama.cpp sous le runtime local autorisé."""

        return _require_file_within(
            self.project_root,
            self.document.runtime.executable,
            self.project_root / "runtime" / "llama.cpp",
            "Exécutable llama.cpp",
        )

    def system_prompt(self, profile_id: str, *, include_memory: bool = False) -> str:
        """Compose le profil avec l’unique contrat commun et l’instruction mémoire."""

        profile = self.profile(profile_id)
        sections = [
            self.prompt_texts[profile.prompt.profile_path],
            self.prompt_texts[profile.prompt.reliability_path],
        ]
        if include_memory:
            sections.append(self.prompt_texts[profile.prompt.memory_path])
        return "\n\n".join(section.strip() for section in sections if section.strip())

    def public_profiles(self) -> list[dict[str, Any]]:
        """Expose au navigateur les capacités utiles sans chemin ni empreinte locale."""

        return [
            {
                "id": profile.id,
                "display_name": profile.display_name,
                "model_type": profile.model_type,
                "role": profile.role,
                "enabled": profile.enabled,
                "display_order": profile.display_order,
                "context_tokens": profile.context_tokens,
                "capabilities": list(profile.capabilities),
            }
            for profile in sorted(self.document.profiles, key=lambda item: item.display_order)
        ]


def load_model_registry(
    registry_path: str | Path | None = None,
    *,
    project_root: str | Path | None = None,
) -> LoadedModelRegistry:
    """Charge, valide et résout intégralement le registre avant tout démarrage."""

    root = Path(project_root).resolve() if project_root is not None else PROJECT_ROOT
    if registry_path is None:
        path = root / "config" / "models.json"
    else:
        configured_path = Path(registry_path)
        path = configured_path.resolve() if configured_path.is_absolute() else (root / configured_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise RegistryError("Le registre doit rester dans la racine du projet.") from error
    if not path.is_file():
        raise RegistryError(f"Registre des modèles introuvable : {path}")
    try:
        raw_document = json.loads(path.read_text(encoding="utf-8"))
        document = RegistryDocument.model_validate(raw_document)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise RegistryError(f"Registre des modèles invalide : {error}") from error

    workspace = PureWindowsPath(document.workspace_root)
    if not workspace.is_absolute() or workspace.drive.upper() != "L:":
        raise RegistryError("workspace_root doit être un chemin absolu sur le lecteur L:.")

    runtime_path = _require_file_within(
        root,
        document.runtime.executable,
        root / "runtime" / "llama.cpp",
        "Exécutable llama.cpp",
    )
    if runtime_path.name.lower() != "llama-server.exe":
        raise RegistryError("Le runtime doit référencer llama-server.exe.")

    prompt_texts: dict[str, str] = {}
    for profile in document.profiles:
        # Même un profil désactivé ne peut conserver un chemin extérieur : le
        # registre reste une source de vérité sûre avant sa future activation.
        model_path = _resolve_relative_path(
            root,
            profile.model_path,
            f"Modèle du profil {profile.id}",
        )
        try:
            model_path.relative_to((root / "models").resolve())
        except ValueError as error:
            raise RegistryError(
                f"Modèle du profil {profile.id} n’est pas situé sous {root / 'models'}."
            ) from error
        if profile.enabled and not model_path.is_file():
            raise RegistryError(
                f"Modèle activé {profile.id} est introuvable : {model_path}"
            )
        for relative_prompt in (
            profile.prompt.reliability_path,
            profile.prompt.profile_path,
            profile.prompt.memory_path,
        ):
            prompt_path = _require_file_within(
                root,
                relative_prompt,
                root / "config" / "prompts",
                f"Prompt du profil {profile.id}",
            )
            try:
                prompt_text = prompt_path.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError) as error:
                raise RegistryError(f"Impossible de lire le prompt {prompt_path}.") from error
            if not prompt_text:
                raise RegistryError(f"Le prompt {prompt_path} est vide.")
            prompt_texts[relative_prompt] = prompt_text

    return LoadedModelRegistry(
        document=document,
        project_root=root,
        registry_path=path,
        prompt_texts=prompt_texts,
    )
