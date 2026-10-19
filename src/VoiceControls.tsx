import { useEffect, useRef, useState } from 'react'
import { audioBase64, effectiveVoiceRate, MicrophoneCapture, VoicePlayback, voiceRequest } from './voice'
import type { VoiceStatus } from './voice'
import type { Preferences } from './preferences'

type Phase = 'idle' | 'permission' | 'recording' | 'transcribing' | 'thinking' | 'synthesizing' | 'speaking'
type Props = {
  preferences: Preferences | null; contextKey: string; ready: boolean; blocked: boolean; hidden: boolean
  onMode: (open: boolean) => void
  onDictated: (text: string) => void
  onSend: (text: string, signal: AbortSignal) => Promise<{ text: string; review?: boolean; notice?: string }>
}
const labels: Record<Phase, string> = { idle: 'Prête pour une intervention.', permission: 'Autorisation du microphone…', recording: 'Écoute… Clique à nouveau pour terminer.', transcribing: 'Transcription locale…', thinking: 'Léa traite la demande…', synthesizing: 'Préparation de la voix…', speaking: 'Léa parle…' }

// This view owns audio only. App retains conversations, profiles and OpenHands decisions.
export default function VoiceControls(props: Props) {
  const [open, setOpen] = useState(false)
  const [phase, setPhase] = useState<Phase>('idle')
  const [message, setMessage] = useState('')
  const [review, setReview] = useState(false)
  const capture = useRef<MicrophoneCapture | null>(null)
  const playback = useRef<VoicePlayback | null>(null)
  const request = useRef<AbortController | null>(null)
  const epoch = useRef(0)
  const lock = useRef<Phase>('idle')
  const callbacks = useRef({ onDictated: props.onDictated, onSend: props.onSend })
  const options = useRef(props.preferences)

  // One cancellation path handles navigation, core/profile changes and unmount.
  function cancel() {
    epoch.current++; request.current?.abort(); request.current = null
    capture.current?.cancel(); capture.current = null
    playback.current?.stop(); playback.current = null
    lock.current = 'idle'; setPhase('idle')
  }
  useEffect(() => {
    if (lock.current !== 'idle') setMessage('Contexte modifié : audio annulé. Vérifie l’historique si une demande avait déjà été envoyée.')
    cancel()
  }, [props.contextKey, props.hidden])
  useEffect(() => cancel, [])
  useEffect(() => {
    const leave = () => cancel()
    window.addEventListener('pagehide', leave)
    return () => window.removeEventListener('pagehide', leave)
  }, [])

  // Keep the dedicated view text-free: only states and safety notices are rendered.
  function close() {
    const wasThinking = lock.current === 'thinking'
    cancel(); setOpen(false); props.onMode(false); setReview(false)
    setMessage(wasThinking ? 'Le traitement lancé peut continuer. Consulte son état dans l’historique ou le panneau OpenHands ; il n’est pas relancé.' : '')
  }
  function transition(value: Phase) { lock.current = value; setPhase(value) }

  // The second click alone submits a vocal turn; dictation only appends its result.
  async function microphone() {
    if (lock.current !== 'idle' && lock.current !== 'recording') return
    if (lock.current === 'idle') {
      if (!props.preferences || props.blocked || (open && !props.ready)) return
      const ticket = ++epoch.current
      callbacks.current = { onDictated: props.onDictated, onSend: props.onSend }
      options.current = props.preferences
      setMessage(''); setReview(false); transition('permission')
      const mic = new MicrophoneCapture(); capture.current = mic
      try {
        if (open && props.preferences.voice_enabled) {
          playback.current = new VoicePlayback(); await playback.current.prepare()
        }
        if (ticket !== epoch.current) return
        await mic.start(props.preferences.voice_microphone_id, (failure) => {
          if (ticket === epoch.current) { cancel(); setMessage(failure.message) }
        })
        if (ticket === epoch.current) transition('recording')
      } catch (failure) {
        if (ticket === epoch.current) { cancel(); setMessage(failure instanceof Error ? failure.message : 'Microphone indisponible.') }
      }
      return
    }
    const ticket = epoch.current
    const preferences = options.current!
    const controller = new AbortController(); request.current = controller
    let outcome = ''
    transition('transcribing')
    try {
      const bytes = await capture.current!.stop()
      if (ticket !== epoch.current) return
      const result = await voiceRequest<{ text: string }>('transcribe', { audio: audioBase64(bytes), language: preferences.voice_language }, controller.signal)
      if (ticket !== epoch.current) return
      if (typeof result.text !== 'string' || !result.text.trim()) throw new Error('Aucune transcription exploitable.')
      if (!open) { callbacks.current.onDictated(result.text); setMessage('Dictée ajoutée au brouillon. Relis puis envoie manuellement.'); return }
      transition('thinking')
      const answer = await callbacks.current.onSend(result.text, controller.signal)
      if (ticket !== epoch.current) return
      setReview(Boolean(answer.review))
      // A run's safety state stays visible even if speech is disabled or fails.
      // This is a status notice, never the hidden conversation text.
      outcome = answer.notice ?? ''
      setMessage(outcome)
      if (!preferences.voice_enabled) { setMessage(`${outcome} Réponse enregistrée ; lecture désactivée dans les paramètres.`.trim()); return }
      transition('synthesizing')
      const status = await voiceRequest<VoiceStatus>('status', undefined, controller.signal)
      const selectedVoice = status.voices.find((voice) => voice.id === preferences.voice_id)
      if (!status.tts || !selectedVoice) throw new Error('La voix choisie est indisponible. La réponse reste dans l’historique ; vérifie les paramètres ou sélectionne une autre voix.')
      // Pocket TTS exposes no truthful speed control; retain the saved Piper rate without faking it.
      const effectiveRate = effectiveVoiceRate(selectedVoice, preferences.voice_rate)
      const sound = await voiceRequest<{ audio: string; partial: boolean }>('speak', { text: answer.text, voice_id: selectedVoice.id, rate: effectiveRate }, controller.signal)
      if (ticket !== epoch.current) return
      if (sound.partial) setMessage(`${outcome} Lecture partielle ; contenu complet dans l’historique.`.trim())
      transition('speaking')
      await playback.current!.play(sound.audio, preferences.voice_volume)
    } catch (failure) {
      if (ticket === epoch.current) setMessage(`${outcome} ${failure instanceof Error ? failure.message : 'Le traitement vocal a échoué.'}`.trim())
    } finally {
      if (ticket === epoch.current) { cancel() }
    }
  }

  return <section className={open ? 'chat' : 'voice-controls'} hidden={props.hidden} aria-label={open ? 'Conversation vocale' : 'Commandes vocales'}>
    {open && <h1>Conversation vocale</h1>}
    {open && !props.ready && <p role="status">Démarre un profil IA dans l’interface classique avant de parler à Léa.</p>}
    <div className="page-header">
      <button type="button" onClick={() => void microphone()} disabled={review || props.blocked || !props.preferences || (open && !props.ready) || !['idle', 'recording'].includes(phase)}>
        {phase === 'recording' ? (open ? 'Terminer et envoyer' : 'Terminer la dictée') : (open ? 'Parler à Léa' : 'Dicter au microphone')}
      </button>
      {!open && <button type="button" className="secondary-button" disabled={phase !== 'idle' || props.blocked} onClick={() => { setOpen(true); props.onMode(true); setMessage('') }}>Conversation vocale</button>}
      {phase !== 'idle' && <button type="button" className="secondary-button" onClick={() => { const thinking = phase === 'thinking'; cancel(); setMessage(thinking ? 'Traitement déjà lancé : vérifie son résultat dans l’interface classique.' : 'Audio arrêté.') }}> {phase === 'speaking' ? 'Arrêter la lecture' : 'Annuler l’audio'}</button>}
      {open && <button type="button" className="secondary-button" onClick={close}>{review ? 'Examiner le run et le diff' : 'Retour aux conversations'}</button>}
    </div>
    {(open || phase !== 'idle') && <p role="status">{labels[phase]}</p>}
    {review && <p role="status">Validation visuelle obligatoire : examine le résultat et les changements avant d’accepter ou de restaurer. Aucune décision automatique.</p>}
    {message && <p role="status">{message}</p>}
  </section>
}
