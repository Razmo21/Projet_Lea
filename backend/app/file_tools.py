"""Outils de fichiers structurés, bornés et confinés au projet actif."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .database import Database, ProjectNotFoundError
from .workspace import ValidatedWorkspacePath, WorkspaceGuard, WorkspacePathError


MAX_TEXT_FILE_BYTES = 1_048_576
MAX_LIST_LIMIT = 200
MAX_SEARCH_LIMIT = 100
MAX_RANGE_LINES = 500
DEFAULT_IGNORED_NAMES = {
    ".git",
    ".venv",
    "bin",
    "build",
    "cache",
    "caches",
    "dist",
    "models",
    "node_modules",
    "obj",
    "venv",
}
DEFAULT_IGNORED_SUFFIXES = {".gguf", ".safetensors"}


class FileToolError(RuntimeError):
    """Retourne une erreur d'outil sûre sans chemin absolu ni traceback."""


class StrictToolArguments(BaseModel):
    """Refuse tout argument implicite ou inconnu fourni par le modèle."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ListFilesArguments(StrictToolArguments):
    """Arguments paginés de l'inventaire d'un sous-dossier."""

    path: str = "."
    recursive: bool = True
    cursor: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=MAX_LIST_LIMIT)


class SearchFilesArguments(StrictToolArguments):
    """Arguments d'une recherche textuelle bornée et non binaire."""

    query: str = Field(min_length=1, max_length=500)
    path: str = "."
    case_sensitive: bool = False
    cursor: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=MAX_SEARCH_LIMIT)


class ReadFileArguments(StrictToolArguments):
    """Arguments d'une lecture complète sous la limite de taille."""

    path: str


class ReadFileRangeArguments(ReadFileArguments):
    """Arguments d'une lecture inclusive par numéros de lignes."""

    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class CreateFileArguments(StrictToolArguments):
    """Arguments d'une création UTF-8 qui refuse toute destination existante."""

    path: str
    content: str = Field(max_length=MAX_TEXT_FILE_BYTES)


class ApplyPatchArguments(StrictToolArguments):
    """Patch textuel exact protégé par le SHA-256 de la version lue."""

    path: str
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    old_text: str = Field(min_length=1, max_length=MAX_TEXT_FILE_BYTES)
    new_text: str = Field(max_length=MAX_TEXT_FILE_BYTES)
    replace_all: bool = False


class MoveFileArguments(StrictToolArguments):
    """Arguments d'un déplacement sans écrasement silencieux."""

    source: str
    destination: str
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RenameFileArguments(StrictToolArguments):
    """Arguments d'un renommage dans le dossier du fichier source."""

    path: str
    new_name: str = Field(min_length=1, max_length=255)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DeleteFileArguments(ReadFileArguments):
    """Arguments d'une suppression sauvegardée et protégée par hash."""

    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class MakeDirectoryArguments(ReadFileArguments):
    """Arguments d'une création de dossier sans parents implicites."""


class FileInfoArguments(ReadFileArguments):
    """Arguments de consultation des métadonnées d'un chemin existant."""


TOOL_ARGUMENT_MODELS: dict[str, type[StrictToolArguments]] = {
    "list_files": ListFilesArguments,
    "search_files": SearchFilesArguments,
    "read_file": ReadFileArguments,
    "read_file_range": ReadFileRangeArguments,
    "create_file": CreateFileArguments,
    "apply_patch": ApplyPatchArguments,
    "move_file": MoveFileArguments,
    "rename_file": RenameFileArguments,
    "delete_file": DeleteFileArguments,
    "make_directory": MakeDirectoryArguments,
    "file_info": FileInfoArguments,
}


def sha256_bytes(content: bytes) -> str:
    """Calcule l'empreinte canonique utilisée pour toutes les écritures optimistes."""

    return hashlib.sha256(content).hexdigest()


def decode_text(content: bytes) -> tuple[str, str]:
    """Détecte les encodages Unicode usuels et refuse les contenus binaires."""

    if len(content) > MAX_TEXT_FILE_BYTES:
        raise FileToolError(f"Le fichier dépasse {MAX_TEXT_FILE_BYTES} octets.")
    if b"\x00" in content[:4096] and not content.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise FileToolError("Le fichier binaire n'est pas pris en charge.")
    candidates = (
        ("utf-8-sig", content.startswith(b"\xef\xbb\xbf")),
        ("utf-16-le", content.startswith(b"\xff\xfe")),
        ("utf-16-be", content.startswith(b"\xfe\xff")),
        ("utf-8", True),
    )
    for encoding, enabled in candidates:
        if not enabled:
            continue
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if encoding.startswith("utf-16") and text.startswith("\ufeff"):
            text = text[1:]
        return text, encoding
    raise FileToolError("L'encodage du fichier texte n'est pas pris en charge.")


def encode_text(content: str, encoding: str) -> bytes:
    """Réencode selon le format détecté sans convertir silencieusement le fichier."""

    try:
        if encoding == "utf-16-le":
            return b"\xff\xfe" + content.encode("utf-16-le")
        if encoding == "utf-16-be":
            return b"\xfe\xff" + content.encode("utf-16-be")
        return content.encode(encoding)
    except UnicodeEncodeError as error:
        raise FileToolError("Le texte ne peut pas conserver l'encodage d'origine.") from error


class IgnoreMatcher:
    """Applique les exclusions sûres par défaut puis les fichiers ignore du projet."""

    def __init__(self, project_root: Path) -> None:
        """Charge `.gitignore` et `.leaignore` sans exécuter Git."""

        self.patterns: list[tuple[str, bool]] = []
        for name in (".gitignore", ".leaignore"):
            path = project_root / name
            if not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8-sig").splitlines()
            except (OSError, UnicodeError):
                continue
            for raw_line in lines:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                included = line.startswith("!")
                pattern = line[1:] if included else line
                self.patterns.append((pattern.replace("\\", "/"), included))

    def ignored(self, relative_path: str, *, is_directory: bool) -> bool:
        """Décide une exclusion avec une sémantique simple, déterministe et bornée."""

        normalized = relative_path.replace("\\", "/").strip("/")
        parts = normalized.split("/") if normalized else []
        if any(part.casefold() in DEFAULT_IGNORED_NAMES for part in parts):
            return True
        if not is_directory and Path(normalized).suffix.casefold() in DEFAULT_IGNORED_SUFFIXES:
            return True
        ignored = False
        for pattern, included in self.patterns:
            directory_pattern = pattern.endswith("/")
            candidate_pattern = pattern.rstrip("/").lstrip("/")
            if directory_pattern and not is_directory:
                matched = normalized.startswith(candidate_pattern + "/")
            elif "/" in candidate_pattern:
                matched = fnmatch.fnmatchcase(normalized, candidate_pattern)
            else:
                matched = any(fnmatch.fnmatchcase(part, candidate_pattern) for part in parts)
            if matched:
                ignored = not included
        return ignored


class FileCheckpointStore:
    """Sauvegarde localement l'état antérieur avant chaque mutation de fichier."""

    def __init__(self, root: Path) -> None:
        """Utilise un dossier ignoré par Git et un verrou de journal par processus."""

        self.root = root
        self._lock = threading.RLock()

    def prepare(
        self,
        run_id: str,
        operation: str,
        originals: list[tuple[str, bytes | None]],
    ) -> str:
        """Écrit les sauvegardes et le manifeste avant d'autoriser la mutation."""

        try:
            canonical_run_id = str(uuid.UUID(run_id))
        except (ValueError, TypeError, AttributeError) as error:
            raise FileToolError("L'identifiant de run est invalide.") from error
        with self._lock:
            run_directory = self.root / canonical_run_id
            run_directory.mkdir(parents=True, exist_ok=True)
            manifest_path = run_directory / "manifest.json"
            entries: list[dict[str, Any]] = []
            if manifest_path.is_file():
                entries = json.loads(manifest_path.read_text(encoding="utf-8"))
            checkpoint_id = str(uuid.uuid4())
            order = len(entries) + 1
            changes: list[dict[str, Any]] = []
            for index, (relative_path, content) in enumerate(originals):
                backup_name = None
                before_hash = None
                if content is not None:
                    backup_name = f"{order:06d}-{index:02d}.bin"
                    (run_directory / backup_name).write_bytes(content)
                    before_hash = sha256_bytes(content)
                changes.append(
                    {
                        "path": relative_path,
                        "existed": content is not None,
                        "before_sha256": before_hash,
                        "backup": backup_name,
                    }
                )
            entries.append(
                {
                    "checkpoint_id": checkpoint_id,
                    "order": order,
                    "operation": operation,
                    "status": "prepared",
                    "changes": changes,
                }
            )
            self._write_manifest(manifest_path, entries)
            return checkpoint_id

    def complete(self, run_id: str, checkpoint_id: str, after_hashes: dict[str, str | None]) -> None:
        """Marque le checkpoint terminé avec les empreintes réellement observées."""

        with self._lock:
            manifest_path = self.root / str(uuid.UUID(run_id)) / "manifest.json"
            entries = json.loads(manifest_path.read_text(encoding="utf-8"))
            entry = next(item for item in entries if item["checkpoint_id"] == checkpoint_id)
            entry["status"] = "completed"
            for change in entry["changes"]:
                change["after_sha256"] = after_hashes.get(change["path"])
            self._write_manifest(manifest_path, entries)

    @staticmethod
    def _write_manifest(path: Path, entries: list[dict[str, Any]]) -> None:
        """Remplace atomiquement le manifeste pour survivre à une interruption."""

        descriptor, temporary_name = tempfile.mkstemp(prefix="manifest-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(entries, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise


class FileToolExecutor:
    """Exécute seulement les outils nommés du catalogue sur le projet SQLite actif."""

    def __init__(
        self,
        database: Database,
        guard: WorkspaceGuard,
        checkpoint_root: Path,
    ) -> None:
        """Lie l'autorité SQLite, le confinement et le stockage de rollback."""

        self.database = database
        self.guard = guard
        self.checkpoints = FileCheckpointStore(checkpoint_root)

    def schemas(self) -> list[dict[str, Any]]:
        """Expose des schémas JSON stricts compatibles avec l'API d'outils llama.cpp."""

        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": model.__doc__.strip() if model.__doc__ else name,
                    "parameters": model.model_json_schema(),
                },
            }
            for name, model in TOOL_ARGUMENT_MODELS.items()
        ]

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Valide les arguments puis distribue vers une méthode fixe, jamais dynamique."""

        argument_model = TOOL_ARGUMENT_MODELS.get(name)
        if argument_model is None:
            raise FileToolError("Outil de fichier inconnu.")
        parsed = argument_model.model_validate(arguments)
        handler = {
            "list_files": self._list_files,
            "search_files": self._search_files,
            "read_file": self._read_file,
            "read_file_range": self._read_file_range,
            "create_file": self._create_file,
            "apply_patch": self._apply_patch,
            "move_file": self._move_file,
            "rename_file": self._rename_file,
            "delete_file": self._delete_file,
            "make_directory": self._make_directory,
            "file_info": self._file_info,
        }[name]
        effective_run_id = run_id or str(uuid.uuid4())
        try:
            return handler(parsed, effective_run_id)
        except (OSError, UnicodeError, WorkspacePathError) as error:
            raise FileToolError(str(error)) from error

    def _active_project(self) -> ValidatedWorkspacePath:
        """Résout à chaque action l'unique projet actif depuis son chemin relatif."""

        project = self.database.get_active_project()
        if project is None:
            raise ProjectNotFoundError("Sélectionne un projet actif avant d'utiliser un outil.")
        return self.guard.resolve_project(project["relative_path"])

    def _iter_visible(self, project: ValidatedWorkspacePath, start: Path) -> list[Path]:
        """Parcourt les chemins visibles sans suivre de reparse point ni dossier ignoré."""

        matcher = IgnoreMatcher(project.path)
        visible: list[Path] = []
        stack = [start]
        while stack:
            directory = stack.pop()
            children = sorted(directory.iterdir(), key=lambda item: (item.name.casefold(), item.name))
            for child in children:
                relative = child.relative_to(project.path).as_posix()
                try:
                    validated = self.guard.resolve_member(project, relative)
                except WorkspacePathError:
                    continue
                is_directory = validated.path.is_dir()
                if matcher.ignored(relative, is_directory=is_directory):
                    continue
                visible.append(validated.path)
                if is_directory:
                    stack.append(validated.path)
        return sorted(visible, key=lambda item: item.relative_to(project.path).as_posix().casefold())

    def _read_bytes(self, project: ValidatedWorkspacePath, relative_path: str) -> tuple[ValidatedWorkspacePath, bytes]:
        """Lit un fichier ordinaire borné après validation du projet et du membre."""

        member = self.guard.resolve_member(project, relative_path)
        if not member.path.is_file():
            raise FileToolError("Le chemin demandé n'est pas un fichier.")
        size = member.path.stat().st_size
        if size > MAX_TEXT_FILE_BYTES:
            raise FileToolError(f"Le fichier dépasse {MAX_TEXT_FILE_BYTES} octets.")
        content = member.path.read_bytes()
        self.guard.revalidate_member(project, member)
        return member, content

    def _list_files(self, arguments: ListFilesArguments, _run_id: str) -> dict[str, Any]:
        """Liste une tranche déterministe de fichiers et dossiers visibles."""

        project = self._active_project()
        start = self.guard.resolve_member(project, arguments.path)
        if not start.path.is_dir():
            raise FileToolError("Le chemin de liste n'est pas un dossier.")
        paths = self._iter_visible(project, start.path)
        if not arguments.recursive:
            paths = [path for path in paths if path.parent == start.path]
        page = paths[arguments.cursor : arguments.cursor + arguments.limit]
        next_cursor = arguments.cursor + len(page)
        return {
            "entries": [
                {
                    "path": path.relative_to(project.path).as_posix(),
                    "type": "directory" if path.is_dir() else "file",
                    "size": path.stat().st_size if path.is_file() else None,
                }
                for path in page
            ],
            "next_cursor": next_cursor if next_cursor < len(paths) else None,
            "total_visible": len(paths),
        }

    def _search_files(self, arguments: SearchFilesArguments, _run_id: str) -> dict[str, Any]:
        """Recherche un texte dans les fichiers visibles sans charger de binaire."""

        project = self._active_project()
        start = self.guard.resolve_member(project, arguments.path)
        matcher = IgnoreMatcher(project.path)
        if start.path.is_file() and matcher.ignored(start.relative_path, is_directory=False):
            candidates: list[Path] = []
        else:
            candidates = [start.path] if start.path.is_file() else self._iter_visible(project, start.path)
        matches: list[dict[str, Any]] = []
        needle = arguments.query if arguments.case_sensitive else arguments.query.casefold()
        for path in candidates:
            if not path.is_file() or path.stat().st_size > MAX_TEXT_FILE_BYTES:
                continue
            try:
                text, _encoding = decode_text(path.read_bytes())
            except FileToolError:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                haystack = line if arguments.case_sensitive else line.casefold()
                if needle in haystack:
                    matches.append(
                        {
                            "path": path.relative_to(project.path).as_posix(),
                            "line": line_number,
                            "preview": line[:500],
                        }
                    )
        page = matches[arguments.cursor : arguments.cursor + arguments.limit]
        next_cursor = arguments.cursor + len(page)
        return {
            "matches": page,
            "next_cursor": next_cursor if next_cursor < len(matches) else None,
            "total_matches": len(matches),
        }

    def _read_file(self, arguments: ReadFileArguments, _run_id: str) -> dict[str, Any]:
        """Retourne le texte, l'encodage et le hash utiles à un futur patch."""

        project = self._active_project()
        member, content = self._read_bytes(project, arguments.path)
        text, encoding = decode_text(content)
        return {
            "path": member.relative_path,
            "content": text,
            "encoding": encoding,
            "sha256": sha256_bytes(content),
            "size": len(content),
        }

    def _read_file_range(self, arguments: ReadFileRangeArguments, _run_id: str) -> dict[str, Any]:
        """Retourne au plus 500 lignes inclusives avec leurs limites réelles."""

        if arguments.end_line < arguments.start_line:
            raise FileToolError("end_line doit être supérieur ou égal à start_line.")
        if arguments.end_line - arguments.start_line + 1 > MAX_RANGE_LINES:
            raise FileToolError(f"Une lecture est limitée à {MAX_RANGE_LINES} lignes.")
        result = self._read_file(ReadFileArguments(path=arguments.path), _run_id)
        lines = str(result["content"]).splitlines(keepends=True)
        result["content"] = "".join(lines[arguments.start_line - 1 : arguments.end_line])
        result["start_line"] = arguments.start_line
        result["end_line"] = min(arguments.end_line, len(lines))
        result["total_lines"] = len(lines)
        return result

    def _temporary_file(self, parent: Path, content: bytes) -> Path:
        """Écrit et synchronise un fichier temporaire dans le dossier de destination."""

        descriptor, name = tempfile.mkstemp(prefix=".lea-write-", suffix=".tmp", dir=parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            return Path(name)
        except BaseException:
            try:
                os.unlink(name)
            except OSError:
                pass
            raise

    def _create_file(self, arguments: CreateFileArguments, run_id: str) -> dict[str, Any]:
        """Crée un fichier UTF-8 par hard-link atomique depuis un temporaire synchronisé."""

        project = self._active_project()
        destination, parent = self.guard.resolve_destination(project, arguments.path)
        content = arguments.content.encode("utf-8")
        if len(content) > MAX_TEXT_FILE_BYTES:
            raise FileToolError(f"Le contenu dépasse {MAX_TEXT_FILE_BYTES} octets.")
        relative = destination.relative_to(project.path).as_posix()
        checkpoint = self.checkpoints.prepare(run_id, "create_file", [(relative, None)])
        temporary = self._temporary_file(parent.path, content)
        try:
            self.guard.revalidate_project(project)
            self.guard.revalidate_member(project, parent)
            if destination.exists() or destination.is_symlink():
                raise FileToolError("La destination existe déjà.")
            os.link(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        created = self.guard.resolve_member(project, relative)
        after_hash = sha256_bytes(created.path.read_bytes())
        self.checkpoints.complete(run_id, checkpoint, {relative: after_hash})
        return {"path": relative, "sha256": after_hash, "checkpoint_id": checkpoint, "run_id": run_id}

    def _apply_patch(self, arguments: ApplyPatchArguments, run_id: str) -> dict[str, Any]:
        """Remplace un texte exact après double vérification du hash et de l'identité."""

        project = self._active_project()
        member, original = self._read_bytes(project, arguments.path)
        if sha256_bytes(original) != arguments.expected_sha256:
            raise FileToolError("Le fichier a changé depuis sa lecture ; patch refusé.")
        text, encoding = decode_text(original)
        occurrences = text.count(arguments.old_text)
        if occurrences == 0 or (occurrences != 1 and not arguments.replace_all):
            raise FileToolError("Le texte à remplacer est absent ou ambigu.")
        updated_text = text.replace(
            arguments.old_text,
            arguments.new_text,
            -1 if arguments.replace_all else 1,
        )
        updated = encode_text(updated_text, encoding)
        if len(updated) > MAX_TEXT_FILE_BYTES:
            raise FileToolError(f"Le fichier modifié dépasse {MAX_TEXT_FILE_BYTES} octets.")
        checkpoint = self.checkpoints.prepare(run_id, "apply_patch", [(member.relative_path, original)])
        temporary = self._temporary_file(member.path.parent, updated)
        try:
            current = self.guard.revalidate_member(project, member)
            if sha256_bytes(current.path.read_bytes()) != arguments.expected_sha256:
                raise FileToolError("Le fichier a changé pendant le patch ; opération refusée.")
            os.replace(temporary, current.path)
        finally:
            temporary.unlink(missing_ok=True)
        after_hash = sha256_bytes(member.path.read_bytes())
        self.checkpoints.complete(run_id, checkpoint, {member.relative_path: after_hash})
        return {"path": member.relative_path, "sha256": after_hash, "checkpoint_id": checkpoint, "run_id": run_id}

    def _move_file(self, arguments: MoveFileArguments, run_id: str) -> dict[str, Any]:
        """Déplace atomiquement un fichier vérifié vers une destination inexistante."""

        project = self._active_project()
        source, original = self._read_bytes(project, arguments.source)
        if sha256_bytes(original) != arguments.expected_sha256:
            raise FileToolError("Le fichier source a changé ; déplacement refusé.")
        destination, parent = self.guard.resolve_destination(project, arguments.destination)
        destination_relative = destination.relative_to(project.path).as_posix()
        checkpoint = self.checkpoints.prepare(
            run_id,
            "move_file",
            [(source.relative_path, original), (destination_relative, None)],
        )
        self.guard.revalidate_member(project, source)
        self.guard.revalidate_member(project, parent)
        if destination.exists() or destination.is_symlink():
            raise FileToolError("La destination existe déjà.")
        os.rename(source.path, destination)
        after_hash = sha256_bytes(destination.read_bytes())
        self.checkpoints.complete(
            run_id,
            checkpoint,
            {source.relative_path: None, destination_relative: after_hash},
        )
        return {"source": source.relative_path, "destination": destination_relative, "sha256": after_hash, "checkpoint_id": checkpoint, "run_id": run_id}

    def _rename_file(self, arguments: RenameFileArguments, run_id: str) -> dict[str, Any]:
        """Transforme un nouveau nom simple en déplacement sûr dans le même dossier."""

        if len(Path(arguments.new_name).parts) != 1 or arguments.new_name in {".", ".."}:
            raise FileToolError("Le nouveau nom doit être un nom de fichier simple.")
        source_path = Path(arguments.path.replace("\\", "/"))
        destination = (source_path.parent / arguments.new_name).as_posix()
        return self._move_file(
            MoveFileArguments(
                source=arguments.path,
                destination=destination,
                expected_sha256=arguments.expected_sha256,
            ),
            run_id,
        )

    def _delete_file(self, arguments: DeleteFileArguments, run_id: str) -> dict[str, Any]:
        """Sauvegarde puis supprime un fichier seulement si son hash reste identique."""

        project = self._active_project()
        member, original = self._read_bytes(project, arguments.path)
        if sha256_bytes(original) != arguments.expected_sha256:
            raise FileToolError("Le fichier a changé ; suppression refusée.")
        checkpoint = self.checkpoints.prepare(run_id, "delete_file", [(member.relative_path, original)])
        current = self.guard.revalidate_member(project, member)
        if sha256_bytes(current.path.read_bytes()) != arguments.expected_sha256:
            raise FileToolError("Le fichier a changé pendant la suppression ; opération refusée.")
        current.path.unlink()
        self.checkpoints.complete(run_id, checkpoint, {member.relative_path: None})
        return {"path": member.relative_path, "deleted": True, "checkpoint_id": checkpoint, "run_id": run_id}

    def _make_directory(self, arguments: MakeDirectoryArguments, run_id: str) -> dict[str, Any]:
        """Crée un seul dossier après checkpoint et revalidation de son parent."""

        project = self._active_project()
        destination, parent = self.guard.resolve_destination(project, arguments.path)
        relative = destination.relative_to(project.path).as_posix()
        checkpoint = self.checkpoints.prepare(run_id, "make_directory", [(relative, None)])
        self.guard.revalidate_member(project, parent)
        destination.mkdir()
        self.checkpoints.complete(run_id, checkpoint, {relative: None})
        return {"path": relative, "created": True, "checkpoint_id": checkpoint, "run_id": run_id}

    def _file_info(self, arguments: FileInfoArguments, _run_id: str) -> dict[str, Any]:
        """Retourne les métadonnées relatives et le hash d'un fichier ordinaire."""

        project = self._active_project()
        member = self.guard.resolve_member(project, arguments.path)
        metadata = member.path.stat()
        result: dict[str, Any] = {
            "path": member.relative_path,
            "type": "directory" if member.path.is_dir() else "file",
            "size": metadata.st_size if member.path.is_file() else None,
            "modified_ns": metadata.st_mtime_ns,
        }
        if member.path.is_file():
            _member, content = self._read_bytes(project, arguments.path)
            result["sha256"] = sha256_bytes(content)
            result["encoding"] = decode_text(content)[1]
        return result
