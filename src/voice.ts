import type { VoicePreferences } from './preferences'

export type VoiceStatus = {
  stt: boolean
  tts: boolean
  voices: { id: string; label: string; engine: 'piper' | 'pocket-tts'; supports_rate: boolean }[]
  stt_engine?: string
  tts_engines?: string[]
}

// Preserve a user's SIWIS setting while refusing to invent Pocket TTS rate support.
export function effectiveVoiceRate(voice: VoiceStatus['voices'][number], savedRate: number): number {
  return voice.supports_rate ? savedRate : 1
}

// Only the local, bounded Vite controller receives audio. No browser speech service.
export async function voiceRequest<T>(action: 'status' | 'transcribe' | 'speak', body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/voice/${action}`, {
    method: body ? 'POST' : 'GET', cache: 'no-store', signal,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const value = await response.json()
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Moteur vocal indisponible.')
  return value as T
}

// Preserve edits made while STT was working; dictation never replaces the draft.
export function appendDictation(draft: string, text: string): string {
  return draft + (draft && !/\s$/.test(draft) ? ' ' : '') + text.trim()
}

// Encode the fixed format understood by Whisper, without a filename or temporary file.
export function pcmWav(samples: Float32Array): Uint8Array {
  if (samples.length < 3200 || samples.length > 120 * 16000) throw new Error('Enregistrement vide ou trop long (120 secondes maximum).')
  const bytes = new Uint8Array(44 + samples.length * 2)
  const view = new DataView(bytes.buffer)
  const word = (offset: number, value: string) => { for (let i = 0; i < value.length; i++) bytes[offset + i] = value.charCodeAt(i) }
  word(0, 'RIFF'); view.setUint32(4, bytes.length - 8, true); word(8, 'WAVEfmt ')
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true)
  view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true)
  word(36, 'data'); view.setUint32(40, samples.length * 2, true)
  for (let i = 0; i < samples.length; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(44 + i * 2, sample * (sample < 0 ? 32768 : 32767), true)
  }
  return bytes
}

// Chunk conversion avoids an argument-stack overflow for a two-minute recording.
export function audioBase64(bytes: Uint8Array): string {
  let binary = ''
  for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192))
  return btoa(binary)
}

// Identify only the container header, not speech content; decoding remains the integrity check.
export function audioContainer(bytes: Uint8Array): string {
  const word = (offset: number, text: string) => [...text].every((char, index) => bytes[offset + index] === char.charCodeAt(0))
  if (word(0, 'RIFF') && word(8, 'WAVE')) return 'wav'
  if ([0x1a, 0x45, 0xdf, 0xa3].every((byte, index) => bytes[index] === byte)) return 'webm/ebml'
  if (word(4, 'ftyp')) return 'mp4'
  if (word(0, 'OggS')) return 'ogg'
  return 'unknown'
}

export class MicrophoneCapture {
  private stream?: MediaStream
  private recorder?: MediaRecorder
  private chunks: Blob[] = []
  private timer?: ReturnType<typeof setTimeout>
  private cancelled = false
  private decode?: AudioContext
  private pendingStop?: (reason: Error) => void
  private startedAt = 0
  private diagnostic: Record<string, unknown> = {}

  // Metadata only, in the local browser console: never audio, text, device IDs or labels.
  private report(stage: string, failure?: unknown) {
    const metadata = { ...this.diagnostic, stage, error: failure instanceof Error ? failure.name : undefined }
    if (failure) console.warn('[Lea microphone]', metadata)
    else console.info('[Lea microphone]', metadata)
  }

  // Permission is requested only by the user's microphone click, never on mount.
  async start(deviceId: string, onFailure: (error: Error) => void): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') throw new Error('Capture microphone indisponible dans ce navigateur.')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: deviceId ? { deviceId: { exact: deviceId } } : true })
      if (this.cancelled) { stream.getTracks().forEach((track) => track.stop()); return }
      this.stream = stream
      for (const track of stream.getTracks()) track.onended = () => { this.cancel(); onFailure(new Error('Microphone déconnecté.')) }
      // Negotiate a supported format; still inspect the actual MIME and bytes at stop.
      // isTypeSupported describes recording support, not a guarantee of successful decoding.
      const requestedMime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : ''
      const recorder = new MediaRecorder(stream, requestedMime ? { mimeType: requestedMime } : undefined)
      this.recorder = recorder
      const settings = stream.getAudioTracks?.()[0]?.getSettings?.()
      this.diagnostic = { requestedMime, inputRate: settings?.sampleRate, inputChannels: settings?.channelCount }
      recorder.ondataavailable = (event) => { if (!this.cancelled && event.data.size) this.chunks.push(event.data) }
      recorder.onerror = () => { this.cancel(); onFailure(new Error('La capture audio a échoué.')) }
      this.startedAt = performance.now()
      recorder.start(1000)
      this.timer = setTimeout(() => { this.cancel(); onFailure(new Error('Limite de 120 secondes atteinte. Enregistrement annulé, rien envoyé.')) }, 120_000)
    } catch (failure) {
      this.cancel()
      const name = failure instanceof DOMException ? failure.name : ''
      throw new Error(name === 'NotAllowedError' ? 'Autorisation microphone refusée.' :
        ['NotFoundError', 'OverconstrainedError'].includes(name) ? 'Microphone sélectionné absent. Vérifie les paramètres.' : 'Microphone indisponible ou déjà utilisé.')
    }
  }

  // Final dataavailable precedes stop. Keep the source alive until that flush completes,
  // then release every track before decoding/STT; cancellation still releases immediately.
  async stop(): Promise<Uint8Array> {
    const recorder = this.recorder
    if (!recorder || recorder.state === 'inactive' || this.cancelled) throw new Error('Aucun enregistrement actif.')
    clearTimeout(this.timer)
    this.diagnostic.captureMs = Math.round(performance.now() - this.startedAt)
    const blob = await new Promise<Blob>((resolve, reject) => {
      // Bound a broken recorder's finalization; never send a partial recording on timeout.
      const timer = setTimeout(() => fail(new Error('Finalisation audio interrompue après 3 secondes. Rien envoyé.')), 3000)
      const cleanup = () => {
        clearTimeout(timer); this.pendingStop = undefined
        recorder.onstop = null; recorder.ondataavailable = null; recorder.onerror = null
        this.releaseTracks()
      }
      const fail = (reason: Error) => {
        cleanup(); this.chunks = []; this.report('finalize', reason); reject(reason)
      }
      this.pendingStop = fail
      recorder.onstop = () => {
        this.diagnostic.recorderMime = recorder.mimeType
        this.diagnostic.chunks = this.chunks.map(chunk => ({ mime: chunk.type, bytes: chunk.size }))
        const result = new Blob(this.chunks, { type: recorder.mimeType })
        this.diagnostic.bytes = result.size
        this.diagnostic.finalized = true
        cleanup(); this.chunks = []
        if (this.cancelled) reject(new Error('Enregistrement annulé.')); else resolve(result)
      }
      try { recorder.stop() } catch (failure) { fail(failure instanceof Error ? failure : new Error('Arrêt audio impossible.')) }
    })
    let stage = 'recording'
    try {
      if (this.cancelled || !blob.size || blob.size > 16 * 1024 * 1024) throw new Error('Enregistrement vide, annulé ou trop volumineux.')
      if (Number(this.diagnostic.captureMs) < 200) throw new Error('Enregistrement trop court. Parle au moins une seconde avant de terminer.')
      const encoded = await blob.arrayBuffer()
      this.diagnostic.container = audioContainer(new Uint8Array(encoded))
      stage = 'decode'
      const context = new AudioContext()
      this.decode = context
      const decoded = await context.decodeAudioData(encoded)
      this.diagnostic.decodedSeconds = decoded.duration
      this.diagnostic.decodedRate = decoded.sampleRate
      this.diagnostic.decodedChannels = decoded.numberOfChannels
      if (this.cancelled || decoded.duration > 120 || decoded.duration < 0.2) throw new Error('Enregistrement vide, annulé ou trop long.')
      stage = 'convert'
      const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000)
      const source = offline.createBufferSource()
      source.buffer = decoded; source.connect(offline.destination); source.start()
      const rendered = await offline.startRendering()
      if (this.cancelled) throw new Error('Enregistrement annulé.')
      const wav = pcmWav(rendered.getChannelData(0))
      this.diagnostic.wavBytes = wav.length
      this.report('ready')
      return wav
    } catch (failure) {
      this.report(stage, failure)
      if (stage === 'decode' && failure instanceof DOMException && failure.name === 'EncodingError') {
        // VS Code can advertise Opus recording/playback while its decoder rejects it.
        // Do not retry with renamed bytes or send this compressed container to Whisper.
        throw new Error(`Ce navigateur ne peut pas décoder l’enregistrement, avant envoi à Whisper. Si tu utilises le navigateur intégré de VS Code, ouvre http://127.0.0.1:5173 dans une fenêtre Microsoft Edge externe. Aucun audio envoyé (${blob.type || 'MIME absent'}, ${blob.size} octets, ${this.diagnostic.captureMs} ms, conteneur ${this.diagnostic.container}). Détails techniques dans la console : [Lea microphone].`)
      }
      throw failure
    } finally {
      const context = this.decode; this.decode = undefined
      if (context && context.state !== 'closed') await context.close()
    }
  }

  // Remove disconnection listeners before stopping tracks intentionally.
  private releaseTracks() {
    this.stream?.getTracks().forEach((track) => { track.onended = null; track.stop() })
    this.stream = undefined
  }

  // Idempotent cancellation also covers an unresolved permission prompt and decoder.
  cancel() {
    this.cancelled = true
    clearTimeout(this.timer)
    if (this.recorder?.state === 'recording') this.recorder.stop()
    this.releaseTracks(); this.chunks = []
    this.pendingStop?.(new Error('Enregistrement annulé.')); this.pendingStop = undefined
    if (this.decode && this.decode.state !== 'closed') void this.decode.close().catch(() => {})
  }
}

export class VoicePlayback {
  private context?: AudioContext
  private source?: AudioBufferSourceNode
  private finish?: () => void

  // Resume in the microphone click gesture to respect browser autoplay permissions.
  async prepare(): Promise<void> {
    this.context ??= new AudioContext()
    await this.context.resume()
  }

  // The entire WAV stays in RAM, then becomes unreachable when playback stops.
  async play(audio: string, volume: VoicePreferences['voice_volume']): Promise<void> {
    const context = this.context
    if (!context || context.state === 'closed') throw new Error('La sortie audio a été fermée.')
    const bytes = Uint8Array.from(atob(audio), (character) => character.charCodeAt(0))
    const buffer = await context.decodeAudioData(bytes.buffer)
    if (context.state !== 'running') throw new Error('Lecture bloquée par le navigateur. Réactive la sortie audio.')
    const source = context.createBufferSource()
    const gain = context.createGain()
    gain.gain.value = volume; source.buffer = buffer; source.connect(gain); gain.connect(context.destination)
    this.source = source
    await new Promise<void>((resolve) => { this.finish = resolve; source.onended = () => resolve(); source.start() })
    source.disconnect(); gain.disconnect(); this.stop()
  }

  // Stopping playback never cancels or deletes an already persisted model response.
  stop() {
    if (this.source) { this.source.onended = null; try { this.source.stop() } catch { /* Already ended. */ }; this.source.disconnect() }
    this.source = undefined; this.finish?.(); this.finish = undefined
    if (this.context && this.context.state !== 'closed') void this.context.close().catch(() => {})
    this.context = undefined
  }
}
