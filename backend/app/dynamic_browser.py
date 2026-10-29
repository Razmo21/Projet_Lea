"""Lecture JavaScript publique, éphémère et strictement non interactive.

Edge ne démarre que pendant un recours explicite du Web Gateway. Son profil
temporaire est supprimé après usage et tout trafic HTTP(S) traverse un proxy
local qui résout puis épingle uniquement des destinations publiques.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit


LOGGER = logging.getLogger(__name__)
EDGE_EXECUTABLE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
_MAX_PROXY_HEADER_BYTES = 32 * 1024
_ALLOWED_RESOURCE_TYPES = frozenset({"document", "fetch", "script", "stylesheet", "xhr"})
_DOWNLOAD_SUFFIXES = (
    ".7z",
    ".dmg",
    ".doc",
    ".docx",
    ".exe",
    ".iso",
    ".msi",
    ".pdf",
    ".pkg",
    ".rar",
    ".tar",
    ".zip",
)
_SENSITIVE_NAVIGATION = re.compile(
    r"(?:^|[/_?&=.-])(?:auth|book(?:ing)?|buy|cart|checkout|confirm|delete|download|"
    r"install|login|logout|oauth|order|pay(?:ment)?|purchase|remove|reserv(?:e|ation)|"
    r"signin|signup|submit|subscribe)(?:$|[/_?&=.-])",
    re.IGNORECASE,
)
_BLOCKED_PAGE = re.compile(
    r"\b(?:captcha|verify you are human|vérifiez que vous êtes humain|access denied|"
    r"accès refusé|sign in to continue|connectez-vous pour continuer|paywall)\b",
    re.IGNORECASE,
)


class PublicDestinationPolicy(Protocol):
    """Surface minimale réutilisée depuis la barrière SSRF du Web Gateway."""

    @staticmethod
    def validate_url(url: str) -> tuple[str, int]:
        """Valide la forme et la destination publique apparente."""

        ...

    async def resolve_public_destination(self, url: str) -> tuple[str, int, str]:
        """Retourne le nom, le port et une IP publique déjà contrôlée."""

        ...


class DynamicBrowserError(RuntimeError):
    """Erreur interne traduite en erreur publique par le Web Gateway."""


class DynamicBrowserUnavailable(DynamicBrowserError):
    """Edge ou Playwright n'est pas utilisable pour cette lecture."""


class DynamicBrowserPolicyError(DynamicBrowserError):
    """Une navigation ou sous-ressource enfreint la politique publique."""


class DynamicBrowserTimeout(DynamicBrowserError):
    """La session a dépassé son budget temporel."""


class DynamicBrowserCancelled(DynamicBrowserError):
    """La session a été annulée par l'utilisateur ou le client local."""


@dataclass(frozen=True)
class DynamicBrowserLimits:
    """Budgets maximaux d'une unique session Edge dynamique."""

    timeout_seconds: int = 20
    max_pages: int = 3
    max_requests: int = 80
    max_characters: int = 8_000
    max_proxy_bytes: int = 12 * 1024 * 1024
    max_connections: int = 24

    def __post_init__(self) -> None:
        """Empêche un appelant d'élargir silencieusement les plafonds livrés."""

        valid = (
            5 <= self.timeout_seconds <= 25
            and 1 <= self.max_pages <= 3
            and 10 <= self.max_requests <= 100
            and 1_000 <= self.max_characters <= 12_000
            and 1 * 1024 * 1024 <= self.max_proxy_bytes <= 16 * 1024 * 1024
            and 4 <= self.max_connections <= 32
        )
        if not valid:
            raise ValueError("Budget de navigation dynamique invalide.")


@dataclass(frozen=True)
class DynamicPagePart:
    """Conserve le texte visible avec l'URL exacte de la page qui le porte."""

    url: str
    title: str
    content: str
    published_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class DynamicPageSnapshot:
    """Texte visible et métadonnées bornées extraits d'une session jetable."""

    url: str
    title: str
    content: str
    page_count: int
    published_at: str | None = None
    updated_at: str | None = None
    pages: tuple[DynamicPagePart, ...] = ()


class _BrowserNetworkGuard:
    """Partage la validation URL et l'épinglage DNS entre routeur et proxy."""

    def __init__(
        self,
        policy: PublicDestinationPolicy,
        *,
        test_origins: frozenset[str] = frozenset(),
    ) -> None:
        """Les origines locales sont réservées aux serveurs isolés des tests."""

        self.policy = policy
        self.test_origins = test_origins

    @staticmethod
    def origin(url: str) -> str:
        """Normalise une origine HTTP(S) en incluant son port effectif."""

        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError:
            return ""
        return f"{parsed.scheme}://{parsed.hostname.rstrip('.').lower()}:{port}"

    def validate_url(self, url: str) -> tuple[str, int]:
        """Accepte une origine de test exacte ou applique la politique de production."""

        origin = self.origin(url)
        if origin in self.test_origins:
            parsed = urlsplit(url)
            return (
                str(parsed.hostname),
                parsed.port or (443 if parsed.scheme == "https" else 80),
            )
        try:
            return self.policy.validate_url(url)
        except Exception as error:
            raise DynamicBrowserPolicyError("Destination de navigation refusée.") from error

    async def resolve(self, url: str) -> tuple[str, int, str]:
        """Résout une destination publique ou l'origine locale exacte d'un test."""

        host, port = self.validate_url(url)
        if self.origin(url) in self.test_origins:
            return host, port, host
        try:
            return await self.policy.resolve_public_destination(url)
        except Exception as error:
            raise DynamicBrowserPolicyError("Destination de navigation refusée.") from error


class _TrafficBudget:
    """Compte les octets cumulés de tous les tunnels d'une session."""

    def __init__(self, limit: int) -> None:
        """Initialise le plafond partagé et son verrou de concurrence."""

        self.limit = limit
        self.total = 0
        self.lock = asyncio.Lock()

    async def consume(self, size: int) -> None:
        """Interrompt le flux avant de dépasser le plafond partagé."""

        async with self.lock:
            self.total += size
            if self.total > self.limit:
                raise DynamicBrowserPolicyError("Budget réseau de la navigation dépassé.")


class _PinnedHttpProxy:
    """Proxy jetable qui bloque le réseau privé et épingle chaque résolution DNS."""

    def __init__(
        self,
        guard: _BrowserNetworkGuard,
        limits: DynamicBrowserLimits,
        allowed_hosts: frozenset[str],
    ) -> None:
        """Fige les seules destinations et ressources autorisées pour la session."""

        self.guard = guard
        self.limits = limits
        self.allowed_hosts = allowed_hosts
        self.server: asyncio.Server | None = None
        self.tasks: set[asyncio.Task[object]] = set()
        self.connections = asyncio.Semaphore(limits.max_connections)
        self.traffic = _TrafficBudget(limits.max_proxy_bytes)

    async def __aenter__(self) -> "_PinnedHttpProxy":
        """Ouvre une écoute loopback éphémère seulement pour la durée du navigateur."""

        self.server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Ferme l'écoute et tous les tunnels encore actifs, même après erreur."""

        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
        pending = [task for task in self.tasks if task is not asyncio.current_task()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    @property
    def url(self) -> str:
        """Expose l'adresse locale uniquement après ouverture du proxy."""

        if self.server is None or not self.server.sockets:
            raise RuntimeError("Le proxy dynamique n'est pas ouvert.")
        return f"http://127.0.0.1:{self.server.sockets[0].getsockname()[1]}"

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Traite une seule requête proxy puis ferme explicitement la connexion."""

        task = asyncio.current_task()
        if task is not None:
            self.tasks.add(task)
        try:
            async with self.connections:
                await self._serve_request(reader, writer)
        except (asyncio.CancelledError, DynamicBrowserPolicyError):
            with contextlib.suppress(Exception):
                writer.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
                await writer.drain()
        except (
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            OSError,
            TimeoutError,
            ValueError,
            UnicodeError,
        ) as error:
            LOGGER.debug("dynamic_proxy_connection_failed error=%s", type(error).__name__)
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            if task is not None:
                self.tasks.discard(task)

    async def _serve_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Valide l'en-tête, résout la cible puis relaie vers l'IP publique choisie."""

        header = await asyncio.wait_for(
            reader.readuntil(b"\r\n\r\n"),
            timeout=5,
        )
        if len(header) > _MAX_PROXY_HEADER_BYTES:
            raise DynamicBrowserPolicyError("En-tête proxy trop volumineux.")
        lines = header.decode("iso-8859-1").split("\r\n")
        method, target, version = lines[0].split(" ", 2)
        if version not in {"HTTP/1.0", "HTTP/1.1"}:
            raise DynamicBrowserPolicyError("Version HTTP refusée.")

        if method == "CONNECT":
            parsed_target = urlsplit(f"//{target}")
            if (
                not parsed_target.hostname
                or parsed_target.username is not None
                or parsed_target.password is not None
            ):
                raise DynamicBrowserPolicyError("Tunnel sans destination.")
            port = parsed_target.port or 443
            url = f"https://{parsed_target.hostname}:{port}/"
            _host, destination_port, ip = await self._resolve(url)
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(ip, destination_port),
                timeout=5,
            )
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await self._tunnel(reader, writer, upstream_reader, upstream_writer)
            return

        if method not in {"GET", "HEAD"}:
            raise DynamicBrowserPolicyError("Méthode HTTP refusée.")
        target_url = self._absolute_target(target, lines[1:])
        host, port, ip = await self._resolve(target_url)
        parsed = urlsplit(target_url)
        upstream_reader, upstream_writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=5,
        )
        default_port = 443 if parsed.scheme == "https" else 80
        host_header = host if port == default_port else f"{host}:{port}"
        path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        filtered_headers = [
            line
            for line in lines[1:]
            if line
            and not line.casefold().startswith(
                (
                    "authorization:",
                    "connection:",
                    "content-length:",
                    "cookie:",
                    "host:",
                    "proxy-authorization:",
                    "proxy-connection:",
                    "transfer-encoding:",
                )
            )
        ]
        outbound = (
            f"{method} {path} HTTP/1.1\r\nHost: {host_header}\r\n"
            + "\r\n".join(filtered_headers)
            + "\r\nConnection: close\r\n\r\n"
        ).encode("iso-8859-1")
        await self.traffic.consume(len(outbound))
        upstream_writer.write(outbound)
        await upstream_writer.drain()
        try:
            while chunk := await upstream_reader.read(64 * 1024):
                await self.traffic.consume(len(chunk))
                writer.write(chunk)
                await writer.drain()
        finally:
            upstream_writer.close()
            with contextlib.suppress(Exception):
                await upstream_writer.wait_closed()

    async def _resolve(self, url: str) -> tuple[str, int, str]:
        """Limite aussi le proxy aux hôtes explicitement nécessaires à cette page."""

        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold().rstrip(".")
        if host not in self.allowed_hosts:
            raise DynamicBrowserPolicyError("Hôte tiers refusé par la session dynamique.")
        return await self.guard.resolve(url)

    @staticmethod
    def _absolute_target(target: str, headers: list[str]) -> str:
        """Reconstruit prudemment une URL lorsque le client envoie une forme relative."""

        parsed = urlsplit(target)
        if parsed.scheme == "http" and parsed.hostname:
            return target
        host = next(
            (line.split(":", 1)[1].strip() for line in headers if line.casefold().startswith("host:")),
            "",
        )
        if not host or not target.startswith("/"):
            raise DynamicBrowserPolicyError("Cible HTTP proxy invalide.")
        return f"http://{host}{target}"

    async def _tunnel(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        """Relaye un CONNECT TLS sans inspection, avec budget et fermeture symétrique."""

        async def copy(source: asyncio.StreamReader, destination: asyncio.StreamWriter) -> None:
            """Copie un sens du tunnel jusqu'à EOF ou dépassement du budget."""

            while chunk := await source.read(64 * 1024):
                await self.traffic.consume(len(chunk))
                destination.write(chunk)
                await destination.drain()

        tasks = {
            asyncio.create_task(copy(client_reader, upstream_writer)),
            asyncio.create_task(copy(upstream_reader, client_writer)),
        }
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
        finally:
            upstream_writer.close()
            with contextlib.suppress(Exception):
                await upstream_writer.wait_closed()


class EdgeDynamicPageReader:
    """Rend une page publique avec Edge sans clic, formulaire ni état persistant."""

    def __init__(
        self,
        policy: PublicDestinationPolicy,
        runtime_root: str | Path,
        *,
        limits: DynamicBrowserLimits | None = None,
        edge_executable: str | Path = EDGE_EXECUTABLE,
        _test_origins: frozenset[str] = frozenset(),
    ) -> None:
        """Conserve seulement la configuration ; aucun processus ne démarre ici."""

        self.guard = _BrowserNetworkGuard(policy, test_origins=_test_origins)
        self.runtime_root = Path(runtime_root).resolve()
        self.limits = limits or DynamicBrowserLimits()
        self.edge_executable = Path(edge_executable).resolve()
        self._operation_lock = asyncio.Lock()

    async def read(
        self,
        url: str,
        *,
        cancelled: Callable[[], Awaitable[bool]] | None = None,
    ) -> DynamicPageSnapshot:
        """Lance une session unique et l'annule immédiatement sur demande locale."""

        self.guard.validate_url(url)
        if not _safe_document_url(url):
            raise DynamicBrowserPolicyError("Adresse de navigation sensible refusée.")
        async with self._operation_lock:
            if cancelled is not None and await cancelled():
                raise DynamicBrowserCancelled("Navigation dynamique annulée.")
            abort = asyncio.Event()
            operation = asyncio.create_task(self._read_once(url, abort))
            cancellation = (
                asyncio.create_task(self._wait_for_cancellation(cancelled))
                if cancelled is not None
                else None
            )
            timeout = asyncio.create_task(asyncio.sleep(self.limits.timeout_seconds))
            try:
                waiters = {operation, timeout}
                if cancellation is not None:
                    waiters.add(cancellation)
                done, _pending = await asyncio.wait(
                    waiters,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if operation in done:
                    return await operation
                abort.set()
                await self._finish_aborted_operation(operation)
                if cancellation is not None and cancellation in done:
                    raise DynamicBrowserCancelled("Navigation dynamique annulée.")
                raise DynamicBrowserTimeout("Navigation dynamique trop lente.")
            except asyncio.CancelledError:
                abort.set()
                await asyncio.shield(self._finish_aborted_operation(operation))
                raise
            finally:
                timeout.cancel()
                await asyncio.gather(timeout, return_exceptions=True)
                if cancellation is not None:
                    cancellation.cancel()
                    await asyncio.gather(cancellation, return_exceptions=True)

    @staticmethod
    async def _wait_for_cancellation(
        cancelled: Callable[[], Awaitable[bool]],
    ) -> None:
        """Observe l'annulation sans créer de tâche réseau ni de boucle au repos."""

        while not await cancelled():
            await asyncio.sleep(0.1)

    @staticmethod
    async def _finish_aborted_operation(operation: asyncio.Task[DynamicPageSnapshot]) -> None:
        """Laisse Playwright fermer son pilote avant d'employer l'annulation forcée."""

        try:
            await asyncio.wait_for(asyncio.shield(operation), timeout=5)
        except DynamicBrowserCancelled:
            return
        except TimeoutError:
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
        except DynamicBrowserError:
            return

    async def _read_once(
        self,
        url: str,
        abort: asyncio.Event,
    ) -> DynamicPageSnapshot:
        """Crée le proxy, le profil Edge et une seule page dans un bloc de nettoyage."""

        if not self.edge_executable.is_file():
            raise DynamicBrowserUnavailable(
                "Microsoft Edge n'est pas installé à l'emplacement attendu."
            )
        try:
            from playwright.async_api import Error as PlaywrightError
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except ImportError as error:
            raise DynamicBrowserUnavailable(
                "Le pilote Playwright local n'est pas installé."
            ) from error

        self.runtime_root.mkdir(parents=True, exist_ok=True)
        guard = self.guard
        limits = self.limits
        request_count = 0
        initial_host = (urlsplit(url).hostname or "").casefold().rstrip(".")

        async with _PinnedHttpProxy(guard, limits, frozenset({initial_host})) as proxy:
            try:
                with tempfile.TemporaryDirectory(
                    prefix="lea-edge-",
                    dir=self.runtime_root,
                ) as profile_directory:
                    async with async_playwright() as playwright:
                        context = await playwright.chromium.launch_persistent_context(
                            profile_directory,
                            executable_path=str(self.edge_executable),
                            headless=True,
                            accept_downloads=False,
                            service_workers="block",
                            permissions=[],
                            proxy={"server": proxy.url, "bypass": "<-loopback>"},
                            viewport={"width": 1280, "height": 900},
                            locale="fr-CA",
                            args=[
                                "--disable-background-networking",
                                "--disable-breakpad",
                                "--disable-component-update",
                                "--disable-default-apps",
                                "--disable-domain-reliability",
                                "--disable-extensions",
                                "--disable-features=AutofillServerCommunication,OptimizationHints,Translate",
                                "--disable-notifications",
                                "--disable-print-preview",
                                "--disable-quic",
                                "--disable-sync",
                                "--deny-permission-prompts",
                                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                                "--no-first-run",
                                "--safebrowsing-disable-auto-update",
                            ],
                        )
                        try:
                            pages = context.pages
                            page = pages[0] if pages else await context.new_page()
                            for extra_page in pages[1:]:
                                await extra_page.close()

                            async def close_popup(new_page) -> None:
                                """Ferme toute page secondaire créée par le contenu non fiable."""

                                if new_page is not page:
                                    await new_page.close()

                            event_tasks: set[asyncio.Task[object]] = set()

                            def schedule_event(coroutine) -> None:
                                """Suit chaque nettoyage déclenché par un événement Edge."""

                                task = asyncio.create_task(coroutine)
                                event_tasks.add(task)
                                task.add_done_callback(event_tasks.discard)

                            def schedule_popup_close(new_page) -> None:
                                """Programme le nettoyage depuis le callback synchrone Playwright."""

                                schedule_event(close_popup(new_page))

                            context.on("page", schedule_popup_close)

                            async def route_request(route, request) -> None:
                                """Autorise seulement GET/HEAD et les ressources utiles à la lecture."""

                                nonlocal request_count
                                request_count += 1
                                if request_count > limits.max_requests:
                                    await route.abort("blockedbyclient")
                                    return
                                if request.method not in {"GET", "HEAD"}:
                                    await route.abort("blockedbyclient")
                                    return
                                if request.resource_type not in _ALLOWED_RESOURCE_TYPES:
                                    await route.abort("blockedbyclient")
                                    return
                                try:
                                    guard.validate_url(request.url)
                                except DynamicBrowserPolicyError:
                                    await route.abort("blockedbyclient")
                                    return
                                parsed_request = urlsplit(request.url)
                                target_host = (
                                    parsed_request.hostname or ""
                                ).casefold().rstrip(".")
                                if target_host != initial_host:
                                    await route.abort("blockedbyclient")
                                    return
                                if request.resource_type in {
                                    "document",
                                    "fetch",
                                    "xhr",
                                } and not _safe_document_url(request.url):
                                    await route.abort("blockedbyclient")
                                    return
                                headers = {
                                    name: value
                                    for name, value in request.headers.items()
                                    if name.casefold()
                                    not in {
                                        "authorization",
                                        "cookie",
                                        "proxy-authorization",
                                    }
                                }
                                await route.continue_(headers=headers)

                            await context.route("**/*", route_request)
                            page.on("dialog", lambda dialog: schedule_event(dialog.dismiss()))
                            page.on("download", lambda download: schedule_event(download.cancel()))
                            reading = asyncio.create_task(
                                self._read_pages(page, url, initial_host)
                            )
                            aborting = asyncio.create_task(abort.wait())
                            try:
                                done, _pending = await asyncio.wait(
                                    {reading, aborting},
                                    return_when=asyncio.FIRST_COMPLETED,
                                )
                                if aborting in done:
                                    await context.close()
                                    await asyncio.gather(reading, return_exceptions=True)
                                    raise DynamicBrowserCancelled("Navigation dynamique annulée.")
                                snapshot = await reading
                                await context.clear_cookies()
                                return snapshot
                            finally:
                                aborting.cancel()
                                await asyncio.gather(aborting, return_exceptions=True)
                                if event_tasks:
                                    await asyncio.gather(
                                        *tuple(event_tasks),
                                        return_exceptions=True,
                                    )
                        finally:
                            await context.close()
            except PlaywrightTimeoutError as error:
                raise DynamicBrowserTimeout("La page dynamique n'a pas répondu à temps.") from error
            except PlaywrightError as error:
                LOGGER.warning("dynamic_browser_failed error=%s", type(error).__name__)
                raise DynamicBrowserUnavailable(
                    "La page dynamique n'a pas pu être lue par Edge."
                ) from error
            finally:
                self._remove_empty_runtime_root()

    async def _read_pages(self, page, url: str, initial_host: str) -> DynamicPageSnapshot:
        """Lit le document courant puis suit au plus deux liens de pagination sûrs."""

        parts: list[DynamicPagePart] = []
        title = ""
        final_url = url
        published_at: str | None = None
        updated_at: str | None = None
        current_url: str | None = url
        visited: set[str] = set()

        while current_url and len(parts) < self.limits.max_pages:
            if current_url in visited:
                break
            visited.add(current_url)
            response = await page.goto(
                current_url,
                wait_until="domcontentloaded",
                timeout=min(12_000, self.limits.timeout_seconds * 1_000),
            )
            if response is not None and response.status >= 400:
                raise DynamicBrowserUnavailable(
                    f"La page dynamique a répondu avec le statut HTTP {response.status}."
                )
            with contextlib.suppress(Exception):
                await page.wait_for_load_state("networkidle", timeout=2_500)
            data = await page.evaluate(_EXTRACT_VISIBLE_PAGE_SCRIPT)
            visible = _clean_visible_text(
                str(data.get("content") or ""),
                self.limits.max_characters,
            )
            if _BLOCKED_PAGE.search(f"{data.get('title', '')} {visible[:1_500]}") or bool(
                data.get("blocked")
            ):
                raise DynamicBrowserPolicyError(
                    "La page demande une authentification, un CAPTCHA ou un contournement refusé."
                )
            if not visible:
                raise DynamicBrowserUnavailable(
                    "La page dynamique ne fournit aucun texte public exploitable."
                )
            download_links: list[str] = []
            for raw_link in list(data.get("downloadUrls") or [])[:5]:
                download_url = str(raw_link)
                parsed_download = urlsplit(download_url)
                download_host = (
                    parsed_download.hostname or ""
                ).casefold().rstrip(".")
                if (
                    download_host == initial_host
                    and parsed_download.path.casefold().endswith(_DOWNLOAD_SUFFIXES)
                ):
                    self.guard.validate_url(download_url)
                    download_links.append(download_url)
            if download_links:
                visible += " Liens de téléchargement repérés mais non ouverts : "
                visible += ", ".join(dict.fromkeys(download_links))
            page_title = _clean_visible_text(
                str(data.get("title") or ""),
                300,
            ) or "Page publique"
            page_published_at = _optional_text(data.get("publishedAt"), 100)
            page_updated_at = _optional_text(data.get("updatedAt"), 100)
            if not title:
                title = page_title
                published_at = page_published_at
                updated_at = page_updated_at
            final_url = page.url
            parts.append(
                DynamicPagePart(
                    url=final_url,
                    title=page_title,
                    content=visible,
                    published_at=page_published_at,
                    updated_at=page_updated_at,
                )
            )
            next_url = str(data.get("nextUrl") or "")
            if not next_url or len(parts) >= self.limits.max_pages:
                current_url = None
                continue
            parsed_next = urlsplit(next_url)
            next_host = (parsed_next.hostname or "").casefold().rstrip(".")
            if next_host != initial_host or not _safe_document_url(next_url):
                current_url = None
                continue
            self.guard.validate_url(next_url)
            current_url = next_url

        content = _clean_visible_text(
            "\n\n".join(
                f"Page {index} ({part.url}) : {part.content}"
                for index, part in enumerate(parts, start=1)
            ),
            self.limits.max_characters,
        )
        return DynamicPageSnapshot(
            # L'URL principale reste celle de la page demandée. Chaque page
            # paginée possède sa propre provenance dans ``pages``.
            url=parts[0].url,
            title=title or "Page publique",
            content=content,
            page_count=len(parts),
            published_at=published_at,
            updated_at=updated_at,
            pages=tuple(parts),
        )

    def _remove_empty_runtime_root(self) -> None:
        """Retire le dossier de sessions lorsqu'aucune autre lecture ne l'utilise."""

        with contextlib.suppress(OSError):
            self.runtime_root.rmdir()


def _safe_document_url(url: str) -> bool:
    """Refuse les URL de téléchargement et actions sensibles avant toute navigation."""

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    path = parsed.path.casefold()
    if path.endswith(_DOWNLOAD_SUFFIXES):
        return False
    return _SENSITIVE_NAVIGATION.search(f"{path}?{parsed.query}") is None


def _clean_visible_text(value: str, limit: int) -> str:
    """Normalise le texte DOM sans conserver de page brute."""

    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned[:limit]


def _optional_text(value: object, limit: int) -> str | None:
    """Borne une métadonnée DOM facultative."""

    cleaned = _clean_visible_text(str(value or ""), limit)
    return cleaned or None


_EXTRACT_VISIBLE_PAGE_SCRIPT = r"""
() => {
  const meta = (names) => {
    for (const name of names) {
      const element = document.querySelector(`meta[property="${name}"], meta[name="${name}"]`);
      if (element?.content) return element.content;
    }
    return null;
  };
  const next = document.querySelector('a[rel~="next"]') ||
    [...document.querySelectorAll('a[href]')].find((link) =>
      /^(?:[←→‹›«»]\s*)?(next|suivant|page suivante|older|plus de résultats)(?:\s*[←→‹›«»])?$/i
        .test((link.textContent || '').trim())
    );
  const closedDetails = [...document.querySelectorAll('details:not([open])')]
    .map((element) => element.textContent || '')
    .join('\n');
  const downloadUrls = [...document.querySelectorAll('a[href]')]
    .map((element) => element.href || '')
    .filter((href) => /\.(?:7z|dmg|docx?|exe|iso|msi|pdf|pkg|rar|tar|zip)(?:[?#]|$)/i.test(href))
    .slice(0, 5);
  return {
    title: document.title || '',
    content: `${document.body?.innerText || ''}\n${closedDetails}`,
    nextUrl: next?.href || '',
    downloadUrls,
    publishedAt: meta(['article:published_time', 'datePublished', 'date']),
    updatedAt: meta(['article:modified_time', 'dateModified', 'last-modified']),
    blocked: Boolean(
      document.querySelector('input[type="password"], [id*="captcha" i], [class*="captcha" i]')
    ),
  };
}
"""
