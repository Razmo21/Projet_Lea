"""Validation visuelle réelle, API simulées : aucun accès aux données utilisateur.

Lancer Vite sur 127.0.0.1:5174 puis ce script avec le Python backend qui possède
Playwright. Edge utilise un contexte jetable, sans microphone physique ni modèle.
"""

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright, expect


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / ".test-runtime" / "stage17"
ORIGIN = "http://127.0.0.1:5174"
STAMP = "2026-11-01T14:00:00Z"
FIRST = "123e4567-e89b-42d3-a456-426614174000"
SECOND = "123e4567-e89b-42d3-a456-426614174001"
TEMPORARY = "123e4567-e89b-42d3-a456-426614174099"
PROGRAMMING = "123e4567-e89b-42d3-a456-426614174088"
WELCOME = (
    "Comment puis-je vous aider aujourd'hui ?", "Que puis-je faire pour vous ?",
    "Une question, une idée, un projet ?", "Qu'avez-vous en tête aujourd'hui ?",
    "Par quoi souhaitez-vous commencer ?", "Prêt à donner vie à vos idées ?",
)
ANSWER = '''## Une réponse structurée

**Bonjour**, voici un exemple de lecture avec une source réelle du jeu de test [S1].

| Profil | Usage | État |
| --- | --- | --- |
| Général | Échanger et comprendre | Disponible |
| Vétérinaire | Apprendre et raisonner | Disponible |

- Une idée principale
  - Un détail utile
- Une autre perspective

> Vérifier les informations importantes reste essentiel.

```python
print("bonjour")
```

`C:\\Users\\lea` · **été** · &amp; · \\*\\*bonjour\\*\\*

```typescript
const message: string = "bonjour";
```

```powershell
Get-ChildItem -LiteralPath 'C:\\Users\\lea'
```

![image distante](https://example.org/track)

<script>window.__injected = true</script>

[lien dangereux](javascript:alert%281%29)
'''


def conversation(identity, title, answer):
    """Crée un historique API représentatif dont le texte brut reste vérifiable."""
    value = dict(id=identity, title=title, title_origin="manual", created_at=STAMP,
                 updated_at=STAMP, revision=1, generation_active=False, message_count=2)
    source = dict(source_id="S1", title="Document public de test", url="https://example.org/document",
                  domain="example.org", snippet="", provider="direct", consulted_at=STAMP,
                  published_at="2025-02-01", updated_at=None, document_date=None,
                  retrieval_status="read", source_kind="html", limitations=None)
    value["messages"] = [dict(id=f"{identity}-{i}", conversation_id=identity, position=i,
                              role=role, content=text, status="completed", kind="conversation",
                              model_id="fixture", profile_id="general", web_sources=[source] if i else [],
                              error=None, created_at=STAMP, updated_at=STAMP)
                         for i, (role, text) in enumerate([("user", "Présente les possibilités de Léa."), ("assistant", answer)])]
    return value


class Fixtures:
    """Intercepte toutes les API avant le réseau et refuse toute autre destination."""

    def __init__(self):
        self.active = "general"
        self.core = "ready"
        self.core_failure = False
        self.instance = "fixture-instance"
        self.ephemeral = None
        self.calls = []
        self.unexpected = []
        self.external = []
        self.fail_delete = False
        self.fail_next_list = False
        self.waiting_web = asyncio.Event()
        self.waiting_message = asyncio.Event()
        self.waiting_message.set()
        self.cancelled_responses = set()
        self.resource_alert = ''
        self.conversations = {FIRST: conversation(FIRST, "Découvrir Léa", ANSWER),
                              SECOND: conversation(SECOND, "Notes de travail", "**Autre conversation**")}
        self.profiles = [dict(id=key, display_name=name, model_type="local", role=key, enabled=True,
                              display_order=i, context_tokens=16384, max_user_message_bytes=10000,
                              capabilities=["agent_runs", "workspace_projects"] if key == "development" else [])
                         for i, (key, name) in enumerate([("general", "Général"), ("veterinary", "Vétérinaire"), ("development", "Programmation")])]
        self.preferences = dict(revision=1, general_reasoning="low", general_reasoning_available=True,
                                veterinary_reasoning="high", veterinary_reasoning_available=True,
                                profile_settings=[dict(id=p["id"], display_name=p["display_name"], model_name="Modèle local", reasoning_available=p["id"] != "development") for p in self.profiles],
                                show_resource_chart=False, web_enabled=True, voice_microphone_id="",
                                voice_language="fr", voice_enabled=True, voice_id="lea_voice", voice_volume=1, voice_rate=1)
        self.run = dict(run_id="run-fixture", conversation_id=None, project_id="project-fixture", profile_id="development",
                        openhands_session_id=None, task="Tâche de test", state="failed", started_at=STAMP, finished_at=STAMP,
                        result_summary=None, checkpoint_id="checkpoint-fixture", created_at=STAMP, updated_at=STAMP,
                        validation_status="failed", failure_detail="Le test du projet a échoué.")
        self.runs = {self.run['run_id']: self.run}
        self.run_count = 0
        self.checkpoint = dict(checkpoint_id="checkpoint-fixture", run_id="run-fixture", project_id="project-fixture",
                               project_relative_path="Fixture", project_identity="test", state="completed")
        self.changes = [dict(relative_path="src/example.py", entry_type="file", change="modified")]

    def catalog(self):
        """Le changement de profil est autoritaire comme dans l'API réelle."""
        return dict(default_profile_id="general", active_profile_id=self.active, profiles=self.profiles)

    async def route(self, route):
        """Les fichiers Vite seuls passent ; aucune API ne rejoint le vrai contrôleur."""
        request = route.request
        url = urlparse(request.url)
        if url.hostname != "127.0.0.1" or url.port not in (5174, 8000):
            self.external.append(request.url)
            await route.abort()
            return
        if not url.path.startswith("/api/"):
            if url.port != 5174:
                self.unexpected.append(request.url)
                await route.abort()
            else:
                await route.continue_()
            return
        path = url.path
        if request.method == "OPTIONS":
            await route.fulfill(status=204, headers={"Access-Control-Allow-Origin": ORIGIN,
                                "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
                                "Access-Control-Allow-Headers": "Content-Type"})
            return
        self.calls.append((request.method, path, request.post_data))
        data = None
        status = 200
        body = request.post_data_json if request.post_data else {}
        if path.startswith("/api/core/"):
            if path.endswith("/start"): self.core = "ready"
            if path.endswith("/stop"): self.core = "stopped"
            data = dict(state=self.core, model=self.core, backend=self.core, message="Léa est prête." if self.core == "ready" else "Léa est arrêtée.")
            if self.core_failure:
                data.update(state="error", message="Le contrôleur local de Léa n’est pas disponible.")
                status = 503
        elif path == "/api/preferences":
            if body:
                self.preferences.update({key: val for key, val in body.items() if key != "expected_revision"})
                self.preferences["revision"] += 1
            data = self.preferences
        elif path == "/api/voice/status":
            data = dict(stt=True, tts=True, stt_engine="whisper.cpp", voices=[dict(id="lea_voice", label="Léa — Voix naturelle française", engine="pocket-tts", supports_rate=False), dict(id="siwis", label="SIWIS", engine="piper", supports_rate=True)])
        elif path == "/api/models": data = self.catalog()
        elif path == "/api/models/status":
            data = dict(state="ready", message="Profil prêt.", instance_id=self.instance, active_profile_id=self.active, loading_profile_id=None, generation_active=False, agent_run_active=False)
        elif path == "/api/ephemeral":
            self.ephemeral = conversation(TEMPORARY, "Chat éphémère", "")
            self.ephemeral.update(messages=[], message_count=0, revision=0, instance_id=self.instance)
            data = self.ephemeral
        elif path == f"/api/ephemeral/{TEMPORARY}" and request.method == "DELETE":
            self.ephemeral = None
            status, data = 204, {}
        elif path == f"/api/ephemeral/{TEMPORARY}/messages":
            await self.waiting_message.wait()
            if self.ephemeral is None:
                status, data = 410, dict(detail="Chat effacé.")
            elif request.headers.get('x-lea-response-id') in self.cancelled_responses:
                status, data = 409, dict(detail="La réponse a été interrompue.")
            else:
                pair = conversation(TEMPORARY, "Chat éphémère", "Réponse éphémère.")["messages"]
                pair[0]["content"] = body["message"]
                pair[1]["web_sources"] = []
                pair[0]["id"] += str(self.ephemeral["revision"])
                pair[1]["id"] += str(self.ephemeral["revision"])
                self.ephemeral["messages"].extend(pair)
                self.ephemeral["revision"] += 1
                data = self.ephemeral
        elif path.startswith("/api/models/") and path.endswith("/activate"):
            self.active = path.split("/")[3]
            data = dict(state="ready", message="Profil prêt.", active_profile_id=self.active,
                        loading_profile_id=None, generation_active=False, agent_run_active=False)
        elif path == "/api/resources":
            data = dict(active=True, stale=False, profile_id=self.active, sampled_at=1, level="WARNING" if self.resource_alert else "NORMAL", messages=[self.resource_alert] if self.resource_alert else [],
                        ram=dict(total_bytes=32*1024**3, used_bytes=10*1024**3, available_bytes=22*1024**3), vram=None, cpu_percent=3)
        elif path == "/api/conversations":
            query = parse_qs(url.query).get("search", [""])[0].casefold()
            data = dict(conversations=[{k:v for k,v in c.items() if k != "messages"} for c in self.conversations.values() if query in c["title"].casefold()])
            if self.fail_next_list:
                self.fail_next_list = False
                status, data = 503, dict(detail="Liste indisponible après envoi confirmé.")
        elif path == "/api/conversations/messages":
            await self.waiting_message.wait()
            if "web_request_id" in body:
                await self.waiting_web.wait()
                status, data = 400, dict(detail="Recherche Web annulée.")
            elif request.headers.get('x-lea-response-id') in self.cancelled_responses:
                target = body.get('conversation_id') or FIRST
                data = conversation(target, 'Échange interrompu', '')
                data['messages'] = data['messages'][:1]
                data['messages'][0].update(content=body['message'], status='failed', error='interrupted')
                self.conversations[target] = data
                status, data = 409, dict(detail='La réponse a été interrompue.', conversation=data)
            elif body["message"] == "provoquer erreur":
                status, data = 503, dict(detail="Modèle local indisponible pour cet essai.")
            elif body["message"] == "provoquer conflit":
                status, data = 409, dict(detail="Conflit de révision pour cet essai.",
                                         conversation=self.conversations[body["conversation_id"]])
            else:
                target = body.get("conversation_id") or FIRST
                self.conversations[target] = conversation(target, "Échange de test", "**Réponse reçue**")
                self.conversations[target]["messages"][0]["content"] = body["message"]
                data = self.conversations[target]
                if body["message"] == "échec liste":
                    self.fail_next_list = True
                if body["message"] == "échec enregistré":
                    data["messages"] = data["messages"][:1]
                    data["messages"][0]["status"] = "failed"
                    status, data = 503, dict(detail="Échec enregistré pour cet essai.", conversation=data)
        elif path.startswith('/api/responses/') and path.endswith('/cancel'):
            self.cancelled_responses.add(path.split('/')[3])
            self.waiting_message.set()
            self.waiting_web.set()
            data = dict(status='cancelling')
        elif path.startswith("/api/web/operations/") and path.endswith("/cancel"):
            self.waiting_web.set()
            data = dict(cancelled=True)
        elif path.startswith("/api/conversations/"):
            identity = path.split("/")[3]
            self.sync_run_messages()
            data = self.conversations[identity]
            if request.method == "PATCH":
                if "title" in body: data["title"] = body["title"]
                if "content" in body: data["messages"][0]["content"] = body["content"]
            elif request.method == "DELETE":
                if self.fail_delete:
                    status, data = 409, dict(detail="Conversation modifiée dans un autre onglet.")
                else:
                    del self.conversations[identity]
                    data = {}
        elif path.startswith("/api/projects"):
            data = dict(active_project_id="project-fixture", projects=[dict(id="project-fixture", name="Projet de test", relative_path="Fixture", created_at=STAMP, updated_at=STAMP, active=True)])
        elif path == "/api/agent-runs":
            data = dict(runs=list(reversed(list(self.runs.values()))))
            if request.method == "POST":
                assert body['record_conversation'] is True
                assert body['expected_profile_id'] == 'development'
                assert body['expected_project_id'] == 'project-fixture'
                self.run_count += 1
                identity = body.get('conversation_id') or PROGRAMMING
                if identity not in self.conversations:
                    self.conversations[identity] = conversation(identity, 'Tâche de programmation', '')
                    self.conversations[identity]['messages'] = []
                    self.conversations[identity]['revision'] = 0
                history = self.conversations[identity]
                history['has_agent_runs'] = True
                if body.get('conversation_id'):
                    assert body['expected_revision'] == history['revision']
                self.run = dict(self.run, run_id=f'run-fixture-{self.run_count}', task=body['task'],
                                conversation_id=identity, state='running', validation_status='pending',
                                result_summary=None, failure_detail=None, finished_at=None)
                self.runs[self.run['run_id']] = self.run
                pair = conversation(identity, 'Tâche', 'Run en cours')['messages']
                pair[0]['content'] = body['task']
                for message in pair:
                    message.update(id=message['id'] + f'-run-{self.run_count}', profile_id='development',
                                   agent_run_id=self.run['run_id'], web_sources=[])
                history['messages'].extend(pair)
                history.update(revision=history['revision'] + 1, generation_active=True,
                               message_count=len(history['messages']))
                self.checkpoint.update(state='completed', run_id=self.run['run_id'])
                data = self.run
        elif path.endswith("/changes"):
            data = dict(run_id=self.run["run_id"], checkpoint=self.checkpoint, changes=self.changes)
        elif path.startswith("/api/agent-runs/"):
            if path.endswith("/cancel"):
                self.run.update(state="cancelled", validation_status="failed", finished_at=STAMP)
                self.sync_run_messages()
            if path.endswith("/rollback"): self.checkpoint["state"] = "rolled_back"
            if path.endswith("/accept"): self.checkpoint["state"] = "accepted"
            data = self.runs[path.split('/')[3]]
        else:
            self.unexpected.append(path)
            status, data = 404, dict(detail="Route non prévue par le test")
        await route.fulfill(status=status, content_type="application/json", body=json.dumps(data), headers={"Access-Control-Allow-Origin": ORIGIN})

    def sync_run_messages(self):
        """Imite la mise à jour atomique du tour après terminaison, sans nouveau message."""
        for run in self.runs.values():
            history = self.conversations.get(run['conversation_id'])
            if not history or run['state'] in ('running', 'pending', 'waiting_for_tool'):
                continue
            for message in history['messages']:
                if message.get('agent_run_id') == run['run_id'] and message['role'] == 'assistant':
                    content = run['result_summary'] or run['failure_detail'] or 'Tâche annulée.'
                    if message['content'] != content:
                        message['content'] = content
                        history.update(revision=history['revision'] + 1, generation_active=False)


async def check_composer_height(page, text, lines, scrollable=False):
    """Mesure les lignes réelles dans Edge et vérifie le défilement après la limite."""
    field = page.locator("#question")
    await field.fill(text)
    metrics = await field.evaluate("""el => {
        const style = getComputedStyle(el);
        return {
            height: el.getBoundingClientRect().height,
            line: parseFloat(style.lineHeight),
            inset: parseFloat(style.paddingTop) + parseFloat(style.paddingBottom)
                + parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth),
            scrollHeight: el.scrollHeight, clientHeight: el.clientHeight,
            overflow: style.overflowY,
            scrollbar: style.scrollbarWidth,
            scrollbarColor: style.scrollbarColor,
            webkitScrollbar: getComputedStyle(el, '::-webkit-scrollbar').width,
        };
    }""")
    assert abs(metrics["height"] - (lines * metrics["line"] + metrics["inset"])) <= 1, metrics
    if scrollable:
        assert metrics['scrollbar'] == 'thin', metrics
        assert metrics['scrollbarColor'] != 'auto', metrics
        assert metrics['webkitScrollbar'] == '3px', metrics
        assert metrics["scrollHeight"] > metrics["clientHeight"] and metrics["overflow"] == "auto", metrics
        assert await field.evaluate("el => { el.scrollTop = el.scrollHeight; return el.scrollTop > 0; }")
    else:
        assert metrics["overflow"] == "hidden", metrics


async def check_composer_spacing(page):
    """La commande principale alterne sans déplacement ni doublon ; la dictée reste distincte."""
    field = page.locator('#question')
    draft = await field.input_value()
    measured = []
    for text, name, absent in [('', 'Conversation vocale', 'Envoyer'), ('Bonjour', 'Envoyer', 'Conversation vocale')]:
        await field.fill(text)
        command = page.get_by_role('button', name=name, exact=True)
        await expect(command).to_be_visible()
        await expect(command).to_have_attribute('title', name)
        await expect(page.get_by_role('button', name=absent, exact=True)).to_have_count(0)
        microphone = await page.get_by_role('button', name='Dictée', exact=True).bounding_box()
        box = await command.bounding_box()
        field_box = await field.bounding_box()
        assert abs(box['x'] - microphone['x'] - microphone['width'] - 8) < 0.5
        assert abs(box['y'] - microphone['y']) < 1
        # Le rail de défilement reste à droite des commandes, sans passer dessous.
        assert 15 <= field_box['x'] + field_box['width'] - box['x'] - box['width'] <= 24
        measured.append(box)
    assert all(abs(measured[0][key] - measured[1][key]) < 1 for key in ('x', 'y', 'width', 'height')), measured
    await field.fill(draft)


async def check_theme_contrast(page):
    """Contrôle les contrastes de texte des surfaces et des commandes dans le thème réel."""
    ratios = await page.evaluate("""() => {
        const style = getComputedStyle(document.documentElement);
        const color = name => style.getPropertyValue('--' + name).trim();
        const luminance = value => {
            const rgb = value.startsWith('#')
                ? [1, 3, 5].map(start => parseInt(value.slice(start, start + 2), 16))
                : value.match(/[\\d.]+/g).slice(0, 3).map(Number);
            const linear = rgb.map(n => n / 255).map(n => n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4);
            return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
        };
        const contrast = (a, b) => {
            const [bright, dark] = [luminance(a), luminance(b)].sort((a, b) => b - a);
            return (bright + 0.05) / (dark + 0.05);
        };
        const result = {};
        for (const background of ['canvas', 'sidebar', 'surface', 'soft', 'hover', 'code']) {
            for (const foreground of ['text', 'muted']) {
                result[foreground + '/' + background] = contrast(color(foreground), color(background));
            }
        }
        for (const foreground of ['accent', 'error', 'warning', 'success']) {
            result[foreground + '/surface'] = contrast(color(foreground), color('surface'));
        }
        result['button'] = contrast(color('on-accent'), color('accent'));
        const option = getComputedStyle(document.querySelector('#model-profile option'));
        result['option'] = contrast(option.color, option.backgroundColor);
        return result;
    }""")
    assert all(ratio >= 4.5 for ratio in ratios.values()), ratios
    return min(ratios.values())


async def main():
    """Vérifie les flux visibles, produit des captures et ferme Edge même sur échec."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    checked = []
    fixture = Fixtures()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        try:
            context = await browser.new_context(viewport=dict(width=1440, height=1000), color_scheme="light", reduced_motion="reduce")
            await context.route("**/*", fixture.route)
            await context.add_init_script("""window.__copies = []; Object.defineProperty(navigator, 'clipboard', { value: { writeText: async text => window.__copies.push(text) } });
                navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Test refusal', 'NotAllowedError'); };""")
            page = await context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(ORIGIN)
            await expect(page.locator("#model-profile")).to_have_value("general")
            assert await page.locator(".welcome").inner_text() in WELCOME
            welcome = await page.locator(".welcome").bounding_box()
            viewport = await page.locator(".chat-scroll").bounding_box()
            assert abs(welcome["y"] + welcome["height"] / 2 - viewport["y"] - viewport["height"] / 2) < 2
            assert abs(welcome["x"] + welcome["width"] / 2 - viewport["x"] - viewport["width"] / 2) < 10
            await expect(page.locator(".welcome img, .welcome p, .welcome small, .chat-topbar h1")).to_have_count(0)
            await expect(page.locator(".sidebar-brand h1")).to_have_css("font-size", "20px")
            await expect(page.locator(".sidebar-caption")).to_have_css("font-size", "14px")
            assert "personnelle" not in await page.locator(".sidebar-brand").inner_text()
            assert "locale" not in await page.locator(".sidebar-brand").inner_text()
            await expect(page.locator(".sidebar-caption")).to_have_text("Conversations")
            await expect(page.get_by_text("Vos échanges restent sur ce PC.", exact=True)).to_have_count(0)
            await expect(page.get_by_role("button", name=re.compile("Afficher les conversations|Fermer la barre latérale|Fermer les conversations"))).to_have_count(0)
            await expect(page.locator(".brand-mark")).to_have_attribute("src", "/lea-logo.png")
            await expect(page.locator(".brand-mark")).to_have_js_property("naturalWidth", 1254)
            await expect(page.locator("link[rel='icon']")).to_have_attribute("href", "/lea-logo.png")
            await expect(page.locator(".sidebar-footer").get_by_role("button", name="Démarrer", exact=True)).to_be_disabled()
            await expect(page.locator(".sidebar-footer").get_by_role("button", name="Arrêter", exact=True)).to_be_enabled()
            await expect(page.locator('.sidebar-footer p')).to_have_count(0)
            await expect(page.locator('.core-status')).to_have_count(0)
            commands = [page.get_by_role("button", name=name, exact=True) for name in
                        ("Dictée", "Conversation vocale")]
            bounds = [await command.bounding_box() for command in commands]
            assert all(bounds) and bounds[0]["x"] < bounds[1]["x"]
            assert max(b["y"] for b in bounds) - min(b["y"] for b in bounds) <= 1
            for command in commands:
                assert await command.inner_text() == ""
                await expect(command).to_have_attribute("title", re.compile('.+'))
            await expect(commands[0]).to_have_attribute("title", "Dictée")
            await expect(commands[1]).to_have_attribute("title", "Conversation vocale")
            await check_composer_spacing(page)
            # Entrée sans texte ne doit ni envoyer un tour ni ouvrir la voix.
            sends_before = sum(path == '/api/conversations/messages' for _, path, _ in fixture.calls)
            await page.locator('#question').fill('   ')
            await expect(page.get_by_role('button', name='Conversation vocale', exact=True)).to_be_visible()
            await page.locator('#question').press('Enter')
            await expect(page.get_by_role('heading', name='Conversation vocale')).to_have_count(0)
            assert sum(path == '/api/conversations/messages' for _, path, _ in fixture.calls) == sends_before
            await page.locator('#question').fill('')
            light_contrast = await check_theme_contrast(page)
            checked.append("Commande vocale/envoi unique selon le brouillon, dictée distincte et libellés accessibles")
            settings_box = await page.get_by_role('button', name='Paramètres', exact=True).bounding_box()
            temporary_box = await page.locator('.chat-topbar .ephemeral-toggle').bounding_box()
            chat_box = await page.locator('.chat-topbar').bounding_box()
            assert temporary_box['width'] == settings_box['width'] and temporary_box['height'] == settings_box['height']
            assert chat_box['x'] <= temporary_box['x'] <= chat_box['x'] + 25
            assert chat_box['y'] <= temporary_box['y'] < chat_box['y'] + chat_box['height']
            await expect(page.locator('.chat-footer .ephemeral-toggle')).to_have_count(0)
            await page.screenshot(path=OUTPUT / "welcome-light.png")
            checked.append("Démarrage de l'interface et accueil")

            # Le titre reste fixe au repos et change seulement lors d'un nouvel accueil.
            initial_title = await page.locator('.welcome').inner_text()
            await page.clock.install()
            await page.clock.fast_forward(35000)
            await expect(page.locator('.welcome')).to_have_text(initial_title)
            await page.get_by_role('button', name='Nouvelle conversation', exact=True).click()
            assert await page.locator('.welcome').inner_text() in WELCOME
            assert await page.locator('.welcome').inner_text() != initial_title
            new_title = await page.locator('.welcome').inner_text()
            settings_toggle = page.get_by_role('button', name='Paramètres', exact=True)
            await settings_toggle.click()
            await expect(page.locator('.settings')).to_be_visible()
            await settings_toggle.click()
            await expect(page.locator('.settings')).to_have_count(0)
            await expect(settings_toggle).to_be_focused()
            assert await page.locator('.welcome').inner_text() != new_title
            await page.clock.resume()
            checked.append('Accueil centré, titre fixe au repos et renouvelé à la navigation')

            # Aucun texte temporaire ne doit emprunter l'API normale ni le stockage navigateur.
            await page.locator('#question').fill('Brouillon normal privé du test')
            normal_posts = sum(path == '/api/conversations/messages' for _, path, _ in fixture.calls)
            temporary = page.get_by_role('button', name='Chat éphémère', exact=True)
            await temporary.click()
            await expect(page.locator('.welcome')).to_have_text('Chat éphémère')
            await expect(page.locator('#question')).to_have_value('')
            await expect(page.locator('#model-profile')).to_be_disabled()
            await expect(page.get_by_role('button', name='Nouvelle conversation', exact=True)).to_be_disabled()
            await page.locator('#question').fill('SECRET-EPHEMERE-TEST')
            await page.locator('#question').press('Enter')
            await expect(page.locator('.message-assistant')).to_contain_text('Réponse éphémère.')
            fixture.waiting_message.clear()
            await page.locator('#question').fill('Réponse temporaire à interrompre')
            await page.locator('#question').press('Enter')
            await page.get_by_role('button', name='Arrêter la réponse', exact=True).click()
            await expect(page.get_by_role('button', name='Conversation vocale', exact=True)).to_be_visible()
            await expect(page.locator('#question')).to_have_value('')
            await expect(page.locator('.message-user')).to_have_count(1)
            await expect(page.locator('.message-user')).to_contain_text('SECRET-EPHEMERE-TEST')
            await expect(page.get_by_role('button', name='Quitter le chat éphémère', exact=True)).to_be_visible()
            checked.append('Arrêt éphémère sans fermeture de session ni perte des échanges précédents')
            assert sum(path == '/api/conversations/messages' for _, path, _ in fixture.calls) == normal_posts
            assert 'SECRET-EPHEMERE' not in await page.evaluate('JSON.stringify(localStorage) + JSON.stringify(sessionStorage)')
            assert TEMPORARY not in page.url
            await page.screenshot(path=OUTPUT / 'ephemeral-light.png')
            await page.get_by_role('button', name='Quitter le chat éphémère', exact=True).click()
            await expect(page.locator('#question')).to_have_value('Brouillon normal privé du test')
            await expect(page.locator('.message')).to_have_count(0)
            assert fixture.ephemeral is None
            # Une fermeture pendant une réponse vide aussi la bulle d'attente et le brouillon privé.
            await temporary.click()
            fixture.waiting_message.clear()
            await page.locator('#question').fill('SECRET EN ATTENTE')
            await page.locator('#question').press('Enter')
            await expect(page.locator('.message-pending')).to_contain_text('SECRET EN ATTENTE')
            await page.get_by_role('button', name='Quitter le chat éphémère', exact=True).click()
            await expect(page.locator('#question')).to_have_value('Brouillon normal privé du test')
            await expect(page.locator('.message-pending')).to_have_count(0)
            fixture.waiting_message.set()
            assert fixture.ephemeral is None
            await temporary.click()
            fixture.instance = 'fixture-restarted'
            await expect(temporary).to_be_visible(timeout=12000)
            await expect(page.locator('.welcome')).not_to_have_text('Chat éphémère')
            await expect(page.locator('#question')).to_have_value('Brouillon normal privé du test')
            fixture.ephemeral = None
            await temporary.click()
            await page.reload()
            await expect(page.locator('#model-profile')).to_have_value('general')
            await expect(temporary).to_be_visible()
            await expect(page.locator('.welcome')).not_to_have_text('Chat éphémère')
            await expect(page.locator('#question')).to_have_value('')
            checked.append('Chat éphémère : route dédiée, aucun stockage navigateur, sortie/rechargement/redémarrage sans texte privé')

            await check_composer_height(page, "", 1)
            await check_composer_height(page, "Une ligne", 1)
            await check_composer_height(page, "Première\nDeuxième", 2)
            await check_composer_height(page, "\n".join(["ligne"] * 4), 4)
            await check_composer_height(page, "\n".join(["ligne"] * 5), 4, scrollable=True)
            await check_composer_height(page, "Texte replié automatiquement. " * 60, 4, scrollable=True)
            await page.screenshot(path=OUTPUT / "composer-scroll-light.png")
            await check_composer_height(page, "Deux\nlignes", 2)
            await check_composer_height(page, "", 1)
            checked.append("Saisie de une à quatre lignes, texte replié, défilement interne et retour à une ligne")

            row = [page.locator(".composer-add"), page.locator("#question"), *commands]
            bounds = [await item.bounding_box() for item in row]
            assert all(bounds)
            add_box, field_box, dictation_box, primary_box = bounds
            assert add_box["x"] + add_box["width"] <= field_box["x"] + 1
            assert field_box["x"] < dictation_box["x"] < primary_box["x"]
            assert primary_box["x"] + primary_box["width"] < field_box["x"] + field_box["width"]
            centers = [b["y"] + b["height"] / 2 for b in bounds]
            assert max(centers) - min(centers) <= 1, bounds
            assert (await page.locator(".composer").bounding_box())["height"] <= 60
            await expect(page.locator(".chat-topbar button[aria-label='Paramètres'], .chat-topbar button[aria-label='Nouvelle conversation']")).to_have_count(0)
            brand = await page.locator(".sidebar-brand h1").bounding_box()
            settings = await page.locator(".sidebar-brand button").bounding_box()
            assert settings["x"] >= brand["x"] + brand["width"]
            select = await page.locator("#model-profile").bounding_box()
            topbar = await page.locator(".chat-topbar").bounding_box()
            assert topbar["x"] + topbar["width"] - select["x"] - select["width"] <= 25
            await expect(page.locator(".model-profile-status")).to_have_text("Modèle prêt")
            checked.append("Logo local chargé, barre permanente, paramètres en haut et commandes du cœur en bas")

            await page.locator(".conversation-summary").filter(has_text="Découvrir Léa").click()
            await expect(page.locator(".markdown-content h2")).to_have_text("Une réponse structurée")
            await expect(page.locator(".markdown-content table")).to_be_visible()
            assistant = page.locator(".message-assistant").first
            assert await assistant.evaluate(
                "el => getComputedStyle(el).backgroundColor !== getComputedStyle(document.documentElement).backgroundColor"
            )
            assert await assistant.evaluate("el => parseFloat(getComputedStyle(el).paddingLeft) > 0")
            assert await page.locator(".markdown-content img, .markdown-content script").count() == 0
            assert await page.evaluate("window.__injected") is None
            await page.locator(".message-sources summary").click()
            await expect(page.get_by_role("link", name="[S1] Document public de test")).to_have_attribute("href", "https://example.org/document")
            await page.locator(".code-block").first.get_by_role("button", name="Copier le code").click()
            assert await page.evaluate("window.__copies.at(-1)") == 'print("bonjour")\n'
            await page.locator(".message-assistant").get_by_role("button", name="Copier", exact=True).click()
            assert await page.evaluate("window.__copies.at(-1)") == ANSWER
            checked.append("Markdown, littéraux, code copié, copie brute, sources et contenu hostile")

            await page.locator("#question").fill("Brouillon de nouvelle conversation")
            await expect(page.locator(".composer-add")).to_be_disabled()
            mutations_before = sum(method != "GET" for method, _, _ in fixture.calls)
            await page.locator(".composer-add").evaluate("el => el.click()")
            await expect(page.locator("#question")).to_have_value("Brouillon de nouvelle conversation")
            await expect(page.locator(".conversation-header")).to_have_count(0)
            await expect(page.locator(".conversation-summary[aria-current='page']")).to_contain_text("Découvrir Léa")
            assert sum(method != "GET" for method, _, _ in fixture.calls) == mutations_before
            await expect(page.locator("input[type='file']")).to_have_count(0)
            await page.get_by_role("button", name="Nouvelle conversation", exact=True).click()
            await expect(page.locator(".welcome")).to_be_visible()
            await expect(page.locator("#question")).to_have_value("")
            await expect(page.locator("#question")).to_be_focused()
            await page.locator(".conversation-summary").filter(has_text="Découvrir Léa").click()
            await expect(page.locator(".markdown-content h2")).to_be_visible()

            await page.reload()
            await expect(page.locator(".markdown-content h2")).to_have_text("Une réponse structurée")
            await page.locator(".conversation-summary").filter(has_text="Notes de travail").click()
            await expect(page.locator(".message-assistant strong").last).to_have_text("Autre conversation")
            await page.locator(".conversation-summary").filter(has_text="Découvrir Léa").click()
            await page.locator("#conversation-search").fill("Notes")
            await expect(page.locator(".conversation-summary")).to_have_count(1)
            await page.locator("#conversation-search").fill("")
            await expect(page.locator(".conversation-summary")).to_have_count(2)
            checked.append("Rechargement, sélection, recherche et changement de conversation")

            await page.locator("#question").fill("Brouillon conservé")
            await page.get_by_role("button", name="Paramètres", exact=True).click()
            await expect(page.get_by_role("heading", name="Paramètres de Léa")).to_be_visible()
            await expect(page.locator("#conversation-sidebar")).to_be_visible()
            await page.get_by_label("Sombre", exact=True).check()
            await expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            await page.get_by_label("Afficher le diagramme des ressources").check()
            await page.locator("fieldset").filter(has=page.get_by_text("Général — Raisonnement", exact=True)).get_by_label("High — Réflexion").check()
            page.once("dialog", lambda dialog: dialog.dismiss())
            await page.get_by_role("button", name="Paramètres", exact=True).click()
            await expect(page.locator(".settings")).to_be_visible()
            cards = page.locator(".settings-form > .settings-group")
            await expect(cards).to_have_count(5)
            await expect(page.get_by_role("heading", name="Programmation", exact=True)).to_have_count(0)
            general_box, veterinary_box, voice_box = [
                await cards.nth(index).bounding_box() for index in (0, 1, 4)
            ]
            assert abs(general_box["y"] - veterinary_box["y"]) < 1
            assert voice_box["width"] > general_box["width"] * 1.8
            await expect(page.get_by_role("region", name="Entrée vocale")).to_be_visible()
            await expect(page.get_by_role("region", name="Lecture des réponses")).to_be_visible()
            save_button = page.get_by_role("button", name="Valider", exact=True)
            save_box = await save_button.bounding_box()
            form_box = await page.locator(".settings-form").bounding_box()
            assert abs(
                save_box["x"] + save_box["width"] / 2
                - (form_box["x"] + form_box["width"] / 2)
            ) < 1
            await page.get_by_role("button", name="Valider", exact=True).click()
            await expect(page.get_by_text("Paramètres enregistrés.", exact=False)).to_be_visible()
            settings_box = await page.locator(".settings").bounding_box()
            main_box = await page.locator(".main-pane").bounding_box()
            assert abs((settings_box["x"] + settings_box["width"]) - (main_box["x"] + main_box["width"])) < 1
            assert await page.locator(".settings").evaluate("el => el.scrollHeight > el.clientHeight")
            await page.screenshot(path=OUTPUT / "settings-dark.png")
            await page.get_by_role("button", name="Retour aux conversations").click()
            await expect(page.get_by_role("region", name="Diagramme des ressources")).to_be_visible()
            await expect(page.get_by_role("heading", name="Ressources", exact=True)).to_have_count(0)
            resources_box = await page.locator(".resources").bounding_box()
            main_box = await page.locator(".main-pane").bounding_box()
            assert resources_box["x"] >= main_box["x"]
            assert resources_box["x"] + resources_box["width"] <= main_box["x"] + main_box["width"] + 1
            sidebar_footer = await page.locator('.sidebar-footer').bounding_box()
            assert abs(resources_box['y'] - sidebar_footer['y']) < 1
            assert await page.locator('.chat-topbar').evaluate("""el => {
                const top = getComputedStyle(el);
                const bottom = getComputedStyle(document.querySelector('.resources'));
                return top.borderBottomWidth === '1px'
                    && top.borderBottomStyle === bottom.borderTopStyle
                    && top.borderBottomColor === bottom.borderTopColor;
            }""")
            fixture.resource_alert = 'RAM disponible faible.'
            notice = page.locator('.chat-topbar .resource-notice')
            await expect(notice).to_have_text('RAM disponible faible', timeout=12000)
            notice_box = await notice.bounding_box()
            top_box = await page.locator('.chat-topbar').bounding_box()
            assert abs(notice_box['x'] + notice_box['width']/2 - top_box['x'] - top_box['width']/2) < 1
            await expect(page.locator('.resources .resource-notice')).to_have_count(0)
            await page.screenshot(path=OUTPUT / 'resource-warning-top.png')
            fixture.resource_alert = 'Docker est indisponible ; ouvre Docker Desktop manuellement.'
            await expect(notice).to_have_text('Ouvrez Docker Desktop', timeout=12000)
            assert ';' not in await notice.inner_text()
            checked.append('Avertissement long remplacé par une phrase courte sans point-virgule')
            fixture.resource_alert = ''
            await expect(notice).to_have_count(0, timeout=12000)
            checked.append('Alertes des ressources centrées dans le bandeau supérieur, collecte unique')
            await expect(page.locator(".resource-row").filter(has_text="VRAM")).to_contain_text("Indisponible")
            await expect(page.locator("#question")).to_have_value("Brouillon conservé")
            await expect(page.get_by_role("button", name="Paramètres", exact=True)).to_be_focused()
            await page.reload()
            await expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            await expect(page.locator(".markdown-content h2")).to_be_visible()
            assert await page.locator("#model-profile option").evaluate_all("""options => options.every(option => {
                const style = getComputedStyle(option);
                const root = getComputedStyle(document.documentElement);
                return style.backgroundColor === getComputedStyle(document.querySelector('#model-profile')).backgroundColor
                    && style.color !== style.backgroundColor && root.colorScheme === 'dark';
            })""")
            dark_contrast = await check_theme_contrast(page)
            checked.append("Palette du logo : contrastes du texte, états, boutons et menu vérifiés dans les deux thèmes")
            await page.locator(".chat-scroll").evaluate("el => el.scrollTop = 0")
            await page.screenshot(path=OUTPUT / "conversation-dark.png")
            checked.append("Paramètres, Low/High, sauvegarde, brouillon, thème persistant et focus")

            await page.keyboard.press("Escape")
            await expect(page.locator("#conversation-sidebar")).to_be_visible()
            await page.locator("#model-profile").select_option("veterinary")
            await expect(page.locator("#model-profile")).to_have_value("veterinary")
            await expect(page.locator(".model-profile-status")).to_have_text("Modèle prêt")
            await expect(page.locator(".model-selector [role='alert']")).to_have_count(0)
            await page.locator("#question").fill("Bonjour")
            sends_before = sum(path == "/api/conversations/messages" for _, path, _ in fixture.calls)
            await page.locator("#question").press("Shift+Enter")
            await page.locator("#question").press_sequentially("suite")
            await expect(page.locator("#question")).to_have_value("Bonjour\nsuite")
            await page.locator("#question").dispatch_event("keydown", {"key": "Enter", "isComposing": True})
            await page.locator("#question").dispatch_event("keydown", {"key": "Enter", "repeat": True})
            await page.wait_for_timeout(100)
            assert sum(path == "/api/conversations/messages" for _, path, _ in fixture.calls) == sends_before
            fixture.waiting_message.clear()
            await page.locator("#question").press("Enter")
            await expect(page.locator("#question")).to_have_value("")
            await expect(page.locator(".message-pending")).to_have_count(1)
            await expect(page.locator(".message-pending")).to_contain_text("Bonjour")
            await expect(page.locator(".conversation-pending")).to_have_text("Léa répond…")
            await expect(page.locator(".composer-add")).to_be_disabled()
            await page.screenshot(path=OUTPUT / "sending-dark.png")
            fixture.waiting_message.set()
            await expect(page.get_by_text("Réponse reçue", exact=True)).to_be_visible()
            sent = [json.loads(body) for method, path, body in fixture.calls if path == "/api/conversations/messages"][-1]
            assert "web_request_id" not in sent
            assert sent["message"] == "Bonjour\nsuite"
            checked.append("Entrée envoie, Maj+Entrée conserve une ligne, composition et répétition sans envoi")
            await expect(page.locator("#question")).to_have_value("")
            await expect(page.get_by_role("button", name="Régénérer", exact=True)).to_have_count(0)
            checked.append("Champ vidé pendant la réponse, profil Vétérinaire et absence de Régénérer")

            for profile in ('general', 'veterinary'):
                await page.locator('#model-profile').select_option(profile)
                await expect(page.locator('.model-profile-status')).to_have_text('Modèle prêt')
                await page.get_by_role('button', name='Nouvelle conversation', exact=True).click()
                if profile == 'veterinary':
                    assert await page.locator('.welcome').inner_text() in (
                        'Quel sujet vétérinaire souhaitez-vous explorer ?',
                        'Un cas clinique à étudier ensemble ?',
                        'Quelle espèce vous intéresse aujourd’hui ?',
                        'Une question de soins ou de santé animale ?',
                        'Quelle notion vétérinaire souhaitez-vous approfondir ?',
                    )
                fixture.waiting_message.clear()
                await page.locator('#question').fill('Interrompre cette réponse')
                await page.locator('#question').press('Enter')
                await expect(page.get_by_role('button', name='Arrêter la réponse', exact=True)).to_be_enabled()
                await page.get_by_role('button', name='Arrêter la réponse', exact=True).click()
                await expect(page.get_by_role('button', name='Conversation vocale', exact=True)).to_be_visible()
                await expect(page.locator('#question')).to_have_value('')
                await expect(page.locator('.message-user')).to_have_count(1)
                await page.locator('#question').fill('Nouvelle question après arrêt')
                await page.locator('#question').press('Enter')
                await expect(page.get_by_text('Réponse reçue', exact=True)).to_be_visible()
            checked.append('Arrêt Général/Vétérinaire, historique cohérent, nouvelle réponse et accueil spécialisé')

            # Les arrêts précédents ont libéré cet événement partagé par la fixture.
            # La recherche suivante attend sa propre annulation, comme une requête réelle.
            fixture.waiting_web.clear()
            await page.locator("#question").fill("Cherche sur Internet une documentation publique")
            await page.get_by_role("button", name="Envoyer", exact=True).click()
            await expect(page.get_by_role("button", name="Arrêter la réponse", exact=True)).to_be_enabled()
            await expect(page.locator("#question")).to_be_disabled()
            await page.get_by_role("button", name="Arrêter la réponse").click()
            await expect(page.get_by_role("alert").filter(has_text="Recherche Web annulée")).to_be_visible()
            await page.locator("#question").fill("provoquer erreur")
            await page.get_by_role("button", name="Envoyer", exact=True).click()
            await expect(page.get_by_role("alert").filter(has_text="Modèle local indisponible")).to_be_visible()
            await expect(page.locator("#question")).to_have_value("provoquer erreur")
            await page.locator("#question").fill("provoquer conflit")
            await page.get_by_role("button", name="Envoyer", exact=True).click()
            await expect(page.get_by_role("alert").filter(has_text="Conflit de révision")).to_be_visible()
            await expect(page.locator("#question")).to_have_value("provoquer conflit")
            await page.locator("#question").fill("échec enregistré")
            await page.get_by_role("button", name="Envoyer", exact=True).click()
            await expect(page.get_by_role("alert").filter(has_text="Échec enregistré")).to_be_visible()
            await expect(page.locator("#question")).to_have_value("")
            await expect(page.locator(".message-user")).to_contain_text("échec enregistré")
            await page.locator("#question").fill("échec liste")
            await page.get_by_role("button", name="Envoyer", exact=True).click()
            await expect(page.get_by_role("alert").filter(has_text="Liste indisponible après envoi confirmé")).to_be_visible()
            await expect(page.locator("#question")).to_have_value("")
            await expect(page.locator(".message-user")).to_contain_text("échec liste")
            checked.append("Erreur sans tour enregistré et conflit : brouillon restauré ; échec enregistré : pas de doublon")
            checked.append("Annulation Web et erreurs explicites")

            await page.get_by_role("button", name="Conversation vocale", exact=True).click()
            await expect(page.get_by_role("heading", name="Conversation vocale")).to_be_visible()
            await expect(page.locator("#conversation-sidebar")).to_be_visible()
            await expect(page.get_by_role("heading", name="Conversation vocale")).to_be_focused()
            await expect(page.locator(".chat-topbar")).to_be_hidden()
            await page.screenshot(path=OUTPUT / "voice-dark.png")
            await page.get_by_role("button", name="Retour aux conversations").click()
            await expect(page.get_by_role("button", name="Conversation vocale", exact=True)).to_be_focused()
            await page.get_by_role("button", name="Dictée", exact=True).click()
            await expect(page.locator(".voice-controls [role='status']").last).to_contain_text("refus")
            assert not any(path == "/api/voice/transcribe" for _, path, _ in fixture.calls)
            checked.append("Vue vocale et refus du microphone simulé sans envoi")

            await page.locator("#model-profile").select_option("development")
            await expect(page.locator(".model-profile-status")).to_have_text("Modèle prêt")
            await expect(page.locator("#agent-task")).to_have_count(0)
            await expect(page.get_by_text("Validation de la tâche échouée", exact=True)).to_have_count(0)
            await expect(page.locator('.agent-result')).to_contain_text('La tâche a échoué')
            await expect(page.locator('.agent-result')).to_contain_text('Le test du projet a échoué')
            await expect(page.get_by_role("button", name="Accepter les changements")).to_have_count(0)
            await expect(page.get_by_role("button", name="Restaurer le checkpoint")).to_be_visible()
            await page.get_by_role("button", name="Restaurer le checkpoint").click()
            await expect(page.locator(".agent-changes")).to_have_count(0)
            await expect(page.locator('.agent-result')).to_contain_text('Fichiers restaurés au checkpoint.')
            fixture.checkpoint["state"] = "completed"
            await page.get_by_role('button', name='Nouvelle conversation', exact=True).click()
            task = "Modifie mon code et cherche sur Internet si tu ne sais pas."
            await page.locator("#question").fill(task)
            await expect(page.locator(".web-note")).to_have_count(0)
            await expect(page.locator(".welcome")).to_be_visible()
            assert await page.locator('.welcome').inner_text() in (
                'Quel projet allons-nous faire avancer ?',
                'Un bug à corriger, une idée à coder ?',
                'Quelle fonctionnalité souhaitez-vous créer ?',
                'Quel code souhaitez-vous explorer ?',
                'Quelle tâche puis-je réaliser dans votre projet ?',
            )
            center = await page.locator('.welcome').bounding_box()
            space = await page.locator('.chat-scroll').bounding_box()
            assert abs(center['y'] + center['height']/2 - space['y'] - space['height']/2) < 2
            assert (await page.locator('.project-controls').bounding_box())['height'] < 95
            await expect(page.get_by_role("button", name="Démarrer la tâche", exact=True)).to_have_count(0)
            sends_before = sum(path == "/api/conversations/messages" for _, path, _ in fixture.calls)
            await page.get_by_role("button", name="Envoyer", exact=True).click()
            await expect(page.locator("#question")).to_have_value("")
            assert sum(path == "/api/conversations/messages" for _, path, _ in fixture.calls) == sends_before
            run_posts = [
                body for method, path, body in fixture.calls
                if method == "POST" and path == "/api/agent-runs"
            ]
            assert json.loads(run_posts[-1])["task"] == task
            assert json.loads(run_posts[-1])['record_conversation'] is True
            await expect(page.locator('.message-user').filter(has_text=task)).to_have_count(1)
            await expect(page.locator('.agent-result')).to_contain_text('Tâche en cours')
            await expect(page.get_by_role('button', name='Nouvelle conversation', exact=True)).to_be_disabled()
            await expect(page.get_by_role('button', name='Annuler la tâche', exact=True)).to_have_count(0)
            await expect(page.locator('.composer').get_by_role('button', name='Arrêter la réponse')).to_be_enabled()
            project_top = (await page.locator('.project-controls').bounding_box())['y']
            await page.locator('.chat-scroll').evaluate('el => el.scrollTop = el.scrollHeight')
            assert (await page.locator('.project-controls').bounding_box())['y'] == project_top
            await expect(page.locator('.project-controls')).to_be_in_viewport()
            await page.screenshot(path=OUTPUT / "programming-dark.png")
            await page.get_by_role("button", name="Arrêter la réponse").click()
            await expect(page.get_by_role("button", name="Arrêter la réponse")).to_have_count(0)
            # Un second tour doit conserver la première consigne, même après annulation.
            await expect(page.get_by_role('button', name='Nouvelle conversation', exact=True)).to_be_enabled()
            await page.locator('#question').fill('Lis le fichier texte.')
            await page.get_by_role('button', name='Envoyer', exact=True).click()
            await expect(page.locator('.message-user').filter(has_text='Lis le fichier texte.')).to_have_count(1)
            await expect(page.locator('.message-user').filter(has_text=task)).to_have_count(1)
            fixture.run.update(state="completed", validation_status="validated",
                               result_summary="Le fichier texte contient **bonjour**.", failure_detail=None)
            fixture.changes = []
            await page.reload()
            await expect(page.locator('.agent-result strong').filter(has_text='bonjour')).to_be_visible()
            await expect(page.locator('.agent-result')).to_contain_text('Aucun fichier modifié.')
            await expect(page.locator('.agent-result').get_by_role('button', name='Accepter les changements')).to_be_visible()
            await expect(page.get_by_role("button", name="Accepter les changements")).to_be_visible()
            await page.get_by_role("button", name="Accepter les changements").click()
            await expect(page.locator(".agent-changes")).to_have_count(0)
            await expect(page.locator('.agent-result')).to_contain_text('Changements acceptés.')
            await expect(page.locator('.agent-result')).to_contain_text('Le fichier texte contient bonjour.')
            await expect(page.locator('.message-user').filter(has_text=task)).to_have_count(1)
            await expect(page.locator('.message-user').filter(has_text='Lis le fichier texte.')).to_have_count(1)
            await page.reload()
            await expect(page.locator('.agent-result')).to_contain_text('Le fichier texte contient bonjour.')
            checked.append('Réponse de lecture sans diff, résultat conservé après Accept et rechargement, échec backend lisible')
            checked.append("Programmation : accueil spécialisé, Projet compact, arrêt depuis la saisie et checkpoint simulés")
            checked.append('Programmation en bulles : deux consignes persistantes, absence de doublons, Projet fixe et décisions dans la réponse')

            await page.locator("#model-profile").select_option("general")
            fixture.conversations[FIRST] = conversation(FIRST, "Découvrir Léa", ANSWER)
            await page.locator('.conversation-row').filter(has_text='Découvrir Léa').locator('.conversation-summary').click()
            await expect(page.locator('.conversation-summary[aria-current="page"]')).to_contain_text('Découvrir Léa')
            await page.reload()
            await expect(page.locator(".markdown-content table")).to_be_visible()
            for width, height in [(1920, 1080), (1024, 768), (768, 700), (600, 600), (390, 844), (320, 568)]:
                await page.set_viewport_size(dict(width=width, height=height))
                await expect(page.locator("#conversation-sidebar")).to_be_visible()
                await expect(page.locator(".sidebar-brand button")).to_be_in_viewport()
                await expect(page.locator(".sidebar-footer")).to_be_in_viewport()
                assert await page.locator('.sidebar-footer').evaluate("""footer => {
                    const box = footer.getBoundingClientRect();
                    const sidebar = document.querySelector('.sidebar').getBoundingClientRect();
                    return Math.abs(box.x - sidebar.x) < 1
                        && Math.abs(box.right - sidebar.right) <= 1;
                }""")
                if width > 600:
                    resource_box = await page.locator('.resources').bounding_box()
                    footer_box = await page.locator('.sidebar-footer').bounding_box()
                    assert abs(resource_box['y'] - footer_box['y']) < 1
                await expect(page.locator('.chat-topbar .ephemeral-toggle')).to_be_in_viewport()
                await check_composer_height(page, "Texte replié automatiquement. " * 60, 4, scrollable=True)
                await check_composer_height(page, "", 1)
                await check_composer_spacing(page)
                await page.locator(".chat-scroll").evaluate("el => el.scrollTop = 100")
                assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"overflow {width}"
                bounds = await page.locator("#question").bounding_box()
                assert bounds and bounds["width"] > 100 and bounds["y"] + bounds["height"] <= height, bounds
                assert (await page.locator(".chat-scroll").bounding_box())["height"] >= 140
                await page.screenshot(path=OUTPUT / f"conversation-{width}.png")
            await page.get_by_role("button", name="Arrêter", exact=True).focus()
            await page.keyboard.press("Tab")
            await expect(page.locator('.chat-topbar .ephemeral-toggle')).to_be_focused()
            await page.keyboard.press("Tab")
            await expect(page.locator("#model-profile")).to_be_focused()
            await page.keyboard.press("Escape")
            await expect(page.locator("#conversation-sidebar")).to_be_visible()
            await expect(page.get_by_role("dialog", name="Conversations locales")).to_have_count(0)
            checked.append("Six dimensions, barre toujours visible, historique compact et clavier sans piège de focus")

            # Sur écran tactile, aucune action ne doit dépendre d'un survol impossible.
            touch_fixture = Fixtures()
            touch = await browser.new_context(viewport=dict(width=390, height=844), has_touch=True, is_mobile=True)
            await touch.route("**/*", touch_fixture.route)
            touch_page = await touch.new_page()
            touch_page.on("pageerror", lambda error: errors.append(str(error)))
            await touch_page.goto(ORIGIN)
            await expect(touch_page.locator("#model-profile")).to_have_value("general")
            touch_row = touch_page.locator(".conversation-row").filter(has_text="Notes de travail")
            await expect(touch_row.locator(".conversation-row-actions")).to_have_css("opacity", "1")
            await touch_row.get_by_role("button", name="Renommer « Notes de travail »").tap()
            await expect(touch_page.locator("#conversation-title")).to_have_value("Notes de travail")
            await expect(touch_page.locator("#conversation-sidebar")).to_be_visible()
            await touch_page.get_by_role("button", name="Paramètres", exact=True).tap()
            await expect(touch_page.get_by_role("heading", name="Paramètres de Léa")).to_be_visible()
            await touch_page.get_by_role("button", name="Retour aux conversations").tap()
            await expect(touch_page.get_by_role("button", name="Paramètres", exact=True)).to_be_focused()
            await expect(touch_page.locator("#conversation-title")).to_have_value("Notes de travail")
            assert not touch_fixture.external and not touch_fixture.unexpected
            await touch.close()
            checked.append("Actions tactiles et paramètres accessibles sans fermer la barre permanente")

            await page.set_viewport_size(dict(width=1440, height=1000))
            await check_composer_height(page, "ligne\n" * 30, 4, scrollable=True)
            await page.get_by_role("button", name="Arrêter", exact=True).click()
            await expect(page.locator(".core-status")).to_have_count(0)
            await expect(page.get_by_role("button", name="Arrêter", exact=True)).to_be_disabled()
            await expect(page.get_by_role("button", name="Démarrer", exact=True)).to_be_enabled()
            sends_before = sum(path == "/api/conversations/messages" for _, path, _ in fixture.calls)
            await page.locator("#question").press("Enter")
            await page.wait_for_timeout(100)
            assert sum(path == "/api/conversations/messages" for _, path, _ in fixture.calls) == sends_before
            # Une erreur réelle du contrôleur reste lisible hors du pied de page.
            fixture.core_failure = True
            await page.get_by_role('button', name='Démarrer', exact=True).click()
            await expect(page.locator('.chat-topbar .core-status')).to_contain_text('contrôleur local')
            assert await page.locator('.chat-topbar .core-status').evaluate("""notice => {
                const box = notice.getBoundingClientRect();
                const bar = notice.closest('header').getBoundingClientRect();
                return Math.abs(box.x + box.width / 2 - bar.x - bar.width / 2) < 1;
            }""")
            await expect(page.locator('.sidebar-footer p')).to_have_count(0)
            await page.get_by_role("button", name="Paramètres", exact=True).click()
            await expect(page.locator('.core-status-banner .core-status')).to_contain_text('contrôleur local')
            await expect(page.get_by_label("Sombre", exact=True)).to_be_checked()
            await page.get_by_label("Clair", exact=True).check()
            await page.locator(".settings").evaluate("el => el.scrollTop = 0")
            await page.screenshot(path=OUTPUT / "settings-light.png")
            await page.get_by_role("button", name="Retour aux conversations").click()
            await check_theme_contrast(page)
            fixture.core_failure = False
            fixture.core = 'stopped'
            # Le profil peut garder sa valeur pendant le redémarrage : attendre
            # aussi le rechargement de l'historique avant de saisir le brouillon suivant.
            async with page.expect_response(lambda response: response.url.endswith(f"/api/conversations/{FIRST}")):
                await page.get_by_role("button", name="Démarrer", exact=True).click()
            await expect(page.locator("#model-profile")).to_have_value("general")
            await expect(page.locator("#question")).to_be_enabled()
            await expect(page.locator('.core-status')).to_have_count(0)
            checked.append("Saisie bornée, arrêt/redémarrage simulés et paramètres IA arrêtée")
            checked.append("Séparateurs alignés bord à bord ; erreur du cœur centrée en haut, aussi visible dans les paramètres")

            # Le crayon d'une autre conversation charge sa révision avant de renommer.
            row = page.locator(".conversation-row").filter(has_text="Notes de travail")
            await page.locator("#question").fill("Brouillon à conserver")
            await expect(page.locator("#question")).to_have_value("Brouillon à conserver")
            await page.locator("#question").hover()
            await expect(row.locator(".conversation-row-actions")).to_have_css("opacity", "0")
            await row.hover()
            await expect(row.locator(".conversation-row-actions")).to_have_css("opacity", "1")
            await page.screenshot(path=OUTPUT / "sidebar-actions.png")
            await row.locator(".conversation-summary").focus()
            await page.keyboard.press("Tab")
            await expect(row.get_by_role("button", name="Renommer « Notes de travail »")).to_be_focused()
            await row.get_by_role("button", name="Renommer « Notes de travail »").click()
            await expect(page.locator("#conversation-title")).to_have_value("Notes de travail")
            await expect(page.locator("#conversation-title")).to_be_focused()
            await page.locator("#conversation-title").fill("Notes renommées")
            await page.get_by_role("button", name="Enregistrer", exact=True).click()
            assert fixture.conversations[SECOND]["title"] == "Notes renommées"
            assert fixture.conversations[FIRST]["title"] == "Découvrir Léa"
            await page.locator(".conversation-summary").filter(has_text="Découvrir Léa").click()
            await expect(page.locator(".conversation-summary[aria-current='page']")).to_contain_text("Découvrir Léa")
            checked.append("Crayon au survol et au clavier, renommage de la bonne conversation")

            # Un refus, un conflit ou une suppression d'une autre ligne préserve le brouillon actif.
            delete = page.get_by_role("button", name="Supprimer « Notes renommées »", exact=True)
            await expect(delete).to_be_enabled()
            await delete.focus()
            await expect(delete).to_be_focused()
            deletes_before = sum(method == "DELETE" for method, _, _ in fixture.calls)
            page.once("dialog", lambda dialog: dialog.dismiss())
            await delete.click()
            assert sum(method == "DELETE" for method, _, _ in fixture.calls) == deletes_before
            fixture.fail_delete = True
            page.once("dialog", lambda dialog: dialog.accept())
            await delete.click()
            await expect(page.get_by_role("alert").filter(has_text="autre onglet")).to_be_visible()
            assert SECOND in fixture.conversations
            fixture.fail_delete = False
            await delete.focus()
            page.once("dialog", lambda dialog: dialog.accept())
            await delete.click()
            await expect(page.locator(".conversation-summary")).to_have_count(2)
            await expect(page.locator(".conversation-summary[aria-current='page']")).to_contain_text("Découvrir Léa")
            await expect(page.locator("#question")).to_have_value("Brouillon à conserver")
            assert FIRST in fixture.conversations and SECOND not in fixture.conversations
            checked.append("Poubelle : confirmation, conflit et suppression inactive sans perte du brouillon")

            # La ligne Programmation reste gérable sans charger son contenu dans Général.
            row = page.locator('.conversation-row').filter(has_text='Tâche de programmation')
            await expect(row.locator('.conversation-summary')).to_be_disabled()
            loads_before = sum(method == 'GET' and path == f'/api/conversations/{PROGRAMMING}'
                               for method, path, _body in fixture.calls)
            await row.get_by_role('button', name='Renommer « Tâche de programmation »').click()
            await page.locator('#conversation-title').fill('Travail renommé')
            await page.get_by_role('button', name='Enregistrer', exact=True).click()
            await expect(page.locator('#conversation-title')).to_have_count(0)
            assert sum(method == 'GET' and path == f'/api/conversations/{PROGRAMMING}'
                       for method, path, _body in fixture.calls) == loads_before
            await expect(page.locator('#question')).to_have_value('Brouillon à conserver')
            page.once('dialog', lambda dialog: dialog.accept())
            await page.locator('.conversation-row').filter(has_text='Travail renommé').hover()
            await page.locator('.conversation-row').filter(has_text='Travail renommé').hover()
            await page.get_by_role('button', name='Supprimer « Travail renommé »').click()
            await expect(page.locator('.conversation-summary')).to_have_count(1)
            checked.append('Historique Programmation verrouillé hors profil, renommage et suppression sans chargement')

            # Le titre et ses actions restent uniquement dans la barre latérale.
            await expect(page.locator(".conversation-header")).to_have_count(0)
            await expect(page.get_by_role("button", name="Renommer", exact=True)).to_have_count(0)
            await expect(page.get_by_role("button", name="Supprimer", exact=True)).to_have_count(0)
            page.on("dialog", lambda dialog: dialog.accept())
            await page.locator(".conversation-row").filter(has_text="Découvrir Léa").hover()
            await page.get_by_role("button", name="Renommer « Découvrir Léa »", exact=True).click()
            await page.locator("#conversation-title").fill("Titre modifié")
            await page.get_by_role("button", name="Enregistrer", exact=True).click()
            await expect(page.locator(".conversation-summary[aria-current='page']")).to_contain_text("Titre modifié")
            await page.locator(".conversation-row").filter(has_text="Titre modifié").hover()
            await page.get_by_role("button", name="Supprimer « Titre modifié »", exact=True).click()
            await expect(page.locator(".welcome")).to_be_visible()
            await expect(page.locator("#question")).to_be_focused()
            assert FIRST not in fixture.conversations
            checked.append("Titre et actions retirés du chat ; renommage et suppression conservés dans la barre")
            assert not fixture.external, fixture.external
            assert not any(path.endswith("/regenerate") for _, path, _ in fixture.calls)
            assert not fixture.unexpected, fixture.unexpected
            assert not errors, errors
            checked.append("Zéro requête externe, API non prévue ou erreur JavaScript")
            report = dict(passed=len(checked), checks=checked, browser=browser.version,
                          minimum_text_contrast=dict(light=round(light_contrast, 2), dark=round(dark_contrast, 2)),
                          api_calls=len(fixture.calls), external_requests=fixture.external, page_errors=errors,
                          limitation="API simulées ; pas de modèle, Docker, microphone physique ni base utilisateur.")
            (OUTPUT / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=True, indent=2))
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
