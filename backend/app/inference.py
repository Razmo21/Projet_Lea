"""Frontière avec le moteur local : commande, endpoints et protocole d’inférence.

Les propriétaires de processus conservent les PID et leur cycle de vie. Cet
adaptateur ne charge aucun modèle et ne décide jamais des permissions du profil.
"""

from __future__ import annotations

import subprocess
from typing import Any

import httpx

from .model_registry import LoadedModelRegistry, RegistryError


MODEL_UNAVAILABLE_MESSAGE = "Le modèle local de Léa n’est pas disponible."
MODEL_INVALID_RESPONSE_MESSAGE = "Le modèle local de Léa n’a pas fourni de réponse exploitable."


class ModelUnavailableError(RuntimeError):
    """Signale un moteur injoignable sans exposer son diagnostic réseau."""


class ModelResponseError(RuntimeError):
    """Signale une réponse d’inférence mal formée ou refusée par le moteur."""


def llama_cpp_arguments(configuration: dict[str, Any]) -> list[str]:
    """Construit une liste sans shell à partir des paramètres déjà validés."""

    runtime = configuration["runtime"]
    arguments = [
        "-m", str(configuration["model_path"]),
        "--host", configuration["host"],
        "--port", str(configuration["port"]),
        "--alias", configuration["alias"],
        "--ctx-size", str(configuration["context"]),
        "--parallel", str(runtime["parallel_slots"]),
        "--cache-type-k", runtime["cache_type_k"],
        "--cache-type-v", runtime["cache_type_v"],
        "--cache-ram", "1" if runtime["cache_ram"] else "0",
        "--gpu-layers", str(runtime["gpu_layers"]),
        "--fit", "on" if runtime["fit"] else "off",
        "--fit-target", str(runtime["fit_target_mib"]),
        "--fit-ctx", str(runtime["fit_context_min_tokens"]),
        "--prio", str(runtime["priority"]),
        "--threads", str(runtime["threads"]),
        "--batch-size", str(runtime["batch_size"]),
        "--ubatch-size", str(runtime["ubatch_size"]),
        "--mmap" if runtime["mmap"] else "--no-mmap",
    ]
    if runtime["jinja"]:
        arguments.append("--jinja")
    if configuration["template"] is not None:
        # Le moteur doit activer Jinja avant de recevoir un template personnalisé.
        arguments.extend(("--chat-template-file", str(configuration["template"])))
    arguments.append(
        "--skip-chat-parsing" if runtime["skip_chat_parsing"] else "--no-skip-chat-parsing"
    )
    return arguments


class LlamaCppAdapter:
    """Adapte le seul moteur actuellement pris en charge, sans dépendance à Qwen."""

    def __init__(self, registry: LoadedModelRegistry, profile_id: str) -> None:
        """Fige le modèle résolu et l’endpoint local propre au mode du profil."""

        self.registry = registry
        self.profile = registry.profile(profile_id)
        self.endpoint = (
            registry.document.openhands.model_endpoint
            if self.profile.agent_engine == "OpenHands" else registry.document.runtime
        )

    @property
    def chat_url(self) -> str:
        """Adresse locale utilisée par les conversations directes."""

        return f"http://{self.endpoint.host}:{self.endpoint.port}{self.endpoint.chat_completions_path}"

    @property
    def models_url(self) -> str:
        """Adresse de readiness : la liste doit annoncer l’alias configuré."""

        return f"http://{self.endpoint.host}:{self.endpoint.port}{self.endpoint.models_path}"

    @property
    def sdk_base_url(self) -> str:
        """Expose le même serveur au SDK exécuté dans le conteneur Docker Desktop."""

        suffix = "/chat/completions"
        path = self.endpoint.chat_completions_path
        if not path.endswith(suffix):
            raise RegistryError("Le SDK exige une route de type /v1/chat/completions.")
        prefix = path[:-len(suffix)]
        return f"http://host.docker.internal:{self.endpoint.port}{prefix}"

    def launch_configuration(self, *, verify_model: bool = False) -> dict[str, Any]:
        """Résout les fichiers locaux ; le hash GGUF n’est calculé qu’avant lancement."""

        profile_id = self.profile.id
        return {
            "root": self.registry.project_root,
            "executable": self.registry.runtime_executable(),
            "model_path": (
                self.registry.verify_model_integrity(profile_id)
                if verify_model else self.registry.model_path(profile_id)
            ),
            "template": self.registry.model_template(profile_id),
            "host": self.endpoint.host,
            "port": self.endpoint.port,
            "models_path": self.endpoint.models_path,
            "alias": self.profile.runtime.alias,
            "context": self.profile.context_tokens,
            "runtime": self.profile.runtime.model_dump(),
        }

    def launch_command(self) -> dict[str, Any]:
        """Fournit les arguments aux propriétaires Windows, sans exécuter de shell."""

        configuration = self.launch_configuration()
        arguments = llama_cpp_arguments(configuration)
        return {
            "executable": str(configuration["executable"]),
            "arguments": arguments,
            # Start-Process attend une chaîne Windows correctement échappée.
            "windows_arguments": subprocess.list2cmdline(arguments),
        }

    def sdk_extra_body(self) -> dict[str, Any]:
        """Sépare les contraintes d’outils des séquences d’arrêt propres au modèle."""

        body: dict[str, Any] = {"tool_choice": "auto", "parallel_tool_calls": False}
        if self.profile.model.stop_sequences:
            body["stop"] = list(self.profile.model.stop_sequences)
        return body

    async def is_ready(self, *, transport: httpx.AsyncBaseTransport | None = None) -> bool:
        """Confirme l’alias réellement servi ; une réponse mal formée n’est pas prête."""

        try:
            async with httpx.AsyncClient(timeout=2.0, transport=transport) as client:
                response = await client.get(self.models_url)
                response.raise_for_status()
            entries = response.json()["data"]
            return isinstance(entries, list) and any(
                isinstance(entry, dict) and entry.get("id") == self.profile.runtime.alias
                for entry in entries
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return False

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> str:
        """Échange au format OpenAI local ; la publication et son filtrage restent à Léa."""

        payload: dict[str, Any] = {
            "model": self.profile.runtime.alias,
            "messages": messages,
            "stream": False,
            "max_tokens": self.profile.generation.max_tokens,
        }
        if self.profile.model.stop_sequences:
            payload["stop"] = list(self.profile.model.stop_sequences)
        try:
            async with httpx.AsyncClient(timeout=120.0, transport=transport) as client:
                response = await client.post(self.chat_url, json=payload)
                response.raise_for_status()
        except httpx.RequestError as error:
            raise ModelUnavailableError(MODEL_UNAVAILABLE_MESSAGE) from error
        except httpx.HTTPStatusError as error:
            raise ModelResponseError("Le modèle local de Léa a renvoyé une erreur.") from error
        try:
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("Réponse non textuelle.")
            return content
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise ModelResponseError(MODEL_INVALID_RESPONSE_MESSAGE) from error


def inference_adapter(registry: LoadedModelRegistry, profile_id: str) -> LlamaCppAdapter:
    """Résout explicitement le moteur ; aucune substitution silencieuse n’est permise."""

    engine = registry.profile(profile_id).model.engine
    if engine != "llama.cpp":
        raise RegistryError(f"Moteur d’inférence non pris en charge : {engine}")
    return LlamaCppAdapter(registry, profile_id)
