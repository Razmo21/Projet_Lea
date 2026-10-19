import assert from 'node:assert/strict'

// Diagnostic only: two disposable browser instances, never the user's editor/profile.
// Generate one synthetic recording in Edge and decode those exact bytes in both hosts.
const originalPort = process.env.LEA_EDGE_CDP_PORT
process.env.LEA_EDGE_CDP_PORT = originalPort ?? '9236'
const { connect: connectEdge } = await import('./edge-stage12.mjs?codec-edge')
process.env.LEA_EDGE_CDP_PORT = process.env.LEA_CODEC_HOST_CDP_PORT ?? '9238'
const { connect: connectHost } = await import('./edge-stage12.mjs?codec-host')
if (originalPort === undefined) delete process.env.LEA_EDGE_CDP_PORT
else process.env.LEA_EDGE_CDP_PORT = originalPort

const edge = await connectEdge()
const host = await connectHost()
try {
  await edge.navigate('http://127.0.0.1:5173')
  const fixture = await edge.evaluate(`(async()=>{
    const context=new AudioContext();await context.resume();
    const destination=context.createMediaStreamDestination();const oscillator=context.createOscillator();
    oscillator.connect(destination);oscillator.start();
    const recorder=new MediaRecorder(destination.stream,{mimeType:'audio/webm;codecs=opus'});const chunks=[];
    recorder.ondataavailable=event=>chunks.push(event.data);
    const stopped=new Promise(resolve=>recorder.onstop=resolve);
    try {
      recorder.start();await new Promise(resolve=>setTimeout(resolve,1500));recorder.stop();await stopped;
      const bytes=new Uint8Array(await new Blob(chunks,{type:recorder.mimeType}).arrayBuffer());
      const decoded=await context.decodeAudioData(bytes.buffer.slice(0));
      const {pcmWav,audioBase64}=await import('/src/voice.ts');
      const pcm=Float32Array.from({length:16000},(_,index)=>Math.sin(index*.1)*.2);
      return {opus:audioBase64(bytes),wav:audioBase64(pcmWav(pcm)),bytes:bytes.length,seconds:decoded.duration,mime:recorder.mimeType};
    } finally { destination.stream.getTracks().forEach(track=>track.stop());oscillator.stop();await context.close() }
  })()`)
  assert.ok(fixture.seconds > .2)
  // Audio bytes stay inside this process and the renderer, never in logs or files.
  const result = await host.evaluate(`(async()=>{
    const results=[];
    for(const [format,audio]of Object.entries(${JSON.stringify({ opus: fixture.opus, wav: fixture.wav })})) {
      const context=new AudioContext();const item={format,rate:context.sampleRate,state:context.state};
      try {const decoded=await context.decodeAudioData(Uint8Array.from(atob(audio),char=>char.charCodeAt(0)).buffer);item.seconds=decoded.duration}
      catch(error){item.error=error.name+': '+error.message}
      finally{await context.close()}
      results.push(item);
    }
    return {userAgent:navigator.userAgent,canRecordOpus:MediaRecorder.isTypeSupported('audio/webm;codecs=opus'),canPlayOpus:document.createElement('audio').canPlayType('audio/webm;codecs=opus'),results};
  })()`)
  assert.equal(result.results.find(item => item.format === 'wav').seconds, 1)
  console.log(JSON.stringify({ edge: { mime: fixture.mime, bytes: fixture.bytes, seconds: fixture.seconds }, otherHost: result }, null, 2))
  // A future VS Code decoder fix should be reported, not treated as an app regression.
  console.log(result.results.find(item => item.format === 'opus').error
    ? 'REPRODUCED: identical complete Opus decodes in Edge, rejected by the other host; PCM works.'
    : 'Opus decoding is now available in both tested hosts.')
} finally { edge.socket.close(); host.socket.close() }
