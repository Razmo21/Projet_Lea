import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { connect } from './edge-stage12.mjs'

const api = 'http://127.0.0.1:8000'
const app = 'http://127.0.0.1:5173'
const out = '.test-runtime/stage14-20261017'
const session = await connect()
const fixture = await readFile(`${out}/synthetic-programming.wav`)
const duration = (fixture.length - 44) / 32000

// This script selects only the named disposable fixture, never the current user's project.
async function mutate(path) {
  const response = await fetch(`${api}${path}`, { method: 'POST', headers: { Origin: app } })
  assert.equal(response.status, 200)
  return response.json()
}

try {
  const projects = await (await fetch(`${api}/api/projects`)).json()
  const project = projects.projects.find(item => item.name === 'Lea_Stage14_20261017')
  assert.ok(project)
  await mutate(`/api/projects/${project.id}/activate`)
  await session.navigate(app)
  await session.wait(`document.body.innerText.includes('Programmation est prêt.') && document.querySelector('#agent-task') !== null`, 30000)
  await session.evaluate(`(() => {
    window.__calls = []; window.__play = []; window.__tracks = [];
    const fetcher = window.fetch;
    window.fetch = async (...args) => {
      const entry = {url:String(args[0]), start:performance.now(), method:args[1]?.method ?? 'GET'};
      window.__calls.push(entry);
      const result = await fetcher(...args);
      entry.end=performance.now(); entry.status=result.status;
      if (entry.url.endsWith('/api/core/status')) entry.core = await result.clone().json();
      return result;
    };
    const media = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async (...args) => {const stream=await media(...args); window.__tracks.push(...stream.getTracks()); return stream;};
    const start = AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start = function(...args) { if(this.context instanceof AudioContext) window.__play.push({time:performance.now(),state:this.context.state}); return start.apply(this,args); };
  })()`)
  await session.click('button', 'Conversation vocale')
  assert.equal(await session.evaluate(`!![...document.querySelectorAll('textarea,.message')].find(el=>el.getClientRects().length)`), false)
  await session.click('button', 'Parler à Léa')
  await session.wait(`document.body.innerText.includes('Clique à nouveau pour terminer')`)
  await new Promise(resolve => setTimeout(resolve, duration * 1000 + 150))
  await session.click('button', 'Terminer et envoyer')
  await session.wait(`document.body.innerText.includes('Validation visuelle obligatoire') || document.body.innerText.includes('Contexte modifié')`, 600000)
  if (await session.evaluate(`document.body.innerText.includes('Contexte modifié')`)) {
    const diagnostic = await session.evaluate('window.__calls.filter(item=>item.core)')
    await writeFile(`${out}/browser-programming-context-error.json`, JSON.stringify(diagnostic, null, 2))
    assert.fail('Le contexte vocal a changé pendant le run ; diagnostic de statut sauvegardé.')
  }
  await session.wait(`window.__play.length > 0`, 60000)
  const runs = await (await fetch(`${api}/api/agent-runs`)).json()
  const run = runs.runs.find(item=>item.project_id===project.id)
  assert.ok(run)
  const changes = await (await fetch(`${api}/api/agent-runs/${run.run_id}/changes`)).json()
  // Preserve real feedback evidence even if the model fails its project validation.
  const feedback = await session.evaluate('({calls:window.__calls,playback:window.__play})')
  await writeFile(`${out}/browser-programming-feedback.json`, JSON.stringify({syntheticMicrophone:true,mutedOutput:true,run,changes,timings:feedback},null,2))
  assert.equal(changes.checkpoint.state, 'completed')
  assert.equal(run.state, 'completed')
  assert.equal(run.validation_status, 'validated')
  assert.deepEqual(changes.changes.map(item=>item.relative_path), ['app.py'])
  const detail = await (await fetch(`${api}/api/conversations/${run.conversation_id}`)).json()
  assert.equal(detail.messages.filter(item=>item.agent_run_id===run.run_id).length, 2)
  assert.equal(await session.evaluate(`window.__calls.some(item => item.url.endsWith('/api/conversations/messages'))`), false)
  assert.equal(await session.evaluate(`window.__calls.some(item => /\/(accept|rollback)$/.test(item.url))`), false)
  assert.equal(await session.evaluate(`window.__tracks.every(track=>track.readyState==='ended')`), true)
  await session.click('button', 'Examiner le run et le diff')
  await session.wait(`document.querySelector('.agent-changes')?.textContent.includes('app.py')`)
  const operation = process.argv.includes('--accept') ? 'Accepter les changements' : 'Restaurer le checkpoint'
  await session.send('Page.enable')
  const dialog = (event) => {
    if (JSON.parse(String(event.data)).method === 'Page.javascriptDialogOpening') void session.send('Page.handleJavaScriptDialog', { accept: true })
  }
  session.socket.addEventListener('message', dialog)
  try {
    await session.click('button', operation)
    await session.wait(`document.querySelector('.agent-changes')?.textContent.includes('${process.argv.includes('--accept') ? 'accepted' : 'rolled_back'}')`, 30000)
  } finally { session.socket.removeEventListener('message', dialog) }
  const timings = await session.evaluate('({calls:window.__calls,playback:window.__play})')
  await writeFile(`${out}/browser-programming-${process.argv.includes('--accept') ? 'accept' : 'rollback'}.json`, JSON.stringify({syntheticMicrophone:true,mutedOutput:true,run,changes,timings},null,2))
  console.log(`PASS voix Programmation réelle, source modifiée, tests verts, validation, histoire liée, ${operation} explicite.`)
} finally { session.socket.close() }
