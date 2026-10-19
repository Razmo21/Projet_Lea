import assert from 'node:assert/strict'
import { connect } from './edge-stage12.mjs'

// Run against an isolated Vite database and a muted, disposable Edge on LEA_EDGE_CDP_PORT.
// Real Piper -> synthetic MediaStream -> native MediaRecorder -> app conversion -> real Whisper.
// The mounted production conversation then uses its default real Pocket TTS voice.
// No physical microphone, model conversation, project mutation or audio file is used.
const session = await connect()
const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds))
try {
  await session.navigate('http://127.0.0.1:5173')
  await session.evaluate(`(async () => {
    window.__voiceModule = await import('/src/voice.ts');
    const sound = await window.__voiceModule.voiceRequest('speak', {text:'Bonjour. Ceci est un test du microphone.', voice_id:'fr-siwis', rate:1});
    window.__input = new AudioContext({sampleRate:48000}); await window.__input.resume();
    window.__speech = await window.__input.decodeAudioData(Uint8Array.from(atob(sound.audio), c=>c.charCodeAt(0)).buffer);
    window.__sources=[]; window.__tracks=[]; window.__parts=[]; window.__events=[];
    navigator.mediaDevices.getUserMedia = async () => {
      const destination=window.__input.createMediaStreamDestination();
      const source=window.__input.createBufferSource();source.buffer=window.__speech;source.loop=true;source.connect(destination);source.start();
      window.__sources.push(source);window.__tracks.push(...destination.stream.getTracks());return destination.stream;
    };
    const NativeRecorder=MediaRecorder;
    window.MediaRecorder=class extends NativeRecorder {
      constructor(stream, options) {
        super(stream, window.__forcedMime ? {mimeType:window.__forcedMime} : options);
        this.addEventListener('dataavailable', e=>{window.__parts.push(e.data);window.__events.push({event:'data',bytes:e.data.size,mime:e.data.type})});
        this.addEventListener('stop', ()=>window.__events.push({event:'stop',mime:this.mimeType,tracksLive:stream.getTracks().every(t=>t.readyState==='live')}));
      }
    };
    const info=console.info;window.__diagnostics=[];
    console.info=(label,metadata)=>{if(label==='[Lea microphone]')window.__diagnostics.push(metadata);info(label,metadata)};
  })()`)

  for (const mime of ['', 'audio/mp4;codecs=mp4a.40.2']) {
    if (mime && !await session.evaluate(`MediaRecorder.isTypeSupported(${JSON.stringify(mime)})`)) continue
    await session.evaluate(`(async()=>{window.__forcedMime=${JSON.stringify(mime)};window.__parts=[];window.__events=[];window.__capture=new window.__voiceModule.MicrophoneCapture();await window.__capture.start('',e=>{throw e})})()`)
    await pause(3800)
    const result = await session.evaluate(`(async()=>{
      const wav=await window.__capture.stop();const view=new DataView(wav.buffer);
      const transcript=await window.__voiceModule.voiceRequest('transcribe',{audio:window.__voiceModule.audioBase64(wav),language:'fr'});
      const encoded=new Blob(window.__parts);let truncatedError='';const decoder=new AudioContext();
      try{await decoder.decodeAudioData((await encoded.arrayBuffer()).slice(0,8))}catch(e){truncatedError=e.name}finally{await decoder.close()}
      const rejected=[];
      for(const bytes of [new Uint8Array(await encoded.arrayBuffer()),wav.slice(0,-32)]){
        const reply=await fetch('/api/voice/transcribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({audio:window.__voiceModule.audioBase64(bytes),language:'fr'})});rejected.push(reply.status);
      }
      window.__parts=[];window.__sources.splice(0).forEach(s=>s.stop());
      return {events:window.__events,diagnostic:window.__diagnostics.at(-1),wav:{container:window.__voiceModule.audioContainer(wav),rate:view.getUint32(24,true),channels:view.getUint16(22,true),bits:view.getUint16(34,true),bytes:wav.length},transcribed:!!transcript.text.trim(),seconds:transcript.audio_seconds,rejected,truncatedError,tracksEnded:window.__tracks.every(t=>t.readyState==='ended')};
    })()`)
    assert.ok(result.transcribed)
    assert.equal(result.wav.container, 'wav'); assert.equal(result.wav.rate, 16000)
    assert.equal(result.wav.channels, 1); assert.equal(result.wav.bits, 16)
    assert.ok(result.events.filter(event => event.event === 'data').length > 1)
    assert.deepEqual(result.events.at(-1), { event: 'stop', mime: result.diagnostic.recorderMime, tracksLive: true })
    assert.equal(result.tracksEnded, true); assert.equal(result.truncatedError, 'EncodingError')
    assert.deepEqual(result.rejected, [422, 422])
    assert.ok(Math.abs(result.seconds - (result.wav.bytes - 44) / 32000) < .001)
    console.log('PASS native recording, real STT and malformed transport rejection:', JSON.stringify(result))
  }

  // Mount the production component alone: only model readiness/response are test doubles.
  // Both UI modes use real capture, conversion, HTTP validation and Whisper, then Pocket TTS.
  await session.evaluate(`(async()=>{
    window.__forcedMime='';window.__dictated='';window.__sent=0;
    const {default:React}=await import('/node_modules/.vite/deps/react.js');
    const {default:ReactDOM}=await import('/node_modules/.vite/deps/react-dom_client.js');
    const {default:VoiceControls}=await import('/src/VoiceControls.tsx');
    const {defaultVoicePreferences}=await import('/src/preferences.ts');
    document.querySelector('#root').hidden=true;
    const mount=document.createElement('div');document.body.append(mount);window.__testRoot=ReactDOM.createRoot(mount);
    window.__testRoot.render(React.createElement(VoiceControls,{
      preferences:{...defaultVoicePreferences},contextKey:'decode-test',ready:true,blocked:false,hidden:false,
      onMode:()=>{},onDictated:text=>{window.__dictated=text},onSend:async text=>{window.__sent++;return {text:'Bonjour. Le test vocal est terminé.'}}
    }));
  })()`)
  await session.wait(`!![...document.querySelectorAll('button')].find(b=>b.getClientRects().length&&b.textContent==='Dicter au microphone')`)
  for (const conversation of [false, true]) {
    if (conversation) await session.click('button', 'Conversation vocale')
    await session.click('button', conversation ? 'Parler à Léa' : 'Dicter au microphone')
    await session.wait(`!![...document.querySelectorAll('button')].find(b=>b.getClientRects().length&&b.textContent===${JSON.stringify(conversation ? 'Terminer et envoyer' : 'Terminer la dictée')})`)
    await pause(3800)
    await session.click('button', conversation ? 'Terminer et envoyer' : 'Terminer la dictée')
    if (!conversation) {
      await session.wait(`window.__dictated.length>0`, 30000)
      assert.equal(await session.evaluate('window.__sent'), 0)
    } else {
      await session.wait(`document.body.innerText.includes('Léa parle')`, 30000)
      await session.click('button', 'Arrêter la lecture')
      assert.equal(await session.evaluate('window.__sent'), 1)
      await session.click('button', 'Retour aux conversations')
    }
    assert.equal(await session.evaluate(`window.__tracks.every(t=>t.readyState==='ended')`), true)
  }
  console.log('PASS both production voice modes; real browser/STT/TTS, simulated conversation response, no physical audio validation.')
} finally {
  await session.evaluate(`(async()=>{window.__capture?.cancel();window.__testRoot?.unmount();window.__tracks?.forEach(t=>t.stop());window.__sources?.forEach(s=>{try{s.stop()}catch{}});if(window.__input)await window.__input.close();window.__parts=[];window.__speech=null})()`).catch(() => {})
  session.socket.close()
}
