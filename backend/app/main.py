from __future__ import annotations

import asyncio
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .checkpoints import CheckpointConflictError, CheckpointError, CheckpointService
from .database import (
    MAX_TITLE_LENGTH,
    AgentRunNotFoundError,
    CheckpointNotFoundError,
    CheckpointStateError,
    ConversationNotFoundError,
    ConversationOperationError,
    Database,
    GenerationConflictError,
    MessageNotFoundError,
    ProjectNotFoundError,
    RevisionConflictError,
    normalize_spaces,
)
from .memory import (
    EmptyMemoryCommandError,
    MemoryCapacityError,
    build_memory_context,
    ensure_memory_capacity,
    parse_memory_command,
)
from .model_controller import (
    ModelController,
    ModelControllerError,
    PowerShellModelController,
)
from .model_registry import (
    MESSAGE_TOKEN_OVERHEAD,
    LoadedModelRegistry,
    ModelProfile,
    load_model_registry,
)
from .openhands_runtime import OpenHandsRuntime
from .openhands_runs import OpenHandsRunError, OpenHandsRunManager
from .workspace import FrozenProject, WorkspaceGuard, WorkspacePathError


MODEL_REGISTRY = load_model_registry(os.environ.get("LEA_MODEL_REGISTRY") or None)
DEFAULT_PROFILE_ID = MODEL_REGISTRY.document.default_profile_id
DEFAULT_PROFILE = MODEL_REGISTRY.profile(DEFAULT_PROFILE_ID)
MODEL_UNAVAILABLE_MESSAGE = "Le modèle local de Léa n’est pas disponible."
MODEL_INVALID_RESPONSE_MESSAGE = "Le modèle local de Léa n’a pas fourni de réponse exploitable."
CONTEXT_WINDOW_TOKEN_LIMIT = DEFAULT_PROFILE.context_tokens
FINAL_RESPONSE_TOKEN_LIMIT = DEFAULT_PROFILE.generation.max_tokens
SYSTEM_AND_TEMPLATE_TOKEN_RESERVE = DEFAULT_PROFILE.generation.system_template_reserve_tokens
CONTEXT_INPUT_TOKEN_BUDGET = (
    CONTEXT_WINDOW_TOKEN_LIMIT
    - FINAL_RESPONSE_TOKEN_LIMIT
    - SYSTEM_AND_TEMPLATE_TOKEN_RESERVE
)
UTF8_BYTES_PER_ESTIMATED_TOKEN = 1
MAX_USER_MESSAGE_BYTES = DEFAULT_PROFILE.generation.max_user_message_bytes
MAX_ENABLED_PROFILE_USER_MESSAGE_BYTES = max(
    profile.generation.max_user_message_bytes
    for profile in MODEL_REGISTRY.document.profiles
    if profile.enabled
)
MAX_STORED_ASSISTANT_BYTES = 32768
MAX_SEARCH_LENGTH = 100
ALLOWED_BROWSER_ORIGINS = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
}
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
SECURITY_RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}

THINK_XML_OPEN = re.compile(r"<\s*think\s*>", re.IGNORECASE)
THINK_XML_CLOSE = re.compile(r"<\s*/\s*think\s*>", re.IGNORECASE)
THINK_BRACKET_OPEN = re.compile(r"\[\s*start\s+thinking\s*\]", re.IGNORECASE)
THINK_BRACKET_CLOSE = re.compile(r"\[\s*end\s+thinking\s*\]", re.IGNORECASE)
THINK_MARKER_PATTERN = re.compile(
    r"(?P<xml_open><\s*think\s*>)"
    r"|(?P<xml_close><\s*/\s*think\s*>)"
    r"|(?P<bracket_open>\[\s*start\s+thinking\s*\])"
    r"|(?P<bracket_close>\[\s*end\s+thinking\s*\])",
    re.IGNORECASE,
)
NO_THINK_PATTERN = re.compile(r"/\s*no_think\b", re.IGNORECASE)


# Erreurs internes converties plus bas en messages publics sans détail sensible.
class ModelUnavailableError(RuntimeError):
    """Signale que le modèle local ne répond pas dans le délai prévu."""


class ModelResponseError(RuntimeError):
    """Signale une réponse modèle vide, mal formée ou non publiable."""


class ModelGateway(Protocol):
    """Décrit le seul appel de génération attendu par l'API."""

    async def generate(self, messages: list[dict[str, str]]) -> str:
        """Retourne la réponse visible produite à partir des messages internes."""

        ...


def normalize_text(content: str, *, max_bytes: int, field_name: str) -> str:
    """Nettoie un texte public et applique sa limite UTF-8 avant traitement."""

    normalized = content.strip()
    if not normalized:
        raise ValueError(f"{field_name} ne peut pas être vide.")
    if "\x00" in normalized:
        raise ValueError(f"{field_name} ne peut pas contenir de caractère NUL.")
    try:
        byte_length = len(normalized.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise ValueError(f"{field_name} doit être encodable en UTF-8.") from error
    if byte_length > max_bytes:
        raise ValueError(f"{field_name} dépasse la limite de {max_bytes} octets UTF-8.")
    return normalized


def contains_internal_marker(content: str) -> bool:
    """Détecte toute balise interne qui ne doit jamais atteindre l'interface."""

    return any(
        pattern.search(content) is not None
        for pattern in (
            THINK_XML_OPEN,
            THINK_XML_CLOSE,
            THINK_BRACKET_OPEN,
            THINK_BRACKET_CLOSE,
            NO_THINK_PATTERN,
        )
    )


def contains_thinking_marker(content: str) -> bool:
    """Détecte les variantes connues des marqueurs de raisonnement du modèle."""

    return any(
        pattern.search(content) is not None
        for pattern in (
            THINK_XML_OPEN,
            THINK_XML_CLOSE,
            THINK_BRACKET_OPEN,
            THINK_BRACKET_CLOSE,
        )
    )


def normalize_received_user_message(content: str) -> str:
    """Borne la requête avant de connaître le profil réellement figé par le runtime."""

    normalized = normalize_text(
        content,
        max_bytes=MAX_ENABLED_PROFILE_USER_MESSAGE_BYTES,
        field_name="Le message",
    )
    if contains_thinking_marker(normalized):
        raise ValueError("Le message contient un marqueur interne réservé.")
    return normalized


def normalize_user_message(
    content: str,
    profile: ModelProfile = DEFAULT_PROFILE,
) -> str:
    """Valide le message contre le profil figé avant toute écriture de conversation."""

    normalized = normalize_text(
        content,
        max_bytes=profile.generation.max_user_message_bytes,
        field_name="Le message",
    )
    if contains_thinking_marker(normalized):
        raise ValueError("Le message contient un marqueur interne réservé.")
    input_budget = (
        profile.context_tokens
        - profile.generation.max_tokens
        - profile.generation.system_template_reserve_tokens
    )
    if estimate_content_tokens(normalized) > input_budget:
        raise ValueError("Le message est trop grand pour la fenêtre de contexte active.")
    return normalized


def normalize_title(title: str) -> str:
    """Normalise un titre utilisateur tout en conservant sa ponctuation."""

    normalized = normalize_spaces(
        normalize_text(title, max_bytes=400, field_name="Le titre")
    )
    if len(normalized) > MAX_TITLE_LENGTH:
        raise ValueError(f"Le titre dépasse la limite de {MAX_TITLE_LENGTH} caractères.")
    if contains_thinking_marker(normalized):
        raise ValueError("Le titre contient un marqueur interne réservé.")
    return normalized


def remove_thinking(content: str) -> str:
    """Retire défensivement les blocs de pensée, même imbriqués ou incomplets."""

    visible_parts: list[str] = []
    marker_stack: list[str] = []
    cursor = 0

    for marker in THINK_MARKER_PATTERN.finditer(content):
        if not marker_stack:
            visible_parts.append(content[cursor : marker.start()])

        marker_type = marker.lastgroup
        if marker_type == "xml_open":
            marker_stack.append("xml")
        elif marker_type == "bracket_open":
            marker_stack.append("bracket")
        elif marker_stack:
            expected_type = "xml" if marker_type == "xml_close" else "bracket"
            if marker_stack[-1] == expected_type:
                marker_stack.pop()

        cursor = marker.end()

    # Une ouverture sans fermeture rend toute la fin suspecte. Un marqueur
    # fermant isolé est simplement supprimé, sans masquer le texte visible.
    if not marker_stack:
        visible_parts.append(content[cursor:])

    return "".join(visible_parts).strip()


def filter_final_answer(content: object) -> str:
    """Retire le raisonnement et refuse une réponse interne ou non textuelle."""

    if not isinstance(content, str) or "\x00" in content:
        raise ModelResponseError(MODEL_INVALID_RESPONSE_MESSAGE)
    answer = remove_thinking(content)
    if not answer or contains_internal_marker(answer):
        raise ModelResponseError(MODEL_INVALID_RESPONSE_MESSAGE)
    if len(answer.encode("utf-8")) > MAX_STORED_ASSISTANT_BYTES:
        raise ModelResponseError(MODEL_INVALID_RESPONSE_MESSAGE)
    return answer


def estimate_content_tokens(content: str) -> int:
    """Estime prudemment le coût d'un message avec sa surcharge de template."""

    return (
        len(content.encode("utf-8")) // UTF8_BYTES_PER_ESTIMATED_TOKEN
        + MESSAGE_TOKEN_OVERHEAD
    )


def select_history_for_context(
    stored_history: list[dict[str, str]],
    question: str,
    memory_contents: list[str] | tuple[str, ...] = (),
    profile: ModelProfile = DEFAULT_PROFILE,
) -> list[dict[str, str]]:
    """Conserve le suffixe récent de paires complètes qui tient dans le profil."""

    input_budget = (
        profile.context_tokens
        - profile.generation.max_tokens
        - profile.generation.system_template_reserve_tokens
    )
    internal_question = build_internal_user_message(question, memory_contents, profile)
    question_cost = estimate_content_tokens(internal_question)
    if question_cost > input_budget:
        raise ValueError("Le message est trop grand pour la fenêtre de contexte active.")

    complete_pairs: list[list[dict[str, str]]] = []
    for index in range(0, len(stored_history) - 1, 2):
        user = stored_history[index]
        assistant = stored_history[index + 1]
        if user.get("role") != "user" or assistant.get("role") != "assistant":
            break
        complete_pairs.append([user, assistant])

    remaining = input_budget - question_cost
    retained_pairs: list[list[dict[str, str]]] = []
    for pair in reversed(complete_pairs):
        pair_cost = sum(estimate_content_tokens(message["content"]) for message in pair)
        if pair_cost > remaining:
            break
        retained_pairs.insert(0, pair)
        remaining -= pair_cost

    return [message.copy() for pair in retained_pairs for message in pair]


def build_model_messages(
    stored_history: list[dict[str, str]],
    question: str,
    memory_contents: list[str] | tuple[str, ...] = (),
    profile: ModelProfile = DEFAULT_PROFILE,
    registry: LoadedModelRegistry = MODEL_REGISTRY,
) -> list[dict[str, str]]:
    """Construit le contexte d'un profil à partir du registre lié à l'application."""

    retained = select_history_for_context(stored_history, question, memory_contents, profile)
    internal_question = build_internal_user_message(question, memory_contents, profile)
    system_message = registry.system_prompt(
        profile.id,
        include_memory=bool(memory_contents),
    )
    return [
        {"role": "system", "content": system_message},
        *retained,
        {"role": "user", "content": internal_question},
    ]


def build_internal_user_message(
    question: str,
    memory_contents: list[str] | tuple[str, ...] = (),
    profile: ModelProfile = DEFAULT_PROFILE,
) -> str:
    """Ajoute les souvenirs comme données avant la question strictement inchangée."""

    if not memory_contents:
        return f"{question}\n/no_think" if profile.prompt.append_no_think else question
    ensure_memory_capacity(memory_contents)
    memory_context = build_memory_context(memory_contents)
    suffix = "\n/no_think" if profile.prompt.append_no_think else ""
    return (
        f"{memory_context}\n\n"
        "QUESTION ACTUELLE DE L’UTILISATEUR\n"
        f"{question}{suffix}"
    )


class HttpModelGateway:
    def __init__(
        self,
        registry: LoadedModelRegistry = MODEL_REGISTRY,
        profile_id: str = DEFAULT_PROFILE_ID,
    ) -> None:
        """Lie les requêtes HTTP à un profil déjà validé du registre central."""

        self.registry = registry
        self.profile = registry.profile(profile_id)
        runtime = registry.document.runtime
        self.url = f"http://{runtime.host}:{runtime.port}{runtime.chat_completions_path}"

    async def generate(self, messages: list[dict[str, str]]) -> str:
        """Appelle l’unique endpoint local avec l’alias et le budget du profil."""

        payload = {
            "model": self.profile.runtime.alias,
            "messages": messages,
            "stream": False,
            "max_tokens": self.profile.generation.max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(self.url, json=payload)
                response.raise_for_status()
        except httpx.RequestError as error:
            raise ModelUnavailableError(MODEL_UNAVAILABLE_MESSAGE) from error
        except httpx.HTTPStatusError as error:
            raise ModelResponseError(
                "Le modèle local de Léa a renvoyé une erreur."
            ) from error

        try:
            raw_content = response.json()["choices"][0]["message"]["content"]
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise ModelResponseError(MODEL_INVALID_RESPONSE_MESSAGE) from error
        return filter_final_answer(raw_content)


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SendMessageRequest(StrictRequest):
    conversation_id: str | None = None
    message: str
    expected_revision: int | None = Field(default=None, ge=0)

    @field_validator("message")
    @classmethod
    def validate_message(cls, content: str) -> str:
        """Applique seulement la borne commune avant la réservation du profil."""

        return normalize_received_user_message(content)

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, conversation_id: str | None) -> str | None:
        """Canonicalise l'UUID facultatif transmis par le navigateur."""

        if conversation_id is None:
            return None
        try:
            return str(UUID(conversation_id))
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("L’identifiant de conversation est invalide.") from error


class RevisionRequest(StrictRequest):
    expected_revision: int = Field(ge=0)


class RenameConversationRequest(RevisionRequest):
    title: str

    @field_validator("title")
    @classmethod
    def validate_title(cls, title: str) -> str:
        """Applique la normalisation commune aux renommages."""

        return normalize_title(title)


class EditMessageRequest(RevisionRequest):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, content: str) -> str:
        """Applique seulement la borne commune avant la réservation du profil."""

        return normalize_received_user_message(content)


class StartAgentRunRequest(StrictRequest):
    """Valide la tâche textuelle; le projet et le profil viennent de l'état serveur."""

    task: str = Field(min_length=1, max_length=16_384)


class ConversationLockRegistry:
    """Un verrou de génération par conversation, distinct du verrou mémoire."""

    def __init__(self) -> None:
        """Initialise un registre vide, alimenté à la première conversation."""

        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, conversation_id: str) -> asyncio.Lock:
        """Retourne toujours le même verrou pour un identifiant de conversation."""

        return self._locks.setdefault(conversation_id, asyncio.Lock())


class RuntimeCoordinator:
    """Sérialise les générations, runs agents et changements de cerveau."""

    def __init__(self, active_profile_id: str) -> None:
        """Démarre toujours sur le profil par défaut déclaré par le registre."""

        self.active_profile_id = active_profile_id
        self.switching_profile_id: str | None = None
        self.active_generations = 0
        self.active_agent_runs = 0
        self._lock = asyncio.Lock()

    async def begin_generation(self) -> str:
        """Fige le profil d'une réponse et interdit une génération pendant une bascule."""

        async with self._lock:
            if self.switching_profile_id is not None:
                raise GenerationConflictError("Un changement de profil est en cours.")
            self.active_generations += 1
            return self.active_profile_id

    async def finish_generation(self) -> None:
        """Libère exactement une génération enregistrée, même après erreur."""

        async with self._lock:
            if self.active_generations > 0:
                self.active_generations -= 1

    async def begin_agent_run(self, required_profile_id: str) -> None:
        """Réserve le slot agent seulement sur le profil actif et sans autre activité."""

        async with self._lock:
            if self.switching_profile_id is not None:
                raise GenerationConflictError("Un changement de profil est en cours.")
            if self.active_profile_id != required_profile_id:
                raise GenerationConflictError("Active le profil Programmation avant de lancer un run.")
            if self.active_generations or self.active_agent_runs:
                raise GenerationConflictError("Le modèle local est déjà occupé.")
            self.active_agent_runs += 1

    async def finish_agent_run(self) -> None:
        """Libère exactement un run pour réautoriser conversations et commutations."""

        async with self._lock:
            if self.active_agent_runs > 0:
                self.active_agent_runs -= 1

    async def begin_switch(self, profile_id: str) -> str:
        """Réserve la bascule seulement quand aucune activité modèle n'est en cours."""

        async with self._lock:
            if self.switching_profile_id is not None:
                raise GenerationConflictError("Un changement de profil est déjà en cours.")
            if self.active_generations or self.active_agent_runs:
                raise GenerationConflictError(
                    "Le profil ne peut pas changer pendant une génération ou un run agent."
                )
            previous_profile_id = self.active_profile_id
            self.switching_profile_id = profile_id
            return previous_profile_id

    async def finish_switch(self, *, succeeded: bool) -> None:
        """Publie atomiquement la cible seulement après sa readiness complète."""

        async with self._lock:
            if succeeded and self.switching_profile_id is not None:
                self.active_profile_id = self.switching_profile_id
            self.switching_profile_id = None

    async def status(self) -> dict[str, Any]:
        """Retourne un instantané structuré sans exposer de PID ni chemin."""

        async with self._lock:
            return {
                "active_profile_id": self.active_profile_id,
                "loading_profile_id": self.switching_profile_id,
                "generation_active": self.active_generations > 0,
                "agent_run_active": self.active_agent_runs > 0,
            }


def require_local_mutation(request: Request) -> None:
    """Refuse une mutation issue d'une origine navigateur non locale."""

    origin = request.headers.get("origin")
    if origin is not None and origin not in ALLOWED_BROWSER_ORIGINS:
        raise HTTPException(
            status_code=403,
            detail="Cette opération doit venir de l’interface locale de Léa.",
        )


def _database(request: Request) -> Database:
    """Retourne l'unique instance SQLite attachée à l'application."""

    return request.app.state.database


def _gateway(request: Request, profile_id: str) -> ModelGateway:
    """Retourne le faux gateway de test ou un client lié au profil figé."""

    fixed_gateway = request.app.state.fixed_model_gateway
    if fixed_gateway is not None:
        return fixed_gateway
    return HttpModelGateway(request.app.state.model_registry, profile_id)


def _locks(request: Request) -> ConversationLockRegistry:
    """Retourne le registre de verrous partagé par les routes de génération."""

    return request.app.state.conversation_locks


def _memory_lock(request: Request) -> asyncio.Lock:
    """Retourne le verrou qui sérialise les commandes de mémoire globale."""

    return request.app.state.memory_lock


def _runtime(request: Request) -> RuntimeCoordinator:
    """Centralise l'accès au coordinateur de runtime de l'application."""

    return request.app.state.runtime_coordinator


async def _is_active_model_ready(request: Request, profile_id: str) -> bool:
    """Confirme que l'alias annoncé est réellement servi par llama-server."""

    # Les tests d'API injectent un gateway déterministe qui représente un
    # modèle disponible sans ouvrir de port local.
    if request.app.state.fixed_model_gateway is not None:
        return True
    registry = request.app.state.model_registry
    profile = registry.profile(profile_id)
    runtime = registry.document.runtime
    if profile.agent_engine == "OpenHands":
        runtime = registry.document.openhands.model_endpoint
    models_url = f"http://{runtime.host}:{runtime.port}{runtime.models_path}"
    expected_alias = profile.runtime.alias
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(models_url)
            response.raise_for_status()
        entries = response.json()["data"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return False
    return any(
        isinstance(entry, dict) and entry.get("id") == expected_alias
        for entry in entries
    )


def _safe_failure_code(error: BaseException) -> tuple[int, str, str]:
    """Traduit une erreur interne en statut, message public et code persistant."""

    if isinstance(error, ModelUnavailableError):
        return 503, MODEL_UNAVAILABLE_MESSAGE, "model_unavailable"
    if isinstance(error, asyncio.CancelledError):
        return 503, "La génération a été interrompue.", "interrupted"
    if isinstance(error, (MemoryCapacityError, ValueError)):
        return 422, str(error), "model_error"
    return 502, MODEL_INVALID_RESPONSE_MESSAGE, "model_error"


async def _generate_response(
    database: Database,
    gateway: ModelGateway,
    locks: ConversationLockRegistry,
    conversation_id: str,
    user_message_id: str,
    model_messages: list[dict[str, str]],
    profile: ModelProfile,
    runtime: RuntimeCoordinator,
) -> dict[str, Any] | JSONResponse:
    """Finalise une génération réussie ou rend son échec visible et rejouable."""

    lock = locks.get(conversation_id)
    try:
        answer = await gateway.generate(model_messages)
        answer = filter_final_answer(answer)
        database.complete_generation(
            conversation_id,
            user_message_id,
            answer,
            model_id=profile.runtime.alias,
            profile_id=profile.id,
        )
        return database.get_conversation(conversation_id)
    except BaseException as error:
        status_code, public_message, error_code = _safe_failure_code(error)
        try:
            database.fail_generation(conversation_id, user_message_id, error_code)
        except (ConversationNotFoundError, MessageNotFoundError):
            pass
        if isinstance(error, asyncio.CancelledError):
            raise
        detail = database.get_conversation(conversation_id)
        return JSONResponse(
            status_code=status_code,
            content={"detail": public_message, "conversation": detail},
        )
    finally:
        if lock.locked():
            lock.release()
        await runtime.finish_generation()


def _acquire_generation_lock(
    locks: ConversationLockRegistry, conversation_id: str
) -> asyncio.Lock:
    """Réserve sans attente la conversation ou signale l'activité concurrente."""

    lock = locks.get(conversation_id)
    if lock.locked():
        raise GenerationConflictError(
            "Une génération est déjà active pour cette conversation."
        )
    return lock


def create_app(
    database_path: str | Path | None = None,
    model_gateway: ModelGateway | None = None,
    model_registry: LoadedModelRegistry = MODEL_REGISTRY,
    model_controller: ModelController | None = None,
    workspace_root: str | Path | None = None,
    checkpoint_root: str | Path | None = None,
    agent_runtime_root: str | Path | None = None,
) -> FastAPI:
    """Build the sole local API with injected dependencies for safe test isolation."""

    database = Database(database_path)
    # Only the production configuration receives the fixed-root check; tests
    # may inject an isolated directory and no HTTP route can alter that choice.
    workspace_guard = WorkspaceGuard(
        workspace_root or model_registry.document.workspace_root,
        require_expected_root=workspace_root is None,
    )
    checkpoints = CheckpointService(
        database,
        workspace_guard,
        Path(checkpoint_root)
        if checkpoint_root is not None
        else model_registry.project_root / "data" / "agent-checkpoints",
    )
    openhands_runtime = OpenHandsRuntime(model_registry)
    openhands_runs = OpenHandsRunManager(
        database,
        workspace_guard,
        checkpoints,
        openhands_runtime,
        model_registry,
        Path(agent_runtime_root)
        if agent_runtime_root is not None
        else model_registry.project_root / "data" / "openhands-runs",
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        """Initialize persistent state, recover owned runs, then close them safely at shutdown."""

        database.initialize()
        discovered = workspace_guard.discover_projects()
        database.sync_projects(
            [(project.name, project.relative_path) for project in discovered]
        )
        await openhands_runs.recover()
        try:
            yield
        finally:
            await openhands_runs.close()

    application = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.state.database = database
    application.state.model_registry = model_registry
    application.state.fixed_model_gateway = model_gateway
    application.state.openhands_runtime = openhands_runtime
    application.state.model_controller = model_controller or PowerShellModelController(
        registry=model_registry,
        openhands_runtime=openhands_runtime,
    )
    application.state.workspace_guard = workspace_guard
    application.state.checkpoints = checkpoints
    application.state.openhands_runs = openhands_runs
    application.state.conversation_locks = ConversationLockRegistry()
    application.state.memory_lock = asyncio.Lock()
    application.state.runtime_coordinator = RuntimeCoordinator(
        model_registry.document.default_profile_id
    )

    # L'API reste locale ; toute origine navigateur déclarée doit être connue.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(ALLOWED_BROWSER_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    # Refuse le DNS rebinding vers l'API loopback tout en conservant TestClient.
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

    @application.middleware("http")
    async def add_local_security_headers(request: Request, call_next):
        """Prevent local API data caching, MIME guessing, referrer leaks, and framing."""

        response = await call_next(request)
        for name, value in SECURITY_RESPONSE_HEADERS.items():
            response.headers[name] = value
        return response

    @application.exception_handler(ConversationNotFoundError)
    async def conversation_not_found_handler(
        _request: Request, error: ConversationNotFoundError
    ) -> JSONResponse:
        """Transforme une conversation absente en réponse HTTP 404 stable."""

        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.exception_handler(MessageNotFoundError)
    async def message_not_found_handler(
        _request: Request, error: MessageNotFoundError
    ) -> JSONResponse:
        """Transforme un message absent en réponse HTTP 404 stable."""

        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.exception_handler(ProjectNotFoundError)
    async def project_not_found_handler(
        _request: Request, error: ProjectNotFoundError
    ) -> JSONResponse:
        """Convertit un identifiant de projet périmé en réponse locale 404."""

        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.exception_handler(WorkspacePathError)
    async def workspace_path_handler(
        _request: Request, error: WorkspacePathError
    ) -> JSONResponse:
        """Retourne un refus contrôlé sans divulguer de chemin absolu."""

        return JSONResponse(status_code=400, content={"detail": str(error)})

    @application.exception_handler(AgentRunNotFoundError)
    async def agent_run_not_found_handler(
        _request: Request, error: AgentRunNotFoundError
    ) -> JSONResponse:
        """Return a local 404 when a persisted OpenHands run UUID is unknown."""

        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.exception_handler(CheckpointNotFoundError)
    async def checkpoint_not_found_handler(
        _request: Request, error: CheckpointNotFoundError
    ) -> JSONResponse:
        """Return a local 404 when a checkpoint belongs to no retained run."""

        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.exception_handler(CheckpointConflictError)
    async def checkpoint_conflict_handler(
        _request: Request, error: CheckpointConflictError
    ) -> JSONResponse:
        """Expose rollback conflicts without disclosing paths outside the selected project."""

        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(OpenHandsRunError)
    @application.exception_handler(CheckpointStateError)
    @application.exception_handler(CheckpointError)
    async def openhands_run_error_handler(
        _request: Request, error: RuntimeError
    ) -> JSONResponse:
        """Convert controlled OpenHands/checkpoint lifecycle failures into a local conflict response."""

        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(RevisionConflictError)
    async def revision_conflict_handler(
        _request: Request, error: RevisionConflictError
    ) -> JSONResponse:
        """Expose un conflit de révision sans masquer l'écriture refusée."""

        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(GenerationConflictError)
    async def generation_conflict_handler(
        _request: Request, error: GenerationConflictError
    ) -> JSONResponse:
        """Expose une génération concurrente comme conflit HTTP."""

        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(ConversationOperationError)
    async def operation_error_handler(
        _request: Request, error: ConversationOperationError
    ) -> JSONResponse:
        """Retourne un refus métier lisible pour une opération de conversation."""

        return JSONResponse(status_code=400, content={"detail": str(error)})

    @application.exception_handler(MemoryCapacityError)
    async def memory_capacity_handler(
        _request: Request, error: MemoryCapacityError
    ) -> JSONResponse:
        """Informe le navigateur quand la mémoire explicite est pleine."""

        return JSONResponse(status_code=400, content={"detail": str(error)})

    @application.get("/health")
    def health() -> dict[str, str]:
        """Fournit la sonde minimale utilisée par le lanceur local."""

        return {"status": "ok"}

    @application.get("/api/models")
    async def list_models(request: Request) -> dict[str, Any]:
        """Expose les profils configurés sans divulguer chemins ni empreintes locales."""

        registry = request.app.state.model_registry
        runtime_status = await _runtime(request).status()
        return {
            "default_profile_id": registry.document.default_profile_id,
            "active_profile_id": runtime_status["active_profile_id"],
            "profiles": registry.public_profiles(),
        }

    @application.get("/api/models/status")
    async def model_status(request: Request) -> dict[str, Any]:
        """Expose l'activité de commutation sans PID, chemin ni commande système."""

        status = await _runtime(request).status()
        development_readiness: dict[str, bool | str] | None = None
        if status["loading_profile_id"]:
            state = "loading"
            message = "Changement de profil en cours."
        elif (
            status["active_profile_id"] == "development"
            and request.app.state.fixed_model_gateway is None
        ):
            # Qwen seul ne suffit pas : la readiness Programmation exige
            # Docker, Agent Server et les vrais outils OpenHands locaux.
            readiness = await request.app.state.openhands_runtime.status()
            development_readiness = readiness.public()
            state = "ready" if readiness.profile_ready else "error"
            message = readiness.message
        elif await _is_active_model_ready(request, status["active_profile_id"]):
            state = "ready"
            message = "Le profil actif est prêt."
        else:
            state = "error"
            message = "Le modèle actif n'est pas disponible."
        result: dict[str, Any] = {
            "state": state,
            "message": message,
            **status,
        }
        if development_readiness is not None:
            result["development_readiness"] = development_readiness
        return result

    @application.get("/api/runtime/activity")
    async def runtime_activity(request: Request) -> dict[str, bool]:
        """Permet au lanceur local de refuser une bascule pendant une activité."""

        status = await _runtime(request).status()
        return {
            "generation_active": bool(status["generation_active"]),
            "agent_run_active": bool(status["agent_run_active"]),
        }

    @application.post("/api/models/{profile_id}/activate")
    async def activate_model(
        profile_id: str,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any]:
        """Bascule le runtime via le gestionnaire PID sûr puis publie la cible."""

        registry = request.app.state.model_registry
        try:
            profile = registry.profile(profile_id)
        except RuntimeError as error:
            raise HTTPException(status_code=404, detail="Profil de modèle inconnu.") from error
        if not profile.enabled:
            raise HTTPException(status_code=400, detail="Ce profil de modèle est désactivé.")

        runtime = _runtime(request)
        await runtime.begin_switch(profile_id)
        succeeded = False
        rolled_back = False
        try:
            active_profile_id = await request.app.state.model_controller.activate(profile_id)
            succeeded = active_profile_id == profile_id
            rolled_back = not succeeded
        except ModelControllerError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        finally:
            await runtime.finish_switch(succeeded=succeeded)
        if rolled_back:
            raise HTTPException(
                status_code=503,
                detail="Le nouveau profil n'a pas démarré ; l'ancien profil a été restauré.",
            )
        status = await runtime.status()
        return {
            "state": "ready",
            "message": "Le profil sélectionné est prêt.",
            **status,
        }

    @application.get("/api/projects")
    def list_projects(request: Request) -> dict[str, Any]:
        """Expose la liste relative persistée et l'unique sélection active."""

        projects = _database(request).list_projects()
        active = next((project["id"] for project in projects if project["active"]), None)
        return {"projects": projects, "active_project_id": active}

    @application.post("/api/projects/refresh")
    def refresh_projects(
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any]:
        """Rescanne uniquement les sous-dossiers directs validés de IA_WORKSPACE."""

        discovered = request.app.state.workspace_guard.discover_projects()
        projects = _database(request).sync_projects(
            [(project.name, project.relative_path) for project in discovered]
        )
        active = next((project["id"] for project in projects if project["active"]), None)
        return {"projects": projects, "active_project_id": active}

    @application.post("/api/projects/{project_id}/activate")
    def activate_project(
        project_id: str,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any]:
        """Revalide le dossier réel avant de mémoriser sa sélection par UUID."""

        try:
            canonical_id = str(UUID(project_id))
        except (TypeError, ValueError, AttributeError) as error:
            raise HTTPException(status_code=404, detail="Projet inconnu.") from error
        registered = next(
            (
                project
                for project in _database(request).list_projects()
                if project["id"] == canonical_id
            ),
            None,
        )
        if registered is None:
            raise ProjectNotFoundError("Le projet demandé n'existe plus.")
        request.app.state.workspace_guard.resolve_project(registered["relative_path"])
        _database(request).activate_project(canonical_id)
        projects = _database(request).list_projects()
        return {"projects": projects, "active_project_id": canonical_id}

    @application.get("/api/agent-runs")
    def list_agent_runs(request: Request) -> dict[str, Any]:
        """Expose les runs SQLite compacts sans transcript ni observation OpenHands détaillée."""

        manager: OpenHandsRunManager = request.app.state.openhands_runs
        return {"runs": manager.list()}

    @application.post("/api/agent-runs", status_code=202)
    async def start_agent_run(
        body: StartAgentRunRequest,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any]:
        """Freeze the selected project, checkpoint it, and start one real OpenHands SDK run."""

        registry: LoadedModelRegistry = request.app.state.model_registry
        runtime = _runtime(request)
        status = await runtime.status()
        profile = registry.profile(status["active_profile_id"])
        if "agent_runs" not in profile.capabilities:
            raise HTTPException(status_code=409, detail="Active le profil Programmation avant de lancer un run.")
        project = _database(request).get_active_project()
        if project is None:
            raise HTTPException(status_code=409, detail="Sélectionne un projet actif avant le run.")
        frozen = request.app.state.workspace_guard.freeze_project(
            project["id"], project["relative_path"]
        )
        await runtime.begin_agent_run(profile.id)
        try:
            record = await request.app.state.openhands_runs.start(
                body.task,
                profile,
                frozen,
                runtime.finish_agent_run,
            )
        except BaseException:
            await runtime.finish_agent_run()
            raise
        return record

    @application.get("/api/agent-runs/{run_id}")
    async def get_agent_run(run_id: str, request: Request) -> dict[str, Any]:
        """Retourne l'état persistant d'un UUID OpenHands sans dépendre de la sélection active."""

        return await request.app.state.openhands_runs.get(run_id)

    @application.post("/api/agent-runs/{run_id}/cancel")
    async def cancel_agent_run(
        run_id: str,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any]:
        """Attend l'arrêt réel du SDK et du conteneur vérifié avant de publier `cancelled`."""

        return await request.app.state.openhands_runs.cancel(run_id)

    def frozen_project_for_run(request: Request, run: dict[str, Any]) -> FrozenProject:
        """Rebuild the immutable run project from checkpoint metadata, never from the mutable active project."""

        checkpoint_id = run.get("checkpoint_id")
        if not isinstance(checkpoint_id, str):
            raise HTTPException(status_code=409, detail="Ce run ne possède pas de checkpoint exploitable.")
        checkpoint = request.app.state.database.get_project_checkpoint(checkpoint_id)
        if checkpoint["project_id"] != run["project_id"]:
            raise HTTPException(status_code=409, detail="Le checkpoint du run est incohérent.")
        try:
            frozen = request.app.state.workspace_guard.freeze_project(
                str(run["project_id"]), str(checkpoint["project_relative_path"])
            )
            request.app.state.checkpoints.validate_checkpoint_project(checkpoint_id, frozen)
            return frozen
        except WorkspacePathError as error:
            # A deleted project cannot be frozen again.  Persist the conflict
            # before returning so the UI never keeps offering a stale rollback.
            request.app.state.checkpoints.record_conflict(
                checkpoint_id,
                "Le projet figé du checkpoint n'est plus disponible.",
            )
            raise CheckpointConflictError(
                "Le projet figé du checkpoint n'est plus disponible ; restauration refusée."
            ) from error
        except CheckpointConflictError:
            request.app.state.checkpoints.record_conflict(
                checkpoint_id,
                "Le projet figé du checkpoint a changé après le run.",
            )
            raise

    @application.get("/api/agent-runs/{run_id}/changes")
    async def get_agent_run_changes(run_id: str, request: Request) -> dict[str, Any]:
        """Return the checkpoint diff associated with one persisted run without reading the active selection."""

        run = await request.app.state.openhands_runs.get(run_id)
        checkpoint_id = run.get("checkpoint_id")
        if not isinstance(checkpoint_id, str):
            raise HTTPException(status_code=409, detail="Ce run ne possède pas de checkpoint exploitable.")
        checkpoint = request.app.state.database.get_project_checkpoint(checkpoint_id)
        return {
            "run_id": run["run_id"],
            "checkpoint": checkpoint,
            "changes": request.app.state.checkpoints.changes(checkpoint_id),
        }

    @application.post("/api/agent-runs/{run_id}/accept")
    async def accept_agent_run_changes(
        run_id: str,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any]:
        """Accept a completed checkpoint explicitly while retaining its lightweight audit record."""

        run = await request.app.state.openhands_runs.get(run_id)
        if (
            run["state"] != "completed"
            or run.get("validation_status") != "validated"
        ):
            # A checkpoint can still contain partial files after a technically
            # stopped but unvalidated agent run.  Such changes remain
            # reviewable and restorable, never implicitly acceptable.
            raise HTTPException(
                status_code=409,
                detail="Seul un run OpenHands réellement validé peut être accepté.",
            )
        checkpoint_id = run.get("checkpoint_id")
        if not isinstance(checkpoint_id, str):
            raise HTTPException(status_code=409, detail="Ce run ne possède pas de checkpoint exploitable.")
        return {
            "run_id": run["run_id"],
            "checkpoint": request.app.state.checkpoints.accept(checkpoint_id),
        }

    @application.post("/api/agent-runs/{run_id}/rollback")
    async def rollback_agent_run_changes(
        run_id: str,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any]:
        """Restore a completed run only after comparing the current project to its stored after-state."""

        run = await request.app.state.openhands_runs.get(run_id)
        checkpoint_id = run.get("checkpoint_id")
        if not isinstance(checkpoint_id, str):
            raise HTTPException(status_code=409, detail="Ce run ne possède pas de checkpoint exploitable.")
        frozen = frozen_project_for_run(request, run)
        return {
            "run_id": run["run_id"],
            "checkpoint": request.app.state.checkpoints.rollback(checkpoint_id, frozen),
        }

    @application.get("/api/conversations")
    def list_conversations(
        request: Request,
        search: str = Query(default="", max_length=MAX_SEARCH_LENGTH),
    ) -> dict[str, list[dict[str, Any]]]:
        """Liste les conversations selon le filtre textuel validé."""

        if "\x00" in search:
            raise HTTPException(status_code=422, detail="La recherche contient un caractère NUL.")
        return {"conversations": _database(request).list_conversations(search)}

    @application.post("/api/conversations/messages", response_model=None)
    async def send_message(
        body: SendMessageRequest,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any] | JSONResponse:
        """Persist one validated user turn and publish only a verified model response."""

        database_instance = _database(request)
        lock_registry = _locks(request)
        if body.conversation_id is None and body.expected_revision is not None:
            raise HTTPException(
                status_code=422,
                detail="Une nouvelle conversation ne possède pas encore de révision.",
            )
        if body.conversation_id is not None and body.expected_revision is None:
            raise HTTPException(
                status_code=422,
                detail="La révision attendue est obligatoire pour une conversation existante.",
            )

        runtime = _runtime(request)
        profile_id = await runtime.begin_generation()
        generation_handed_off = False
        try:
            profile = request.app.state.model_registry.profile(profile_id)
            if profile.agent_engine == "OpenHands" and request.app.state.fixed_model_gateway is None:
                # The Programming brain is reserved for the OpenHands SDK
                # path. Direct chat here would bypass its tools/checkpoint.
                raise HTTPException(
                    status_code=409,
                    detail="Utilise une tâche Programmation sur un projet sélectionné.",
                )
            try:
                message = normalize_user_message(body.message, profile)
                memory_command = parse_memory_command(message)
            except (EmptyMemoryCommandError, ValueError) as error:
                raise HTTPException(status_code=422, detail=str(error)) from error

            if memory_command is not None:
                # Le profil est figé même pour une commande mémoire afin qu'une
                # bascule ne puisse pas changer ses règles pendant la transaction.
                async with _memory_lock(request):
                    conversation_id = database_instance.apply_memory_command(
                        memory_command,
                        message,
                        body.conversation_id,
                        body.expected_revision,
                    )
                return database_instance.get_conversation(conversation_id)

            gateway = _gateway(request, profile_id)
            if body.conversation_id is None:
                async with _memory_lock(request):
                    memory_contents = [
                        memory["content"]
                        for memory in database_instance.list_memories()
                    ]
                    try:
                        model_messages = build_model_messages(
                            [],
                            message,
                            memory_contents,
                            profile,
                            request.app.state.model_registry,
                        )
                    except (MemoryCapacityError, ValueError) as error:
                        raise HTTPException(status_code=422, detail=str(error)) from error
                    conversation_id, user_message_id = (
                        database_instance.create_pending_conversation(message)
                    )
                    lock = _acquire_generation_lock(lock_registry, conversation_id)
                    await lock.acquire()
            else:
                conversation_id = body.conversation_id
                lock = _acquire_generation_lock(lock_registry, conversation_id)
                await lock.acquire()
                try:
                    async with _memory_lock(request):
                        memory_contents = [
                            memory["content"]
                            for memory in database_instance.list_memories()
                        ]
                        detail = database_instance.get_conversation(conversation_id)
                        stored_history = [
                            {"role": message["role"], "content": message["content"]}
                            for message in detail["messages"]
                            if message["status"] == "completed"
                            and message["kind"] == "conversation"
                        ]
                        try:
                            model_messages = build_model_messages(
                                stored_history,
                                message,
                                memory_contents,
                                profile,
                                request.app.state.model_registry,
                            )
                        except (MemoryCapacityError, ValueError) as error:
                            raise HTTPException(status_code=422, detail=str(error)) from error
                        user_message_id = database_instance.add_pending_message(
                            conversation_id, message, body.expected_revision
                        )
                except BaseException:
                    lock.release()
                    raise

            generation_handed_off = True
            return await _generate_response(
                database_instance,
                gateway,
                lock_registry,
                conversation_id,
                user_message_id,
                model_messages,
                profile,
                runtime,
            )
        finally:
            if not generation_handed_off:
                await runtime.finish_generation()

    @application.get("/api/conversations/{conversation_id}")
    def get_conversation(conversation_id: UUID, request: Request) -> dict[str, Any]:
        """Retourne une conversation complète depuis son UUID canonique."""

        return _database(request).get_conversation(str(conversation_id))

    @application.patch("/api/conversations/{conversation_id}")
    def rename_conversation(
        conversation_id: UUID,
        body: RenameConversationRequest,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any]:
        """Renomme une conversation puis retourne sa version mise à jour."""

        database_instance = _database(request)
        database_instance.rename_conversation(
            str(conversation_id), body.title, body.expected_revision
        )
        return database_instance.get_conversation(str(conversation_id))

    @application.delete("/api/conversations/{conversation_id}", status_code=204)
    async def delete_conversation(
        conversation_id: UUID,
        body: RevisionRequest,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> Response:
        """Supprime une conversation sous le verrou de mémoire partagé."""

        # La provenance éventuelle disparaît avec la conversation, mais le fait
        # global reste intact. Le verrou garde cet ordre avec retenir/oublier.
        async with _memory_lock(request):
            _database(request).delete_conversation(
                str(conversation_id), body.expected_revision
            )
        return Response(status_code=204)

    @application.post(
        "/api/conversations/{conversation_id}/messages/{message_id}/retry",
        response_model=None,
    )
    async def retry_message(
        conversation_id: UUID,
        message_id: UUID,
        body: RevisionRequest,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any] | JSONResponse:
        """Relance la dernière question échouée avec le profil figé courant."""

        conversation_key = str(conversation_id)
        lock_registry = _locks(request)
        runtime = _runtime(request)
        profile_id = await runtime.begin_generation()
        profile = request.app.state.model_registry.profile(profile_id)
        lock: asyncio.Lock | None = None
        try:
            lock = _acquire_generation_lock(lock_registry, conversation_key)
            await lock.acquire()
            async with _memory_lock(request):
                history, question, memory_contents = (
                    _database(request).generation_context_before(
                        conversation_key, str(message_id)
                    )
                )
                try:
                    model_messages = build_model_messages(
                        history,
                        question,
                        memory_contents,
                        profile,
                        request.app.state.model_registry,
                    )
                except (MemoryCapacityError, ValueError) as error:
                    raise HTTPException(status_code=422, detail=str(error)) from error
                user_message_id = _database(request).retry_message(
                    conversation_key, str(message_id), body.expected_revision
                )
        except BaseException:
            if lock is not None and lock.locked():
                lock.release()
            await runtime.finish_generation()
            raise
        return await _generate_response(
            _database(request),
            _gateway(request, profile_id),
            lock_registry,
            conversation_key,
            user_message_id,
            model_messages,
            profile,
            runtime,
        )

    @application.patch(
        "/api/conversations/{conversation_id}/messages/{message_id}",
        response_model=None,
    )
    async def edit_message(
        conversation_id: UUID,
        message_id: UUID,
        body: EditMessageRequest,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any] | JSONResponse:
        """Modifie une question puis régénère depuis le nouvel historique."""

        conversation_key = str(conversation_id)
        lock_registry = _locks(request)
        runtime = _runtime(request)
        profile_id = await runtime.begin_generation()
        lock: asyncio.Lock | None = None
        try:
            profile = request.app.state.model_registry.profile(profile_id)
            try:
                content = normalize_user_message(body.content, profile)
                edited_memory_command = parse_memory_command(content)
            except EmptyMemoryCommandError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            if edited_memory_command is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Une commande mémoire doit être envoyée comme nouveau message.",
                )
            lock = _acquire_generation_lock(lock_registry, conversation_key)
            await lock.acquire()
            async with _memory_lock(request):
                history, _old_question, memory_contents = (
                    _database(request).generation_context_before(
                        conversation_key, str(message_id)
                    )
                )
                try:
                    model_messages = build_model_messages(
                        history,
                        content,
                        memory_contents,
                        profile,
                        request.app.state.model_registry,
                    )
                except (MemoryCapacityError, ValueError) as error:
                    raise HTTPException(status_code=422, detail=str(error)) from error
                user_message_id = _database(request).edit_user_message(
                    conversation_key,
                    str(message_id),
                    content,
                    body.expected_revision,
                )
        except BaseException:
            if lock is not None and lock.locked():
                lock.release()
            await runtime.finish_generation()
            raise
        return await _generate_response(
            _database(request),
            _gateway(request, profile_id),
            lock_registry,
            conversation_key,
            user_message_id,
            model_messages,
            profile,
            runtime,
        )

    @application.post(
        "/api/conversations/{conversation_id}/messages/{message_id}/regenerate",
        response_model=None,
    )
    async def regenerate_message(
        conversation_id: UUID,
        message_id: UUID,
        body: RevisionRequest,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any] | JSONResponse:
        """Relance une réponse existante sans modifier sa question source."""

        conversation_key = str(conversation_id)
        lock_registry = _locks(request)
        runtime = _runtime(request)
        profile_id = await runtime.begin_generation()
        profile = request.app.state.model_registry.profile(profile_id)
        lock: asyncio.Lock | None = None
        try:
            lock = _acquire_generation_lock(lock_registry, conversation_key)
            await lock.acquire()
            async with _memory_lock(request):
                history, question, memory_contents = (
                    _database(request).regeneration_context_for_assistant(
                        conversation_key, str(message_id)
                    )
                )
                try:
                    model_messages = build_model_messages(
                        history,
                        question,
                        memory_contents,
                        profile,
                        request.app.state.model_registry,
                    )
                except (MemoryCapacityError, ValueError) as error:
                    raise HTTPException(status_code=422, detail=str(error)) from error
                user_message_id = _database(request).regenerate_assistant_message(
                    conversation_key, str(message_id), body.expected_revision
                )
        except BaseException:
            if lock is not None and lock.locked():
                lock.release()
            await runtime.finish_generation()
            raise
        return await _generate_response(
            _database(request),
            _gateway(request, profile_id),
            lock_registry,
            conversation_key,
            user_message_id,
            model_messages,
            profile,
            runtime,
        )

    return application


app = create_app()
