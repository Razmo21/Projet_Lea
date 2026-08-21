"""Confinement des projets locaux sous l'unique racine IA_WORKSPACE."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath


FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class WorkspacePathError(ValueError):
    """Signale un chemin absent, ambigu ou extérieur à l'espace autorisé."""


@dataclass(frozen=True)
class ValidatedWorkspacePath:
    """Conserve le chemin canonique et son identité pour une revalidation tardive."""

    path: Path
    relative_path: str
    identity: tuple[int, int]


@dataclass(frozen=True)
class DiscoveredProject:
    """Décrit seulement les métadonnées relatives persistables d'un projet."""

    name: str
    relative_path: str


class WorkspaceGuard:
    """Résout les chemins sans suivre de lien, junction ni reparse point accepté."""

    def __init__(self, root: str | Path) -> None:
        """Fige une racine réelle qui n'est elle-même pas un reparse point."""

        configured = Path(root)
        if not configured.is_absolute():
            raise WorkspacePathError("La racine IA_WORKSPACE doit être absolue.")
        self.root = configured.resolve(strict=True)
        if not self.root.is_dir():
            raise WorkspacePathError("La racine IA_WORKSPACE n'est pas un dossier.")
        self._reject_reparse(self.root)

    @staticmethod
    def _reject_reparse(path: Path) -> None:
        """Refuse les liens symboliques et reparse points Windows sans les suivre."""

        try:
            metadata = path.stat(follow_symlinks=False)
        except OSError as error:
            raise WorkspacePathError(f"Chemin local inaccessible : {path.name}") from error
        attributes = int(getattr(metadata, "st_file_attributes", 0))
        if path.is_symlink() or attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise WorkspacePathError(f"Les liens et reparse points sont interdits : {path.name}")

    @staticmethod
    def _parts(relative_path: str, *, single_component: bool) -> tuple[str, ...]:
        """Valide une syntaxe Windows strictement relative et normalise ses séparateurs."""

        if not isinstance(relative_path, str) or not relative_path.strip() or "\x00" in relative_path:
            raise WorkspacePathError("Le chemin relatif est vide ou invalide.")
        windows_path = PureWindowsPath(relative_path)
        if (
            windows_path.is_absolute()
            or windows_path.drive
            or windows_path.root
            or relative_path.startswith(("\\", "/"))
        ):
            raise WorkspacePathError("Un chemin absolu, UNC ou avec lecteur est interdit.")
        parts = tuple(windows_path.parts)
        if any(part in {"", ".", ".."} for part in parts):
            raise WorkspacePathError("La remontée de dossier est interdite.")
        if single_component and len(parts) != 1:
            raise WorkspacePathError("Un projet doit être un sous-dossier direct de IA_WORKSPACE.")
        return parts

    def _assert_contained(self, path: Path) -> None:
        """Compare les chemins canoniques avec la sémantique insensible à la casse Windows."""

        try:
            common = os.path.commonpath((os.path.normcase(self.root), os.path.normcase(path)))
        except ValueError as error:
            raise WorkspacePathError("Le chemin utilise un autre lecteur.") from error
        if os.path.normcase(common) != os.path.normcase(str(self.root)):
            raise WorkspacePathError("Le chemin sort de IA_WORKSPACE.")

    def _assert_chain(self, lexical_path: Path) -> None:
        """Vérifie chaque composant existant avant toute résolution canonique."""

        try:
            relative = lexical_path.relative_to(self.root)
        except ValueError as error:
            raise WorkspacePathError("Le chemin sort de IA_WORKSPACE.") from error
        cursor = self.root
        for part in relative.parts:
            cursor = cursor / part
            self._reject_reparse(cursor)

    def resolve_project(self, relative_path: str) -> ValidatedWorkspacePath:
        """Résout un sous-dossier de projet réel et retourne une identité revalidable."""

        parts = self._parts(relative_path, single_component=True)
        lexical_path = self.root.joinpath(*parts)
        self._assert_chain(lexical_path)
        try:
            resolved = lexical_path.resolve(strict=True)
            metadata = resolved.stat()
        except OSError as error:
            raise WorkspacePathError("Le projet demandé n'existe pas.") from error
        self._assert_contained(resolved)
        if not resolved.is_dir():
            raise WorkspacePathError("Le projet demandé n'est pas un dossier.")
        return ValidatedWorkspacePath(
            path=resolved,
            relative_path=resolved.relative_to(self.root).as_posix(),
            identity=(int(metadata.st_dev), int(metadata.st_ino)),
        )

    def revalidate_project(self, project: ValidatedWorkspacePath) -> ValidatedWorkspacePath:
        """Détecte un échange TOCTOU du dossier entre validation et opération."""

        current = self.resolve_project(project.relative_path)
        if current.path != project.path or current.identity != project.identity:
            raise WorkspacePathError("Le projet a changé depuis sa validation ; opération refusée.")
        return current

    def discover_projects(self) -> list[DiscoveredProject]:
        """Liste les sous-dossiers directs réels en excluant tout reparse point."""

        discovered: list[DiscoveredProject] = []
        try:
            entries = list(self.root.iterdir())
        except OSError as error:
            raise WorkspacePathError("Impossible d'actualiser IA_WORKSPACE.") from error
        for entry in sorted(entries, key=lambda item: (item.name.casefold(), item.name)):
            try:
                project = self.resolve_project(entry.name)
            except WorkspacePathError:
                continue
            discovered.append(
                DiscoveredProject(name=entry.name, relative_path=project.relative_path)
            )
        return discovered

    def resolve_member(
        self,
        project: ValidatedWorkspacePath,
        relative_path: str,
    ) -> ValidatedWorkspacePath:
        """Résout un membre existant sans pouvoir sortir du projet revalidé."""

        current_project = self.revalidate_project(project)
        if relative_path in {"", "."}:
            return ValidatedWorkspacePath(
                path=current_project.path,
                relative_path=".",
                identity=current_project.identity,
            )
        parts = self._parts(relative_path, single_component=False)
        lexical_path = current_project.path.joinpath(*parts)
        try:
            lexical_path.relative_to(current_project.path)
        except ValueError as error:
            raise WorkspacePathError("Le chemin sort du projet actif.") from error
        self._assert_chain(lexical_path)
        try:
            resolved = lexical_path.resolve(strict=True)
            metadata = resolved.stat()
            resolved.relative_to(current_project.path)
        except (OSError, ValueError) as error:
            raise WorkspacePathError("Le chemin demandé n'existe pas dans le projet.") from error
        self._assert_contained(resolved)
        return ValidatedWorkspacePath(
            path=resolved,
            relative_path=resolved.relative_to(current_project.path).as_posix(),
            identity=(int(metadata.st_dev), int(metadata.st_ino)),
        )

    def resolve_destination(
        self,
        project: ValidatedWorkspacePath,
        relative_path: str,
    ) -> tuple[Path, ValidatedWorkspacePath]:
        """Valide une cible inexistante et retourne son parent revalidable."""

        parts = self._parts(relative_path, single_component=False)
        if not parts:
            raise WorkspacePathError("La destination est vide.")
        parent_relative = str(PureWindowsPath(*parts[:-1])) if len(parts) > 1 else "."
        parent = self.resolve_member(project, parent_relative)
        if not parent.path.is_dir():
            raise WorkspacePathError("Le parent de destination n'est pas un dossier.")
        destination = parent.path / parts[-1]
        if destination.exists() or destination.is_symlink():
            raise WorkspacePathError("La destination existe déjà.")
        return destination, parent

    def revalidate_member(
        self,
        project: ValidatedWorkspacePath,
        member: ValidatedWorkspacePath,
    ) -> ValidatedWorkspacePath:
        """Détecte le remplacement extérieur d'un fichier ou dossier déjà validé."""

        current = self.resolve_member(project, member.relative_path)
        if current.path != member.path or current.identity != member.identity:
            raise WorkspacePathError("Le chemin a changé depuis sa validation ; opération refusée.")
        return current
