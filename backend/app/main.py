from fastapi import FastAPI
from pydantic import BaseModel


class TestResponseRequest(BaseModel):
    question: str


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/test-response")
def test_response(request: TestResponseRequest) -> dict[str, str]:
    return {"answer": "Léa n'est pas encore connectée à son modèle."}
