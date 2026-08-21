from __future__ import annotations

import asyncio
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .agent import AgentError, AgentRunManager, AgentRunner
from .database import (
    MAX_TITLE_LENGTH,
    ConversationNotFoundError,
    ConversationOperationError,
    Database,
    GenerationConflictError,
    MessageNotFoundError,
    ProjectNotFoundError,
    RevisionConflictError,
    normalize_spaces,
)
from .development_tools import DevelopmentToolExecutor
from .memory import (
    EmptyMemoryCommandError,
    MemoryCapacityError,
    build_memory_context,
    ensure_memory_capacity,
    parse_memory_command,
)
from .file_tools import FileToolExecutor
from .model_controller import (
    ModelController,
    ModelControllerError,
    PowerShellModelController,
)
from .model_registry import LoadedModelRegistry, ModelProfile, load_model_registry
from .tool_calling import HttpToolCallingGateway, ToolCallingGateway, ToolDispatcher
from .workspace import WorkspaceGuard, WorkspacePathError


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
MESSAGE_TOKEN_OVERHEAD = 8
MAX_USER_MESSAGE_BYTES = 6000
MAX_STORED_ASSISTANT_BYTES = 32768
MAX_SEARCH_LENGTH = 100
ALLOWED_BROWSER_ORIGINS = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
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
    pass


class ModelResponseError(RuntimeError):
    pass


class ModelGateway(Protocol):
    async def generate(self, messages: list[dict[str, str]]) -> str: ...


def normalize_text(content: str, *, max_bytes: int, field_name: str) -> str:
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
    return any(
        pattern.search(content) is not None
        for pattern in (
            THINK_XML_OPEN,
            THINK_XML_CLOSE,
            THINK_BRACKET_OPEN,
            THINK_BRACKET_CLOSE,
        )
    )


def normalize_user_message(content: str) -> str:
    normalized = normalize_text(
        content,
        max_bytes=MAX_USER_MESSAGE_BYTES,
        field_name="Le message",
    )
    if contains_thinking_marker(normalized):
        raise ValueError("Le message contient un marqueur interne réservé.")
    if estimate_content_tokens(normalized) > CONTEXT_INPUT_TOKEN_BUDGET:
        raise ValueError("Le message est trop grand pour la fenêtre de contexte active.")
    return normalized


def normalize_title(title: str) -> str:
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
    if not isinstance(content, str) or "\x00" in content:
        raise ModelResponseError(MODEL_INVALID_RESPONSE_MESSAGE)
    answer = remove_thinking(content)
    if not answer or contains_internal_marker(answer):
        raise ModelResponseError(MODEL_INVALID_RESPONSE_MESSAGE)
    if len(answer.encode("utf-8")) > MAX_STORED_ASSISTANT_BYTES:
        raise ModelResponseError(MODEL_INVALID_RESPONSE_MESSAGE)
    return answer


def estimate_content_tokens(content: str) -> int:
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
        return normalize_user_message(content)

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, conversation_id: str | None) -> str | None:
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
        return normalize_title(title)


class EditMessageRequest(RevisionRequest):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, content: str) -> str:
        return normalize_user_message(content)


class StartAgentRunRequest(StrictRequest):
    """Valide la tâche textuelle; le projet et le profil viennent de l'état serveur."""

    task: str = Field(min_length=1, max_length=16_384)


class ConversationLockRegistry:
    """Un verrou de génération par conversation, distinct du verrou mémoire."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, conversation_id: str) -> asyncio.Lock:
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
    origin = request.headers.get("origin")
    if origin is not None and origin not in ALLOWED_BROWSER_ORIGINS:
        raise HTTPException(
            status_code=403,
            detail="Cette opération doit venir de l’interface locale de Léa.",
        )


def _database(request: Request) -> Database:
    return request.app.state.database


def _gateway(request: Request, profile_id: str) -> ModelGateway:
    """Retourne le faux gateway de test ou un client lié au profil figé."""

    fixed_gateway = request.app.state.fixed_model_gateway
    if fixed_gateway is not None:
        return fixed_gateway
    return HttpModelGateway(request.app.state.model_registry, profile_id)


def _locks(request: Request) -> ConversationLockRegistry:
    return request.app.state.conversation_locks


def _memory_lock(request: Request) -> asyncio.Lock:
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
    runtime = registry.document.runtime
    models_url = f"http://{runtime.host}:{runtime.port}{runtime.models_path}"
    expected_alias = registry.profile(profile_id).runtime.alias
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
    tool_calling_gateway: ToolCallingGateway | None = None,
) -> FastAPI:
    database = Database(database_path)
    workspace_guard = WorkspaceGuard(
        workspace_root or model_registry.document.workspace_root
    )
    file_tools = FileToolExecutor(
        database,
        workspace_guard,
        Path(checkpoint_root) if checkpoint_root is not None else model_registry.project_root / "data" / "agent-checkpoints",
    )
    development_tools = DevelopmentToolExecutor(
        database,
        workspace_guard,
        Path(agent_runtime_root) if agent_runtime_root is not None else model_registry.project_root / "data" / "agent-runtime",
    )
    tool_dispatcher = ToolDispatcher(file_tools, development_tools)
    agent_runs = AgentRunManager()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database.initialize()
        discovered = workspace_guard.discover_projects()
        database.sync_projects(
            [(project.name, project.relative_path) for project in discovered]
        )
        try:
            yield
        finally:
            await agent_runs.close()
            await development_tools.close()

    application = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.state.database = database
    application.state.model_registry = model_registry
    application.state.fixed_model_gateway = model_gateway
    application.state.model_controller = model_controller or PowerShellModelController()
    application.state.workspace_guard = workspace_guard
    application.state.file_tools = file_tools
    application.state.development_tools = development_tools
    application.state.tool_dispatcher = tool_dispatcher
    application.state.fixed_tool_calling_gateway = tool_calling_gateway
    application.state.agent_runs = agent_runs
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

    @application.exception_handler(ConversationNotFoundError)
    async def conversation_not_found_handler(
        _request: Request, error: ConversationNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.exception_handler(MessageNotFoundError)
    async def message_not_found_handler(
        _request: Request, error: MessageNotFoundError
    ) -> JSONResponse:
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

    @application.exception_handler(AgentError)
    async def agent_error_handler(
        _request: Request, error: AgentError
    ) -> JSONResponse:
        """Convertit les préconditions agent en conflit public sans traceback."""

        status_code = 404 if "introuvable" in str(error).casefold() else 409
        return JSONResponse(status_code=status_code, content={"detail": str(error)})

    @application.exception_handler(RevisionConflictError)
    async def revision_conflict_handler(
        _request: Request, error: RevisionConflictError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(GenerationConflictError)
    async def generation_conflict_handler(
        _request: Request, error: GenerationConflictError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(ConversationOperationError)
    async def operation_error_handler(
        _request: Request, error: ConversationOperationError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @application.exception_handler(MemoryCapacityError)
    async def memory_capacity_handler(
        _request: Request, error: MemoryCapacityError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @application.get("/health")
    def health() -> dict[str, str]:
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
        if status["loading_profile_id"]:
            state = "loading"
            message = "Changement de profil en cours."
        elif await _is_active_model_ready(request, status["active_profile_id"]):
            state = "ready"
            message = "Le profil actif est prêt."
        else:
            state = "error"
            message = "Le modèle actif n'est pas disponible."
        return {
            "state": state,
            "message": message,
            **status,
        }

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
    async def list_agent_runs(request: Request) -> dict[str, Any]:
        """Expose les runs mémoire récents sans transcript modèle ni contenu de fichiers."""

        manager: AgentRunManager = request.app.state.agent_runs
        records = sorted(manager.records.values(), key=lambda item: item.created_at, reverse=True)
        return {"runs": [record.public() for record in records[:20]]}

    @application.post("/api/agent-runs", status_code=202)
    async def start_agent_run(
        body: StartAgentRunRequest,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any]:
        """Lance en arrière-plan un run borné sur le profil et le projet actifs."""

        registry: LoadedModelRegistry = request.app.state.model_registry
        runtime = _runtime(request)
        status = await runtime.status()
        profile = registry.profile(status["active_profile_id"])
        if "agent_runs" not in profile.capabilities:
            raise HTTPException(status_code=409, detail="Active le profil Programmation avant de lancer un run.")
        project = _database(request).get_active_project()
        if project is None:
            raise HTTPException(status_code=409, detail="Sélectionne un projet actif avant le run.")
        request.app.state.workspace_guard.resolve_project(project["relative_path"])
        await runtime.begin_agent_run(profile.id)
        gateway = request.app.state.fixed_tool_calling_gateway or HttpToolCallingGateway(
            registry,
            profile.id,
        )
        runner = AgentRunner(
            registry,
            request.app.state.tool_dispatcher,
            gateway,
            registry.document.agent_policy,
        )
        try:
            record = await request.app.state.agent_runs.start(
                body.task,
                profile,
                project["id"],
                runner,
                runtime.finish_agent_run,
            )
        except BaseException:
            await runtime.finish_agent_run()
            raise
        return record.public()

    @application.get("/api/agent-runs/{run_id}")
    async def get_agent_run(run_id: str, request: Request) -> dict[str, Any]:
        """Retourne l'instantané courant d'un UUID de run connu."""

        return (await request.app.state.agent_runs.get(run_id)).public()

    @application.post("/api/agent-runs/{run_id}/cancel")
    async def cancel_agent_run(
        run_id: str,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any]:
        """Demande une annulation coopérative et ciblée du run indiqué."""

        record = await request.app.state.agent_runs.cancel(run_id)
        await request.app.state.development_tools.cancel_run(record.run_id)
        return record.public()

    @application.get("/api/conversations")
    def list_conversations(
        request: Request,
        search: str = Query(default="", max_length=MAX_SEARCH_LENGTH),
    ) -> dict[str, list[dict[str, Any]]]:
        if "\x00" in search:
            raise HTTPException(status_code=422, detail="La recherche contient un caractère NUL.")
        return {"conversations": _database(request).list_conversations(search)}

    @application.post("/api/conversations/messages", response_model=None)
    async def send_message(
        body: SendMessageRequest,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any] | JSONResponse:
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

        try:
            memory_command = parse_memory_command(body.message)
        except EmptyMemoryCommandError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        if memory_command is not None:
            # Les commandes explicites contournent entièrement le modèle : la
            # base écrit le souvenir, sa provenance et la confirmation atomiquement.
            async with _memory_lock(request):
                conversation_id = database_instance.apply_memory_command(
                    memory_command,
                    body.message,
                    body.conversation_id,
                    body.expected_revision,
                )
            return database_instance.get_conversation(conversation_id)

        runtime = _runtime(request)
        profile_id = await runtime.begin_generation()
        profile = request.app.state.model_registry.profile(profile_id)
        gateway = _gateway(request, profile_id)
        generation_handed_off = False
        try:
            if body.conversation_id is None:
                async with _memory_lock(request):
                    memory_contents = [
                        memory["content"]
                        for memory in database_instance.list_memories()
                    ]
                    try:
                        model_messages = build_model_messages(
                            [],
                            body.message,
                            memory_contents,
                            profile,
                            request.app.state.model_registry,
                        )
                    except (MemoryCapacityError, ValueError) as error:
                        raise HTTPException(status_code=422, detail=str(error)) from error
                    conversation_id, user_message_id = (
                        database_instance.create_pending_conversation(body.message)
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
                                body.message,
                                memory_contents,
                                profile,
                                request.app.state.model_registry,
                            )
                        except (MemoryCapacityError, ValueError) as error:
                            raise HTTPException(status_code=422, detail=str(error)) from error
                        user_message_id = database_instance.add_pending_message(
                            conversation_id, body.message, body.expected_revision
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
        return _database(request).get_conversation(str(conversation_id))

    @application.patch("/api/conversations/{conversation_id}")
    def rename_conversation(
        conversation_id: UUID,
        body: RenameConversationRequest,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, Any]:
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
        try:
            edited_memory_command = parse_memory_command(body.content)
        except EmptyMemoryCommandError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if edited_memory_command is not None:
            raise HTTPException(
                status_code=400,
                detail="Une commande mémoire doit être envoyée comme nouveau message.",
            )
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
                history, _old_question, memory_contents = (
                    _database(request).generation_context_before(
                        conversation_key, str(message_id)
                    )
                )
                try:
                    model_messages = build_model_messages(
                        history,
                        body.content,
                        memory_contents,
                        profile,
                        request.app.state.model_registry,
                    )
                except (MemoryCapacityError, ValueError) as error:
                    raise HTTPException(status_code=422, detail=str(error)) from error
                user_message_id = _database(request).edit_user_message(
                    conversation_key,
                    str(message_id),
                    body.content,
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
