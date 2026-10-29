from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .inference import (
    MODEL_INVALID_RESPONSE_MESSAGE,
    MODEL_UNAVAILABLE_MESSAGE,
    ModelContextError,
    ModelResponseError,
    ModelTruncatedError,
    ModelUnavailableError,
    inference_adapter,
    reasoning_directive,
)
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
from .preferences import PreferencesError, PreferencesStore, ReasoningLevel
from .resources import ResourceMonitor
from .dynamic_browser import EdgeDynamicPageReader
from .web_gateway import (
    SafeHttpFetcher,
    WebAuthorizationError,
    WebAuthorizationManager,
    WebCancelledError,
    WebGateway,
    WebGatewayError,
    WebNetworkError,
    WebPolicyError,
    WebResearch,
    WebTimeoutError,
    WebUnavailableError,
    build_web_augmented_question,
    classify_web_request,
    compact_web_context,
    current_information_unavailable_message,
    insufficient_research_message,
    is_web_confirmation,
    missing_web_confirmation_message,
    requires_current_web_verification,
    replace_web_prompt_context,
    validate_local_answer,
    validate_web_answer,
    web_confirmation_message,
    web_disabled_message,
)


LOGGER = logging.getLogger(__name__)
WEB_SYNTHESIS_FAILURE_MESSAGE = (
    "Des sources Web ont été collectées, mais le modèle local de Léa n’a pas "
    "produit de synthèse exploitable. Renvoie une nouvelle demande Web explicite "
    "pour réessayer."
)
WEB_SIMPLE_RESPONSE_TOKENS = 512
WEB_PROMPT_SAFETY_TOKENS = 64
WEB_EXCERPT_CAPS = (900, 700, 500, 350, 250, 150, 100)


MODEL_REGISTRY = load_model_registry(os.environ.get("LEA_MODEL_REGISTRY") or None)
DEFAULT_PROFILE_ID = MODEL_REGISTRY.document.default_profile_id
DEFAULT_PROFILE = MODEL_REGISTRY.profile(DEFAULT_PROFILE_ID)
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
    for profile in MODEL_REGISTRY.resolved_profiles()
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
REASONING_DIRECTIVE_PATTERN = re.compile(r"/\s*(?:no_think|think)\b", re.IGNORECASE)


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
            REASONING_DIRECTIVE_PATTERN,
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
    reasoning_level: ReasoningLevel = "low",
) -> list[dict[str, str]]:
    """Conserve le suffixe récent de paires complètes qui tient dans le profil."""

    input_budget = (
        profile.context_tokens
        - profile.generation.max_tokens
        - profile.generation.system_template_reserve_tokens
    )
    internal_question = build_internal_user_message(
        question, memory_contents, profile, reasoning_level,
    )
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
    reasoning_level: ReasoningLevel = "low",
) -> list[dict[str, str]]:
    """Construit le contexte d'un profil à partir du registre lié à l'application."""

    retained = select_history_for_context(
        stored_history, question, memory_contents, profile, reasoning_level,
    )
    internal_question = build_internal_user_message(
        question, memory_contents, profile, reasoning_level,
    )
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
    reasoning_level: ReasoningLevel = "low",
) -> str:
    """Entoure la question des souvenirs-données et de la directive interne choisie."""

    directive = reasoning_directive(
        profile, high=profile.id == "general" and reasoning_level == "high",
    )
    suffix = f"\n{directive}" if directive else ""
    if not memory_contents:
        return f"{question}{suffix}"
    ensure_memory_capacity(memory_contents)
    memory_context = build_memory_context(memory_contents)
    return (
        f"{memory_context}\n\n"
        "QUESTION ACTUELLE DE L’UTILISATEUR\n"
        f"{question}{suffix}"
    )


class HttpModelGateway:
    """Relie l’inférence au filtrage de publication, indépendant du moteur et du modèle."""

    def __init__(
        self,
        registry: LoadedModelRegistry = MODEL_REGISTRY,
        profile_id: str = DEFAULT_PROFILE_ID,
        reasoning_level: ReasoningLevel = "low",
    ) -> None:
        """Fige l’adaptateur du profil actif sans charger de modèle supplémentaire."""

        self.adapter = inference_adapter(registry, profile_id)
        self.high_reasoning = reasoning_level == "high"
        self.url = self.adapter.chat_url
        self.web_max_tokens: int | None = None

    async def generate(self, messages: list[dict[str, str]]) -> str:
        """Filtre toute réponse avant qu’elle puisse atteindre SQLite ou l’interface."""

        return filter_final_answer(
            await self.adapter.generate(
                messages,
                high_reasoning=self.high_reasoning,
                max_tokens=self.web_max_tokens,
            )
        )


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SendMessageRequest(StrictRequest):
    conversation_id: str | None = None
    message: str
    expected_revision: int | None = Field(default=None, ge=0)
    expected_profile_id: str | None = Field(default=None, max_length=128)
    web_request_id: str | None = None

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

    @field_validator("web_request_id")
    @classmethod
    def validate_web_request_id(cls, request_id: str | None) -> str | None:
        """Canonicalise l'identifiant éphémère utilisé uniquement pour annuler le Web."""

        if request_id is None:
            return None
        try:
            return str(UUID(request_id))
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("L’identifiant de recherche Web est invalide.") from error


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
    expected_profile_id: str | None = Field(default=None, max_length=128)
    expected_project_id: str | None = Field(default=None, max_length=36)
    record_conversation: bool = False
    conversation_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_conversation(self) -> StartAgentRunRequest:
        """Validate a recorded task before reserving a run or touching its checkpoint."""
        if self.record_conversation:
            self.task = normalize_received_user_message(self.task)
            if (self.conversation_id is None) != (self.expected_revision is None):
                raise ValueError("Conversation et révision doivent être fournies ensemble.")
            if self.conversation_id is not None:
                self.conversation_id = str(UUID(self.conversation_id))
        elif self.conversation_id is not None or self.expected_revision is not None:
            raise ValueError("L’enregistrement de conversation n’est pas demandé.")
        return self


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

    def __init__(self, active_profile_id: str, database: Database | None = None) -> None:
        """Démarre toujours sur le profil par défaut déclaré par le registre."""

        self.active_profile_id = active_profile_id
        self.switching_profile_id: str | None = None
        self.active_generations = 0
        self.active_agent_runs = 0
        self._lock = asyncio.Lock()
        self.database = database

    def _recovery_pending(self) -> bool:
        """Detect persisted runs not owned by this instance without inventing a terminal state."""

        return bool(
            not self.active_agent_runs and self.database is not None
            and self.database.list_incomplete_agent_runs()
        )

    def _require_recovered(self) -> None:
        """Prevent new model activity until orphaned containers have a verified shutdown."""

        if self._recovery_pending():
            raise GenerationConflictError(
                "Un run attend un arrêt vérifié. Vérifie Docker puis redémarre Léa."
            )

    async def begin_generation(self) -> str:
        """Fige le profil d'une réponse et interdit une génération pendant une bascule."""

        async with self._lock:
            self._require_recovered()
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
            self._require_recovered()
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
            self._require_recovered()
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
                "agent_run_active": self.active_agent_runs > 0 or self._recovery_pending(),
                "recovery_pending": self._recovery_pending(),
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


def _conversation_with_web_state(
    request: Request,
    conversation_id: str,
) -> dict[str, Any]:
    """Ajoute uniquement l'attente Web éphémère à l'état persistant retourné."""

    detail = _database(request).get_conversation(conversation_id)
    detail["web_confirmation_pending"] = request.app.state.web_authorization.has_pending(
        conversation_id
    )
    return detail


def _reasoning_level(request: Request, profile: ModelProfile) -> ReasoningLevel:
    """Fige le choix avant génération ; une sauvegarde ultérieure ne modifie pas la requête."""

    if profile.reasoning_preference is None or profile.model.reasoning_control == "none":
        return "low"
    try:
        return getattr(
            request.app.state.preferences.read(),
            profile.reasoning_preference,
        )
    except PreferencesError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _current_information_web_availability(
    request: Request,
    question: str,
) -> bool | None:
    """Lit le réglage uniquement pour un tour local qui exige une donnée actuelle."""

    if not requires_current_web_verification(question):
        return None
    try:
        return request.app.state.preferences.read().web_enabled
    except PreferencesError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _is_persisted_web_failure(
    database: Database,
    conversation_id: str,
    message_id: str,
) -> bool:
    """Repère un échec Web sans déduire son origine depuis le texte utilisateur."""

    conversation = database.get_conversation(conversation_id)
    message = next(
        (item for item in conversation["messages"] if item["id"] == message_id),
        None,
    )
    return bool(
        message is not None
        and isinstance(message.get("failure_kind"), str)
        and message["failure_kind"].startswith("web_")
    )


def _gateway(
    request: Request,
    profile_id: str,
    reasoning_level: ReasoningLevel = "low",
) -> ModelGateway:
    """Retourne le faux gateway de test ou un client lié au profil figé."""

    fixed_gateway = request.app.state.fixed_model_gateway
    if fixed_gateway is not None:
        return fixed_gateway
    return HttpModelGateway(
        request.app.state.model_registry,
        profile_id,
        reasoning_level,
    )


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
    adapter = inference_adapter(request.app.state.model_registry, profile_id)
    return await adapter.is_ready()


def _safe_failure_code(error: BaseException) -> tuple[int, str, str]:
    """Traduit une erreur interne en statut, message public et code persistant."""

    if isinstance(error, ModelContextError):
        return 422, str(error), "model_error"
    if isinstance(error, ModelTruncatedError):
        return 502, str(error), "model_error"
    if isinstance(error, ModelUnavailableError):
        return 503, MODEL_UNAVAILABLE_MESSAGE, "model_unavailable"
    if isinstance(error, asyncio.CancelledError):
        return 503, "La génération a été interrompue.", "interrupted"
    if isinstance(error, WebCancelledError):
        return 409, str(error), "interrupted"
    if isinstance(error, (MemoryCapacityError, ValueError)):
        return 422, str(error), "model_error"
    return 502, MODEL_INVALID_RESPONSE_MESSAGE, "model_error"


def _safe_web_failure(error: WebGatewayError) -> tuple[int, str]:
    """Traduit un échec Web sans publier d'adresse IP ni de détail de transport."""

    if isinstance(error, WebPolicyError):
        return 422, "model_error"
    if isinstance(error, WebAuthorizationError):
        return 409, "model_error"
    if isinstance(error, WebCancelledError):
        return 409, "interrupted"
    if isinstance(error, WebTimeoutError):
        return 504, "model_error"
    if isinstance(error, WebNetworkError):
        return 503, "model_error"
    if isinstance(error, WebUnavailableError):
        return 502, "model_error"
    return 502, "model_error"


async def _prepare_web_prompt(
    model_messages: list[dict[str, str]],
    research: WebResearch,
    query: str,
    profile: ModelProfile,
    gateway: HttpModelGateway,
) -> tuple[list[dict[str, str]], int]:
    """Borne le prompt Web avec le vrai template et tokenizer du modèle actif."""

    output_tokens = min(
        profile.generation.max_tokens,
        WEB_SIMPLE_RESPONSE_TOKENS if research.mode == "simple" else profile.generation.max_tokens,
    )
    max_prompt_tokens = profile.context_tokens - output_tokens - WEB_PROMPT_SAFETY_TOKENS
    if max_prompt_tokens <= 0:
        raise ModelContextError(context_tokens=profile.context_tokens)

    original_user = model_messages[-1]["content"]
    last_count: int | None = None
    for excerpt_cap in (None, *WEB_EXCERPT_CAPS):
        if excerpt_cap is None:
            candidate = model_messages
        else:
            compact = compact_web_context(query, research, excerpt_cap)
            revised_user = replace_web_prompt_context(original_user, research, compact)
            candidate = [
                *model_messages[:-1],
                {**model_messages[-1], "content": revised_user},
            ]
        last_count = await gateway.adapter.prompt_token_count(
            candidate, high_reasoning=gateway.high_reasoning
        )
        if last_count <= max_prompt_tokens:
            gateway.web_max_tokens = output_tokens
            LOGGER.info(
                "web_prompt_prepared profile_id=%s mode=%s sources=%d "
                "prompt_tokens=%d context_tokens=%d output_tokens=%d excerpt_cap=%s",
                profile.id,
                research.mode,
                len(research.sources),
                last_count,
                profile.context_tokens,
                output_tokens,
                excerpt_cap if excerpt_cap is not None else "full",
            )
            return candidate, last_count
    raise ModelContextError(last_count, profile.context_tokens)


async def _generate_response(
    database: Database,
    gateway: ModelGateway,
    locks: ConversationLockRegistry,
    conversation_id: str,
    user_message_id: str,
    model_messages: list[dict[str, str]],
    profile: ModelProfile,
    runtime: RuntimeCoordinator,
    web_research: WebResearch | None = None,
    cancellation: asyncio.Event | None = None,
    current_information_web_available: bool | None = None,
    web_authorization: WebAuthorizationManager | None = None,
    pending_web_query: str | None = None,
    web_query: str | None = None,
) -> dict[str, Any] | JSONResponse:
    """Finalise une réponse locale sûre ou une génération réellement exécutée."""

    lock = locks.get(conversation_id)
    stage = "preflight"
    prompt_tokens: int | None = None
    model_started_at: float | None = None
    try:
        insufficient_research = (
            web_research is not None
            and web_research.mode == "deep"
            and not web_research.evidence_is_sufficient
        )
        model_was_used = (
            current_information_web_available is None and not insufficient_research
        )
        if current_information_web_available is not None:
            answer = current_information_unavailable_message(
                current_information_web_available
            )
        elif insufficient_research and web_research is not None:
            answer = insufficient_research_message(web_research)
        else:
            if web_research is not None and web_query is not None and isinstance(gateway, HttpModelGateway):
                model_messages, prompt_tokens = await _prepare_web_prompt(
                    model_messages, web_research, web_query, profile, gateway
                )
            stage = "model_call"
            model_started_at = time.monotonic()
            if cancellation is None:
                answer = await gateway.generate(model_messages)
            else:
                generation_task = asyncio.create_task(gateway.generate(model_messages))
                cancellation_task = asyncio.create_task(cancellation.wait())
                done, _pending = await asyncio.wait(
                    {generation_task, cancellation_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancellation_task in done:
                    generation_task.cancel()
                    await asyncio.gather(generation_task, return_exceptions=True)
                    raise WebCancelledError("La recherche Web a été annulée.")
                cancellation_task.cancel()
                await asyncio.gather(cancellation_task, return_exceptions=True)
                answer = await generation_task
            if web_research is not None:
                LOGGER.info(
                    "web_model_completed conversation_id=%s message_id=%s "
                    "duration_ms=%d output_chars=%d prompt_tokens=%s",
                    conversation_id,
                    user_message_id,
                    round((time.monotonic() - model_started_at) * 1000),
                    len(answer),
                    prompt_tokens if prompt_tokens is not None else "unknown",
                )
        stage = "answer_filter"
        answer = filter_final_answer(answer)
        if web_research is not None:
            stage = "web_validation"
            validated = validate_web_answer(answer, web_research)
            if validated != answer:
                LOGGER.info(
                    "web_validation_replaced conversation_id=%s message_id=%s "
                    "mode=%s",
                    conversation_id,
                    user_message_id,
                    web_research.mode,
                )
            answer = validated
        elif model_was_used:
            answer = validate_local_answer(answer)
        database.complete_generation(
            conversation_id,
            user_message_id,
            answer,
            model_id=profile.runtime.alias if model_was_used else None,
            profile_id=profile.id,
            web_sources=(
                [source.as_dict() for source in web_research.sources]
                if web_research is not None
                else []
            ),
        )
        detail = database.get_conversation(conversation_id)
        if (
            current_information_web_available is True
            and web_authorization is not None
            and pending_web_query is not None
        ):
            web_authorization.remember_pending(
                conversation_id,
                pending_web_query,
                user_message_id,
                profile.id,
                int(detail["revision"]),
            )
        if web_authorization is not None:
            detail["web_confirmation_pending"] = web_authorization.has_pending(
                conversation_id
            )
        return detail
    except BaseException as error:
        if web_research is not None:
            LOGGER.warning(
                "web_synthesis_failed conversation_id=%s message_id=%s mode=%s "
                "sources=%d stage=%s error=%s prompt_tokens=%s "
                "model_duration_ms=%s",
                conversation_id,
                user_message_id,
                web_research.mode,
                len(web_research.sources),
                stage,
                type(error).__name__,
                (
                    error.prompt_tokens
                    if isinstance(error, ModelContextError)
                    else prompt_tokens
                ) or "unknown",
                round((time.monotonic() - model_started_at) * 1000)
                if model_started_at is not None else "none",
            )
        status_code, public_message, error_code = _safe_failure_code(error)
        if web_research is not None and type(error) is ModelResponseError:
            public_message = WEB_SYNTHESIS_FAILURE_MESSAGE
        if isinstance(error, WebGatewayError):
            failure_kind = error.code
        elif web_research is not None:
            # Le schéma existant reconnaît ce code Web ; un échec de synthèse
            # ne doit pas redevenir un réessai local sans nouvel accord.
            failure_kind = "web_error"
        else:
            failure_kind = None
        try:
            database.fail_generation(
                conversation_id,
                user_message_id,
                error_code,
                failure_kind,
            )
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
    web_gateway: WebGateway | None = None,
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
        # The default profile is already selected at backend startup. Tests
        # injecting a model gateway keep OS probes dormant unless opted in.
        application.state.resource_monitor.set_active(
            model_gateway is None, profile_id=model_registry.document.default_profile_id
        )
        application.state.resource_monitor.start()
        try:
            yield
        finally:
            try:
                await openhands_runs.close()
            finally:
                await application.state.resource_monitor.close()

    application = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.state.database = database
    application.state.preferences = PreferencesStore(database)
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
    application.state.web_authorization = (
        web_gateway.authorization if web_gateway is not None else WebAuthorizationManager()
    )
    if web_gateway is None:
        # Le lecteur Edge ne lance rien ici : il reste un dernier recours créé
        # uniquement pendant une collecte Web explicitement autorisée.
        web_fetcher = SafeHttpFetcher()
        web_gateway = WebGateway(
            application.state.web_authorization,
            fetcher=web_fetcher,
            dynamic_reader=EdgeDynamicPageReader(
                web_fetcher,
                model_registry.project_root / "data" / "browser-sessions",
            ),
        )
    application.state.web_gateway = web_gateway
    application.state.web_cancellations: dict[str, asyncio.Event] = {}
    application.state.runtime_coordinator = RuntimeCoordinator(
        model_registry.document.default_profile_id, database
    )

    async def resource_services() -> dict:
        """Observe the selected model; probe Docker only for an OpenHands workload."""

        state = await application.state.runtime_coordinator.status()
        profile_id = state["loading_profile_id"] or state["active_profile_id"]
        profile = model_registry.profile(profile_id)
        # An interrupted Programming run still needs Docker diagnostics even
        # when a fresh backend has selected its default conversation profile.
        openhands_required = profile.agent_engine == "OpenHands" or state["recovery_pending"]
        model = await inference_adapter(model_registry, profile_id).is_ready()
        docker = await openhands_runtime.docker_available() if openhands_required else None
        agent = (
            await openhands_runtime._agent_server_available()
            if openhands_required and state["agent_run_active"] else None
        )
        return {
            "openhands_required": openhands_required,
            "backend_available": True, "docker_available": docker, "model_available": model,
            "agent_server_available": agent, "run_active": state["agent_run_active"],
            "loading": state["loading_profile_id"] is not None,
        }

    application.state.resource_monitor = ResourceMonitor(
        model_registry.document.resource_policies[
            model_registry.profile(model_registry.document.default_profile_id).resource_policy
        ],
        resource_services,
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
        if status["recovery_pending"]:
            state = "error"
            message = "Un run attend un arrêt vérifié. Vérifie Docker puis redémarre Léa."
        elif status["loading_profile_id"]:
            state = "loading"
            message = "Changement de profil en cours."
        elif (
            status["active_profile_id"] == "development"
            and request.app.state.fixed_model_gateway is None
        ):
            # Hors run, l'absence de serveur est volontaire, pas une panne.
            readiness = await request.app.state.openhands_runtime.status(
                require_agent_server=bool(status["agent_run_active"])
            )
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

    @application.get("/api/resources")
    async def resource_status(request: Request) -> dict:
        """Expose an in-memory snapshot, never paths, commands or persistent telemetry."""

        return request.app.state.resource_monitor.snapshot()

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
        previous_profile_id = await runtime.begin_switch(profile_id)
        monitor = request.app.state.resource_monitor
        if request.app.state.fixed_model_gateway is None:
            monitor.set_active(
                True, profile_id=profile_id,
                policy=registry.document.resource_policies[profile.resource_policy],
            )
        succeeded = False
        rolled_back = False
        try:
            active_profile_id = await request.app.state.model_controller.activate(
                profile_id,
                previous_profile_id,
            )
            succeeded = active_profile_id == profile_id
            rolled_back = not succeeded
        except ModelControllerError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        finally:
            await runtime.finish_switch(succeeded=succeeded)
            if request.app.state.fixed_model_gateway is None:
                # A failed activation must restore the previous profile's
                # thresholds and diagnostics, not those of the requested one.
                current_profile = registry.profile(runtime.active_profile_id)
                monitor.set_active(
                    True, profile_id=current_profile.id,
                    policy=registry.document.resource_policies[current_profile.resource_policy],
                )
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
        if (
            body.expected_profile_id is not None and body.expected_profile_id != profile.id
            or body.expected_project_id is not None and body.expected_project_id != project["id"]
        ):
            raise HTTPException(status_code=409, detail="Le profil ou le projet a changé. Recommence l’intervention.")
        frozen = request.app.state.workspace_guard.freeze_project(
            project["id"], project["relative_path"]
        )
        await runtime.begin_agent_run(profile.id)
        try:
            conversation_options = {
                "record_conversation": True,
                "conversation_id": body.conversation_id,
                "expected_revision": body.expected_revision,
            } if body.record_conversation else {}
            record = await request.app.state.openhands_runs.start(
                body.task,
                profile,
                frozen,
                runtime.finish_agent_run,
                **conversation_options,
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

    @application.post("/api/web/operations/{operation_id}/cancel")
    def cancel_web_operation(
        operation_id: UUID,
        request: Request,
        _local: None = Depends(require_local_mutation),
    ) -> dict[str, str]:
        """Annule une collecte active sans créer une autorisation ou un nouvel accès."""

        event = request.app.state.web_cancellations.get(str(operation_id))
        if event is None:
            raise HTTPException(status_code=404, detail="Cette recherche Web n’est plus active.")
        event.set()
        return {"status": "cancelling"}

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
        registered_web_operation_id: str | None = None
        try:
            if body.expected_profile_id is not None and body.expected_profile_id != profile_id:
                raise HTTPException(status_code=409, detail="Le profil a changé. Recommence l’intervention.")
            profile = request.app.state.model_registry.profile(profile_id)
            authorization: WebAuthorizationManager = request.app.state.web_authorization
            confirmation_answer = is_web_confirmation(body.message)
            web_intent = (
                "pending_confirmation"
                if confirmation_answer
                else classify_web_request(body.message)
            )
            web_query = body.message
            if (
                body.web_request_id is not None
                and body.web_request_id in request.app.state.web_cancellations
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Cet identifiant de recherche Web est déjà actif.",
                )
            if (
                body.conversation_id is not None
                and not confirmation_answer
                and web_intent != "confirmation"
            ):
                authorization.discard_pending(body.conversation_id)
            if web_intent != "local":
                try:
                    web_enabled = request.app.state.preferences.read().web_enabled
                except PreferencesError as error:
                    raise HTTPException(status_code=503, detail=str(error)) from error
                if not web_enabled:
                    web_intent = "disabled"
                    if body.conversation_id is not None:
                        authorization.discard_pending(body.conversation_id)
            if (
                profile.agent_engine == "OpenHands"
                and request.app.state.fixed_model_gateway is None
                and web_intent == "local"
            ):
                # The Programming brain is reserved for the OpenHands SDK
                # path. A Web turn remains conversationnel et ne donne aucun
                # accès réseau au terminal ou au conteneur OpenHands.
                raise HTTPException(
                    status_code=409,
                    detail="Utilise une tâche Programmation sur un projet sélectionné.",
                )
            try:
                message = normalize_user_message(body.message, profile)
                memory_command = parse_memory_command(message)
            except (EmptyMemoryCommandError, ValueError) as error:
                raise HTTPException(status_code=422, detail=str(error)) from error

            if memory_command is not None and web_intent == "local":
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

            reasoning_level = _reasoning_level(request, profile)
            current_information_web_available = (
                _current_information_web_availability(request, message)
                if web_intent == "local"
                else None
            )
            gateway = _gateway(request, profile_id, reasoning_level)
            if body.conversation_id is None:
                async with _memory_lock(request):
                    stored_history: list[dict[str, str]] = []
                    memory_contents = [
                        memory["content"]
                        for memory in database_instance.list_memories()
                    ]
                    try:
                        model_messages = build_model_messages(
                            stored_history,
                            message,
                            memory_contents,
                            profile,
                            request.app.state.model_registry,
                            reasoning_level,
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
                            and message.get("agent_run_id") is None
                        ]
                        try:
                            model_messages = build_model_messages(
                                stored_history,
                                message,
                                memory_contents,
                                profile,
                                request.app.state.model_registry,
                                reasoning_level,
                            )
                        except (MemoryCapacityError, ValueError) as error:
                            raise HTTPException(status_code=422, detail=str(error)) from error
                        user_message_id = database_instance.add_pending_message(
                            conversation_id,
                            message,
                            body.expected_revision,
                            allow_after_failed_web=web_intent == "authorized",
                        )
                except BaseException:
                    lock.release()
                    raise

            LOGGER.info(
                "web_route conversation_id=%s message_id=%s profile_id=%s intent=%s "
                "confirmation=%s operation_id_provided=%s",
                conversation_id,
                user_message_id,
                profile.id,
                web_intent,
                confirmation_answer,
                body.web_request_id is not None,
            )

            if web_intent == "confirmation":
                try:
                    database_instance.complete_generation(
                        conversation_id,
                        user_message_id,
                        web_confirmation_message(message),
                        profile_id=profile.id,
                    )
                    detail = database_instance.get_conversation(conversation_id)
                    authorization.remember_pending(
                        conversation_id,
                        message,
                        user_message_id,
                        profile.id,
                        int(detail["revision"]),
                    )
                    return _conversation_with_web_state(request, conversation_id)
                finally:
                    if lock.locked():
                        lock.release()

            if web_intent == "disabled":
                try:
                    database_instance.complete_generation(
                        conversation_id,
                        user_message_id,
                        web_disabled_message(),
                        profile_id=profile.id,
                    )
                    return _conversation_with_web_state(request, conversation_id)
                finally:
                    if lock.locked():
                        lock.release()

            if web_intent == "pending_confirmation":
                pending = (
                    authorization.confirm_pending(
                        conversation_id,
                        message,
                        profile_id=profile.id,
                        conversation_revision=int(body.expected_revision),
                    )
                    if body.conversation_id is not None
                    and body.expected_revision is not None
                    else None
                )
                if pending is not None:
                    current_detail = database_instance.get_conversation(conversation_id)
                    source_message = next(
                        (
                            item
                            for item in current_detail["messages"]
                            if item["id"] == pending.source_message_id
                        ),
                        None,
                    )
                    if (
                        source_message is None
                        or source_message["role"] != "user"
                        or source_message["status"] != "completed"
                        or source_message["content"] != pending.query
                    ):
                        pending = None
                if pending is None:
                    try:
                        database_instance.complete_generation(
                            conversation_id,
                            user_message_id,
                            missing_web_confirmation_message(),
                            profile_id=profile.id,
                        )
                        return _conversation_with_web_state(request, conversation_id)
                    finally:
                        if lock.locked():
                            lock.release()
                web_intent = "authorized"
                web_query = pending.query

            web_research: WebResearch | None = None
            if web_intent == "authorized":
                permit = authorization.issue(web_query)
                cancellation = asyncio.Event()
                if body.web_request_id is not None:
                    request.app.state.web_cancellations[body.web_request_id] = cancellation
                    registered_web_operation_id = body.web_request_id

                async def web_cancelled() -> bool:
                    """Réunit l'annulation explicite et la fermeture du client local."""

                    return cancellation.is_set() or await request.is_disconnected()

                try:
                    web_research = await request.app.state.web_gateway.retrieve(
                        permit,
                        cancelled=web_cancelled,
                    )
                    LOGGER.info(
                        "web_retrieval_completed conversation_id=%s message_id=%s "
                        "mode=%s sources=%d read_sources=%d context_chars=%d",
                        conversation_id,
                        user_message_id,
                        web_research.mode,
                        len(web_research.sources),
                        sum(
                            source.retrieval_status == "read"
                            for source in web_research.sources
                        ),
                        len(web_research.context),
                    )
                    try:
                        # Une nouvelle collecte possède son propre jeu de sources.
                        # L'historique n'est ni une preuve du tour ni nécessaire à
                        # la reformulation de la requête déjà conservée côté serveur.
                        model_messages = build_model_messages(
                            [],
                            build_web_augmented_question(web_query, web_research),
                            memory_contents,
                            profile,
                            request.app.state.model_registry,
                            reasoning_level,
                        )
                    except (MemoryCapacityError, ValueError) as error:
                        raise WebUnavailableError(
                            "Les extraits Web ne tiennent pas dans le contexte local actif. Reformule la demande."
                        ) from error
                except WebGatewayError as error:
                    LOGGER.warning(
                        "web_retrieval_failed conversation_id=%s message_id=%s "
                        "code=%s error=%s",
                        conversation_id,
                        user_message_id,
                        error.code,
                        type(error).__name__,
                    )
                    status_code, error_code = _safe_web_failure(error)
                    database_instance.fail_generation(
                        conversation_id,
                        user_message_id,
                        error_code,
                        error.code,
                    )
                    if lock.locked():
                        lock.release()
                    return JSONResponse(
                        status_code=status_code,
                        content={
                            "detail": str(error),
                            "conversation": database_instance.get_conversation(conversation_id),
                        },
                    )

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
                web_research,
                cancellation if body.web_request_id is not None else None,
                current_information_web_available=current_information_web_available,
                web_authorization=authorization,
                pending_web_query=message,
                web_query=web_query if web_research is not None else None,
            )
        finally:
            if registered_web_operation_id is not None:
                request.app.state.web_cancellations.pop(registered_web_operation_id, None)
            if not generation_handed_off:
                await runtime.finish_generation()

    @application.get("/api/conversations/{conversation_id}")
    def get_conversation(conversation_id: UUID, request: Request) -> dict[str, Any]:
        """Retourne une conversation complète depuis son UUID canonique."""

        return _conversation_with_web_state(request, str(conversation_id))

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
        database_instance = _database(request)
        if _is_persisted_web_failure(
            database_instance,
            conversation_key,
            str(message_id),
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Une recherche Web échouée exige une nouvelle autorisation. "
                    "Renvoie la demande comme nouveau message."
                ),
            )
        lock_registry = _locks(request)
        runtime = _runtime(request)
        profile_id = await runtime.begin_generation()
        profile = request.app.state.model_registry.profile(profile_id)
        lock: asyncio.Lock | None = None
        try:
            reasoning_level = _reasoning_level(request, profile)
            lock = _acquire_generation_lock(lock_registry, conversation_key)
            await lock.acquire()
            async with _memory_lock(request):
                history, question, memory_contents = (
                    _database(request).generation_context_before(
                        conversation_key, str(message_id)
                    )
                )
                if classify_web_request(question) != "local":
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Une recherche Web échouée exige une nouvelle autorisation. "
                            "Renvoie la demande comme nouveau message."
                        ),
                    )
                current_information_web_available = (
                    _current_information_web_availability(request, question)
                )
                try:
                    model_messages = build_model_messages(
                        history,
                        question,
                        memory_contents,
                        profile,
                        request.app.state.model_registry,
                        reasoning_level,
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
            _gateway(request, profile_id, reasoning_level),
            lock_registry,
            conversation_key,
            user_message_id,
            model_messages,
            profile,
            runtime,
            current_information_web_available=current_information_web_available,
            web_authorization=request.app.state.web_authorization,
            pending_web_query=question,
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
        database_instance = _database(request)
        if _is_persisted_web_failure(
            database_instance,
            conversation_key,
            str(message_id),
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Une recherche Web échouée doit être renvoyée comme nouveau message "
                    "avec une nouvelle autorisation."
                ),
            )
        lock_registry = _locks(request)
        runtime = _runtime(request)
        profile_id = await runtime.begin_generation()
        lock: asyncio.Lock | None = None
        try:
            profile = request.app.state.model_registry.profile(profile_id)
            reasoning_level = _reasoning_level(request, profile)
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
            if classify_web_request(content) != "local":
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Une demande Web modifiée doit être envoyée comme nouveau message "
                        "avec une nouvelle autorisation."
                    ),
                )
            current_information_web_available = (
                _current_information_web_availability(request, content)
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
                        reasoning_level,
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
            _gateway(request, profile_id, reasoning_level),
            lock_registry,
            conversation_key,
            user_message_id,
            model_messages,
            profile,
            runtime,
            current_information_web_available=current_information_web_available,
            web_authorization=request.app.state.web_authorization,
            pending_web_query=content,
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
            reasoning_level = _reasoning_level(request, profile)
            current = _database(request).get_conversation(conversation_key)
            regenerated = next(
                (item for item in current["messages"] if item["id"] == str(message_id)),
                None,
            )
            if regenerated is not None and regenerated.get("web_sources"):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Une réponse Web ne peut pas être régénérée sans nouvelle "
                        "autorisation. Renvoie la demande."
                    ),
                )
            lock = _acquire_generation_lock(lock_registry, conversation_key)
            await lock.acquire()
            async with _memory_lock(request):
                history, question, memory_contents = (
                    _database(request).regeneration_context_for_assistant(
                        conversation_key, str(message_id)
                    )
                )
                current_information_web_available = (
                    _current_information_web_availability(request, question)
                )
                try:
                    model_messages = build_model_messages(
                        history,
                        question,
                        memory_contents,
                        profile,
                        request.app.state.model_registry,
                        reasoning_level,
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
            _gateway(request, profile_id, reasoning_level),
            lock_registry,
            conversation_key,
            user_message_id,
            model_messages,
            profile,
            runtime,
            current_information_web_available=current_information_web_available,
            web_authorization=request.app.state.web_authorization,
            pending_web_query=question,
        )

    return application


app = create_app()
