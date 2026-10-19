import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { connect, type } from './edge-stage12.mjs'

const api = 'http://127.0.0.1:8000'
const session = await connect()
// Confirm dialogs only inside this isolated browser and this named disposable project.
const dialog = event => {
  if (JSON.parse(String(event.data)).method === 'Page.javascriptDialogOpening') {
    void session.send('Page.handleJavaScriptDialog', { accept: true })
  }
}
session.socket.addEventListener('message', dialog)
try {
  const projects = await (await fetch(`${api}/api/projects`)).json()
  const project = projects.projects.find(item => item.name === 'Lea_Stage14_20261017')
  assert.equal(project?.id, projects.active_project_id)
  const before = (await (await fetch(`${api}/api/agent-runs`)).json()).runs[0]
  assert.equal(before.project_id, project.id)
  assert.equal(before.state, 'failed')
  assert.equal(before.validation_status, 'failed')
  const conversation = await (await fetch(`${api}/api/conversations/${before.conversation_id}`)).json()
  assert.equal(conversation.messages.filter(item => item.agent_run_id === before.run_id).length, 2)
  assert.match(conversation.messages.at(-1).content, /failed/)
  await session.click('button', 'Examiner le run et le diff')
  await session.wait(`document.querySelector('.agent-changes')?.textContent.includes('app.py')`)
  assert.equal(await session.evaluate(`!![...document.querySelectorAll('button')].find(b=>b.textContent==='Accepter les changements' && !b.disabled)`), false)
  await session.click('button', 'Restaurer le checkpoint')
  await session.wait(`document.querySelector('.agent-changes')?.textContent.includes('rolled_back')`)
  console.log('PASS retour explicite depuis la voix : failed visible, Accept refusé, Rollback confirmé.')

  // The written regression task names the supported validation command explicitly.
  // No runner/evidence heuristic is changed to accommodate a model decision.
  await type(session, '#agent-task', 'Lis app.py et test_app.py. Corrige uniquement app.py pour que add additionne ses deux arguments. Ne modifie aucun test. Lance exactement python -B -m unittest -v et termine après le test réussi.')
  await session.click('button', 'Lancer le run')
  await session.wait(`document.querySelector('.agent-run-status')?.textContent.includes('running')`, 120000)
  const run = (await (await fetch(`${api}/api/agent-runs`)).json()).runs[0]
  assert.equal(run.project_id, project.id)
  assert.notEqual(run.run_id, before.run_id)
  await session.wait(`document.querySelector('.agent-run-status')?.textContent.includes('completed') || document.querySelector('.agent-run-status')?.textContent.includes('failed')`, 600000)
  const final = await (await fetch(`${api}/api/agent-runs/${run.run_id}`)).json()
  assert.equal(final.state, 'completed')
  assert.equal(final.validation_status, 'validated')
  await session.wait(`document.querySelector('.agent-changes')?.textContent.includes('app.py')`)
  const changes = await (await fetch(`${api}/api/agent-runs/${run.run_id}/changes`)).json()
  assert.deepEqual(changes.changes.map(item=>item.relative_path), ['app.py'])
  await session.click('button', 'Accepter les changements')
  await session.wait(`document.querySelector('.agent-changes')?.textContent.includes('accepted')`)
  await writeFile('.test-runtime/stage14-20261017/programming-accept.json', JSON.stringify({final,changes},null,2))
  console.log('PASS run écrit réel : correction source, test vert reconnu, validation, diff et Accept explicite.')
} finally {
  session.socket.removeEventListener('message', dialog)
  session.socket.close()
}
