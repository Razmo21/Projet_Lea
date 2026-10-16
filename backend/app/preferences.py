"""Préférences fonctionnelles de Léa, sans propriété des modèles ou processus."""

from __future__ import annotations

import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .database import Database


ReasoningLevel = Literal["low", "high"]


class PreferencesError(RuntimeError):
    """Erreur publique de stockage, sans chemin ni contenu privé."""


class PreferencesConflict(PreferencesError):
    """Un autre onglet a déjà enregistré une nouvelle révision."""


class Preferences(BaseModel):
    """Snapshot validé ; le choix absent à la création est toujours Low."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    revision: int = Field(default=0, ge=0)
    general_reasoning: ReasoningLevel = "low"


class PreferenceChange(BaseModel):
    """Liste fermée des valeurs modifiables, sans chemin, commande ou modèle."""

    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: int = Field(ge=0)
    general_reasoning: ReasoningLevel


class PreferencesStore:
    """Réutilise les transactions SQLite existantes, sans mémoire globale mutable."""

    def __init__(self, database: Database) -> None:
        """Réutilise la base choisie par l'application, jamais par le navigateur."""

        self.database = database

    @staticmethod
    def _read(connection: sqlite3.Connection) -> Preferences:
        """Refuse une préférence persistée invalide au lieu de l'écraser par défaut."""

        row = connection.execute(
            "SELECT revision, general_reasoning FROM user_preferences WHERE id = 1"
        ).fetchone()
        if row is None:
            raise PreferencesError("Les préférences enregistrées sont absentes ou invalides.")
        try:
            return Preferences.model_validate(dict(row))
        except ValidationError as error:
            raise PreferencesError("Les préférences enregistrées sont invalides.") from error

    def read(self) -> Preferences:
        """Relit le dernier choix validé, également lorsqu'aucun modèle n'est chargé."""

        try:
            with self.database.connection() as connection:
                return self._read(connection)
        except sqlite3.Error as error:
            raise PreferencesError("Impossible de lire les préférences locales.") from error

    def save(self, change: PreferenceChange) -> Preferences:
        """Valide la révision et relit l'écriture dans la même transaction atomique."""

        try:
            with self.database.transaction() as connection:
                current = self._read(connection)
                if current.revision != change.expected_revision:
                    raise PreferencesConflict(
                        "Les paramètres ont changé dans un autre onglet. Rechargez-les avant de valider."
                    )
                connection.execute(
                    "UPDATE user_preferences SET general_reasoning = ?, revision = revision + 1 WHERE id = 1",
                    (change.general_reasoning,),
                )
                saved = self._read(connection)
            # Le commit a réussi avant que l'appelant puisse annoncer l'enregistrement.
            return saved
        except sqlite3.Error as error:
            raise PreferencesError(
                "Enregistrement impossible. Le dernier réglage valide est conservé."
            ) from error
