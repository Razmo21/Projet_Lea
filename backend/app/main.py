from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MODEL_SERVER_URL = "http://127.0.0.1:8080/v1/chat/completions"
MODEL_UNAVAILABLE_MESSAGE = "Le modèle local de Léa n’est pas disponible."
CONTEXT_WINDOW_TOKEN_LIMIT = 4096
FINAL_RESPONSE_TOKEN_LIMIT = 1024
REASONING_TOKEN_RESERVE = 512
SYSTEM_AND_TEMPLATE_TOKEN_RESERVE = 512
CONTEXT_INPUT_TOKEN_BUDGET = (
    CONTEXT_WINDOW_TOKEN_LIMIT
    - FINAL_RESPONSE_TOKEN_LIMIT
    - REASONING_TOKEN_RESERVE
    - SYSTEM_AND_TEMPLATE_TOKEN_RESERVE
)
# Aucun tokenizer llama.cpp n'est exposé de manière fiable au backend. Un
# octet UTF-8 par token est une borne haute prudente : certains contenus rares
# coûtent presque un token par octet avec les tokenizers BPE.
UTF8_BYTES_PER_ESTIMATED_TOKEN = 1
MESSAGE_TOKEN_OVERHEAD = 8
# La question maximale (2 000 octets + 8 tokens de structure) tient toujours
# dans les 2 048 tokens réservés à l'entrée, même dans le pire cas ci-dessus.
MAX_QUESTION_BYTES = 2000
# Une réponse finale peut être plus longue que la fenêtre d'entrée suivante.
# Elle reste affichée, mais le frontend n'envoie alors pas sa paire en contexte.
MAX_HISTORY_MESSAGE_BYTES = 8192
MAX_HISTORY_MESSAGES = 24
SYSTEM_MESSAGE = (
    "Tu es Léa, un assistant généraliste local. Réponds dans la langue de "
    "l’utilisateur, de façon claire, utile et directe."
)
THINKING_DELIMITERS = ("<think>", "</think>", "[Start thinking]", "[End thinking]")


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


def contains_thinking_delimiter(content: str) -> bool:
    return any(delimiter in content for delimiter in THINKING_DELIMITERS)


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    role: Literal["user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, content: str) -> str:
        return normalize_text(
            content,
            max_bytes=MAX_HISTORY_MESSAGE_BYTES,
            field_name="Le contenu d’un message d’historique",
        )

    @model_validator(mode="after")
    def reject_hidden_reasoning(self) -> "ConversationMessage":
        if self.role == "assistant" and contains_thinking_delimiter(self.content):
            raise ValueError("Un message assistant ne peut pas contenir de raisonnement interne.")
        return self


class ChatRequest(BaseModel):
    # Le contrat historique {"question": "..."} reste valide : history est
    # optionnel et le backend ne conserve aucune conversation entre requêtes.
    model_config = ConfigDict(extra="forbid", strict=True)

    question: str
    history: list[ConversationMessage] = Field(
        default_factory=list,
        max_length=MAX_HISTORY_MESSAGES,
    )

    @field_validator("question")
    @classmethod
    def validate_question(cls, question: str) -> str:
        return normalize_text(
            question,
            max_bytes=MAX_QUESTION_BYTES,
            field_name="La question",
        )

    @model_validator(mode="after")
    def validate_history_pairs(self) -> "ChatRequest":
        if len(self.history) > MAX_HISTORY_MESSAGES:
            raise ValueError(
                f"L’historique ne peut pas dépasser {MAX_HISTORY_MESSAGES} messages."
            )
        if len(self.history) % 2:
            raise ValueError("L’historique doit contenir des paires user/assistant complètes.")

        for index, message in enumerate(self.history):
            expected_role = "user" if index % 2 == 0 else "assistant"
            if message.role != expected_role:
                raise ValueError("L’historique doit alterner user puis assistant.")

        return self


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def estimate_message_tokens(message: ConversationMessage) -> int:
    return (
        len(message.content.encode("utf-8")) // UTF8_BYTES_PER_ESTIMATED_TOKEN
        + MESSAGE_TOKEN_OVERHEAD
    )


def trim_history_for_context(
    history: list[ConversationMessage], question: str
) -> list[ConversationMessage]:
    """Keep the newest complete pairs that fit beside the current question."""
    current_message = ConversationMessage(role="user", content=question)
    remaining_budget = CONTEXT_INPUT_TOKEN_BUDGET - estimate_message_tokens(current_message)
    retained: list[ConversationMessage] = []

    # ChatRequest has already ensured complete alternating pairs. We walk from
    # the newest pair backwards and stop at the first pair that no longer fits,
    # so an older, smaller pair can never displace a more recent exchange.
    for index in range(len(history) - 2, -1, -2):
        pair = history[index : index + 2]
        pair_cost = sum(estimate_message_tokens(message) for message in pair)
        if pair_cost > remaining_budget:
            break
        retained = pair + retained
        remaining_budget -= pair_cost

    return retained


def build_model_messages(request: ChatRequest) -> list[dict[str, str]]:
    history = trim_history_for_context(request.history, request.question)
    return [
        {"role": "system", "content": SYSTEM_MESSAGE},
        *[message.model_dump() for message in history],
        {"role": "user", "content": request.question},
    ]


def build_model_payload(request: ChatRequest) -> dict[str, object]:
    return {
        "model": "lea-general",
        "messages": build_model_messages(request),
        "stream": False,
        # Le budget de raisonnement du serveur est distinct (512 tokens).
        # Cette limite laisse donc aussi de la place à la réponse finale.
        "max_tokens": FINAL_RESPONSE_TOKEN_LIMIT,
    }


def remove_thinking(content: str) -> str:
    # Le template local peut placer la pensée interne entre ces balises dans
    # message.content. Ce filtre conserve uniquement la réponse finale.
    for opening, closing in (("<think>", "</think>"), ("[Start thinking]", "[End thinking]")):
        while opening in content:
            before, _, after_opening = content.partition(opening)
            _, found_closing, after = after_opening.partition(closing)
            content = before + after if found_closing else before

    return content.strip()


@app.post("/chat")
async def chat(request: ChatRequest) -> dict[str, str]:
    payload = build_model_payload(request)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(MODEL_SERVER_URL, json=payload)
            response.raise_for_status()
    except httpx.RequestError as error:
        raise HTTPException(status_code=503, detail=MODEL_UNAVAILABLE_MESSAGE) from error
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=502,
            detail="Le modèle local de Léa a renvoyé une erreur.",
        ) from error

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail="Le modèle local de Léa n’a pas fourni de réponse exploitable.",
        ) from error

    answer = remove_thinking(content) if isinstance(content, str) else ""
    if not answer:
        raise HTTPException(
            status_code=502,
            detail="Le modèle local de Léa n’a pas fourni de réponse exploitable.",
        )

    return {"answer": answer}
