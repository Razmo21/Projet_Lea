"""Tool calling OpenAI strict pour Qwen3-Coder servi localement par llama.cpp."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from .development_tools import DEVELOPMENT_ARGUMENT_MODELS, DevelopmentToolExecutor
from .file_tools import TOOL_ARGUMENT_MODELS, FileToolExecutor
from .model_registry import LoadedModelRegistry


MAX_TOOL_RESULT_BYTES = 65_536


class ToolCallingError(RuntimeError):
    """Signale une réponse modèle ou un appel d'outil impossible à valider sûrement."""


class ToolCallingUnavailableError(ToolCallingError):
    """Distingue une indisponibilité HTTP locale d'une réponse mal formée."""


class ToolAuthorizationError(ToolCallingError):
    """Signale une tentative d'outil qui n'appartient pas au profil actif."""


class ToolArgumentsError(ToolCallingError):
    """Signale des arguments corrigeables qui ne respectent pas le schéma annoncé."""


@dataclass(frozen=True)
class ParsedToolCall:
    """Conserve un unique appel déjà borné à un nom déclaré et un objet JSON."""

    call_id: str
    name: str
    arguments: dict[str, Any]
    assistant_message: dict[str, Any]


@dataclass(frozen=True)
class AssistantTurn:
    """Représente soit une réponse finale, soit exactement un appel structuré."""

    content: str | None
    tool_call: ParsedToolCall | None
    finish_reason: str | None


class ToolCallingGateway(Protocol):
    """Contrat minimal utilisé par la future boucle agentique et les doubles de test."""

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AssistantTurn: ...


def _strict_json_object(raw_arguments: object) -> dict[str, Any]:
    """Parse du JSON sans constante exotique ni clé dupliquée, jamais avec eval."""

    if not isinstance(raw_arguments, str) or len(raw_arguments.encode("utf-8")) > 65_536:
        raise ToolCallingError("Les arguments de l'outil sont absents ou trop grands.")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        """Refuse une ambiguïté JSON qu'un parseur permissif écraserait silencieusement."""

        parsed: dict[str, Any] = {}
        for key, value in pairs:
            if key in parsed:
                raise ToolCallingError("Les arguments JSON contiennent une clé dupliquée.")
            parsed[key] = value
        return parsed

    def reject_constant(value: str) -> None:
        """Interdit NaN et les infinis non conformes au JSON standard."""

        raise ToolCallingError(f"Constante JSON interdite : {value}.")

    try:
        decoded = json.loads(
            raw_arguments,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except ToolCallingError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ToolCallingError("Les arguments de l'outil ne sont pas un JSON valide.") from error
    if not isinstance(decoded, dict):
        raise ToolCallingError("Les arguments de l'outil doivent former un objet JSON.")
    return decoded


def parse_assistant_turn(
    payload: object,
    allowed_tool_names: set[str],
) -> AssistantTurn:
    """Valide la forme OpenAI native et interdit texte mêlé ou appels parallèles."""

    try:
        choice = payload["choices"][0]  # type: ignore[index]
        message = choice["message"]
        finish_reason = choice.get("finish_reason")
    except (IndexError, KeyError, TypeError, AttributeError) as error:
        raise ToolCallingError("La réponse tool calling du modèle est invalide.") from error
    if not isinstance(message, dict) or not isinstance(message.get("role", "assistant"), str):
        raise ToolCallingError("Le message assistant du modèle est invalide.")
    content = message.get("content")
    if content is not None and not isinstance(content, str):
        raise ToolCallingError("Le contenu assistant n'est pas textuel.")
    tool_calls = message.get("tool_calls")
    if tool_calls in (None, []):
        if not isinstance(content, str) or not content.strip():
            raise ToolCallingError("Le modèle n'a produit ni réponse finale ni appel d'outil.")
        return AssistantTurn(content=content.strip(), tool_call=None, finish_reason=finish_reason)
    if not isinstance(tool_calls, list) or len(tool_calls) != 1:
        raise ToolCallingError("Un seul appel d'outil à la fois est autorisé.")
    if isinstance(content, str) and content.strip():
        raise ToolCallingError("Un appel d'outil ne peut pas être mélangé à du texte libre.")

    raw_call = tool_calls[0]
    try:
        call_id = raw_call["id"]
        call_type = raw_call["type"]
        function = raw_call["function"]
        name = function["name"]
        raw_arguments = function["arguments"]
    except (KeyError, TypeError) as error:
        raise ToolCallingError("La structure de l'appel d'outil est invalide.") from error
    if (
        not isinstance(call_id, str)
        or not call_id
        or len(call_id) > 200
        or call_type != "function"
        or not isinstance(name, str)
        or name not in allowed_tool_names
    ):
        raise ToolAuthorizationError("Le modèle a demandé un outil non déclaré ou un identifiant invalide.")
    arguments = _strict_json_object(raw_arguments)
    canonical_message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
                },
            }
        ],
    }
    return AssistantTurn(
        content=None,
        tool_call=ParsedToolCall(call_id, name, arguments, canonical_message),
        finish_reason=finish_reason if isinstance(finish_reason, str) else None,
    )


def tool_result_message(call_id: str, result: dict[str, Any]) -> dict[str, str]:
    """Sérialise un résultat comme donnée bornée liée à l'identifiant exact de l'appel."""

    if not isinstance(call_id, str) or not call_id or len(call_id) > 200:
        raise ToolCallingError("L'identifiant du résultat d'outil est invalide.")
    serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > MAX_TOOL_RESULT_BYTES:
        raise ToolCallingError("Le résultat d'outil dépasse la limite autorisée.")
    return {"role": "tool", "tool_call_id": call_id, "content": serialized}


class HttpToolCallingGateway:
    """Appelle l'API OpenAI locale de llama.cpp avec le template natif Jinja."""

    def __init__(
        self,
        registry: LoadedModelRegistry,
        profile_id: str,
        *,
        timeout_seconds: float = 180.0,
    ) -> None:
        """Fige profil, alias et URL depuis le registre déjà validé."""

        self.registry = registry
        self.profile = registry.profile(profile_id)
        runtime = registry.document.runtime
        self.url = f"http://{runtime.host}:{runtime.port}{runtime.chat_completions_path}"
        self.timeout_seconds = timeout_seconds

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AssistantTurn:
        """Demande auto, désactive le parallélisme et parse uniquement la forme native."""

        allowed_names = {
            tool["function"]["name"]
            for tool in tools
            if isinstance(tool, dict)
            and isinstance(tool.get("function"), dict)
            and isinstance(tool["function"].get("name"), str)
        }
        if not allowed_names:
            raise ToolCallingError("Aucun outil structuré n'est fourni au modèle.")
        payload = {
            "model": self.profile.runtime.alias,
            "messages": messages,
            "stream": False,
            "max_tokens": self.profile.generation.max_tokens,
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.url, json=payload)
                response.raise_for_status()
        except httpx.RequestError as error:
            raise ToolCallingUnavailableError("Le modèle de programmation local est indisponible.") from error
        except httpx.HTTPStatusError as error:
            raise ToolCallingError("Le modèle local a refusé la requête tool calling.") from error
        try:
            document = response.json()
        except ValueError as error:
            raise ToolCallingError("Le modèle a renvoyé un document non JSON.") from error
        return parse_assistant_turn(document, allowed_names)


class ToolDispatcher:
    """Expose l'union exacte des outils autorisés par le profil actif."""

    def __init__(
        self,
        file_tools: FileToolExecutor,
        development_tools: DevelopmentToolExecutor,
    ) -> None:
        """Conserve les deux exécuteurs locaux; aucun handler n'est résolu par réflexion."""

        self.file_tools = file_tools
        self.development_tools = development_tools
        all_schemas = (*file_tools.schemas(), *development_tools.schemas())
        self._schemas = {
            schema["function"]["name"]: schema
            for schema in all_schemas
        }

    def schemas(self, allowed_tools: list[str]) -> list[dict[str, Any]]:
        """Retourne dans l'ordre du registre les schémas réellement implémentés."""

        missing = [name for name in allowed_tools if name not in self._schemas]
        if missing:
            raise ToolCallingError(f"Outils configurés mais non implémentés : {', '.join(missing)}")
        return [self._schemas[name] for name in allowed_tools]

    def supports(self, name: str) -> bool:
        """Indique si un nom du registre possède déjà un exécuteur concret."""

        return name in self._schemas

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        allowed_tools: list[str],
        run_id: str,
    ) -> dict[str, Any]:
        """Valide à nouveau nom et arguments avant d'appeler une branche fixe."""

        if name not in allowed_tools or name not in self._schemas:
            raise ToolAuthorizationError("L'outil demandé n'est pas autorisé pour ce profil.")
        try:
            if name in TOOL_ARGUMENT_MODELS:
                return await asyncio.to_thread(
                    self.file_tools.execute,
                    name,
                    arguments,
                    run_id=run_id,
                )
            if name in DEVELOPMENT_ARGUMENT_MODELS:
                return await self.development_tools.execute(
                    name,
                    arguments,
                    run_id=run_id,
                )
        except ValidationError as error:
            raise ToolArgumentsError("Les arguments de l'outil ne respectent pas son schéma.") from error
        raise ToolCallingError("L'outil demandé n'a aucun exécuteur local.")
