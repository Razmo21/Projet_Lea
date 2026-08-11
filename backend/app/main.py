import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


MODEL_SERVER_URL = "http://127.0.0.1:8080/v1/chat/completions"
MODEL_UNAVAILABLE_MESSAGE = "Le modèle local de Léa n’est pas disponible."
SYSTEM_MESSAGE = (
    "Tu es Léa, un assistant généraliste local. Réponds dans la langue de "
    "l’utilisateur, de façon claire, utile et directe."
)


class ChatRequest(BaseModel):
    question: str


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


def remove_thinking(content: str) -> str:
    for opening, closing in (("<think>", "</think>"), ("[Start thinking]", "[End thinking]")):
        while opening in content:
            before, _, after_opening = content.partition(opening)
            _, found_closing, after = after_opening.partition(closing)
            content = before + after if found_closing else before

    return content.strip()


@app.post("/chat")
async def chat(request: ChatRequest) -> dict[str, str]:
    payload = {
        "model": "lea-general",
        "messages": [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": f"{request.question}\n/no_think"},
        ],
        "stream": False,
        "max_tokens": 512,
    }

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
