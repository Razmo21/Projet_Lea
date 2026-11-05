"""Conversations temporaires bornées, sans base, fichier ni contenu journalisé."""

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from .web_gateway import WebAuthorizationManager


class EphemeralSession:
    """Un historique en RAM, lié à un profil et effacé après trente minutes d'inactivité."""

    def __init__(self, profile_id: str) -> None:
        """Ne conserve que des données locales nécessaires au tour suivant."""
        self.id = str(uuid4())
        self.profile_id = profile_id
        self.messages: list[dict] = []
        self.revision = 0
        self.task: asyncio.Task | None = None
        self.expiry: asyncio.TimerHandle | None = None

    def append(self, question: str, answer: str, sources: list[dict] | None = None) -> dict:
        """Ajoute une paire complète et borne l'historique à 100 messages et 256 Kio."""
        stamp = datetime.now(timezone.utc).isoformat()
        for role, content in (("user", question), ("assistant", answer)):
            self.messages.append(dict(
                id=str(uuid4()), conversation_id=self.id, position=len(self.messages),
                role=role, content=content, status="completed", kind="conversation",
                model_id=None, profile_id=self.profile_id,
                web_sources=(sources or []) if role == "assistant" else [], error=None,
                created_at=stamp, updated_at=stamp,
            ))
        while len(self.messages) > 2 and (
            len(self.messages) > 100
            or len(json.dumps(self.messages, ensure_ascii=False).encode("utf-8")) > 256 * 1024
        ):
            del self.messages[:2]
        self.revision += 1
        return self.detail()

    def detail(self) -> dict:
        """Partage le format de présentation, sans créer une conversation persistante."""
        return dict(
            id=self.id, title="Chat éphémère", title_origin="automatic",
            created_at="", updated_at="", revision=self.revision,
            generation_active=self.task is not None, message_count=len(self.messages),
            messages=[item.copy() for item in self.messages],
        )


class EphemeralSessions:
    """Chaque instance backend possède ses jetons ; un ancien jeton ne recrée rien."""

    def __init__(self) -> None:
        """Initialise un registre vide, sans boucle de surveillance permanente."""
        self.instance_id = str(uuid4())
        self.sessions: dict[str, EphemeralSession] = {}
        self.authorization = WebAuthorizationManager()

    def create(self, profile_id: str) -> EphemeralSession:
        """Refuse une neuvième session plutôt que conserver une quantité illimitée de texte."""
        if len(self.sessions) >= 8:
            raise HTTPException(429, "Ferme un chat éphémère avant d’en ouvrir un autre.")
        session = EphemeralSession(profile_id)
        self.sessions[session.id] = session
        self.touch(session)
        return session

    def get(self, identity: str) -> EphemeralSession:
        """Refuse une session expirée, fermée ou créée avant le redémarrage."""
        session = self.sessions.get(identity)
        if session is None:
            raise HTTPException(410, "Le chat éphémère a été effacé. Ouvre une nouvelle session.")
        return session

    def touch(self, session: EphemeralSession) -> None:
        """Renouvelle un délai unique, annulé à la fermeture de la session."""
        if session.expiry:
            session.expiry.cancel()
        session.expiry = asyncio.get_running_loop().call_later(1800, self.discard, session.id)

    def discard(self, identity: str) -> None:
        """Efface les références au texte et annule une éventuelle génération en cours."""
        session = self.sessions.pop(identity, None)
        self.authorization.discard_pending(identity)
        if session:
            if session.expiry:
                session.expiry.cancel()
            if session.task:
                session.task.cancel()
            session.messages.clear()

    def clear(self) -> None:
        """Libère tous les délais et textes lors de l'arrêt de FastAPI."""
        for identity in list(self.sessions):
            self.discard(identity)
