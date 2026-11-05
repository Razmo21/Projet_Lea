import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import Icon from './Icon'
import {
  audioBase64,
  effectiveVoiceRate,
  MicrophoneCapture,
  VoicePlayback,
  voiceRequest,
} from '../lib/voice'
import type { VoiceStatus } from '../lib/voice'
import type { Preferences } from '../lib/preferences'
import { shortNotice } from '../lib/notices'

type Phase =
  | 'idle'
  | 'permission'
  | 'recording'
  | 'transcribing'
  | 'thinking'
  | 'synthesizing'
  | 'speaking'
type Props = {
  composerSendButton: ReactNode
  ephemeral?: boolean
  controlsHost: HTMLElement | null
  preferences: Preferences | null
  contextKey: string
  ready: boolean
  blocked: boolean
  hidden: boolean
  onMode: (open: boolean) => void
  onDictated: (text: string) => void
  onStopResponse: () => Promise<void>
  stopping: boolean
  onSend: (
    text: string,
    signal: AbortSignal,
  ) => Promise<{ text: string; review?: boolean; notice?: string }>
}
const labels: Record<Phase, string> = {
  idle: 'Prête pour une intervention.',
  permission: 'Autorisation du microphone…',
  recording: 'Écoute… Clique à nouveau pour terminer.',
  transcribing: 'Transcription locale…',
  thinking: 'Léa traite la demande…',
  synthesizing: 'Préparation de la voix…',
  speaking: 'Léa parle…',
}

// Cette vue gère seulement l'audio ; App conserve les conversations et les décisions OpenHands.
export default function VoiceControls(props: Props) {
  const [open, setOpen] = useState(false)
  const [phase, setPhase] = useState<Phase>('idle')
  const [message, setMessage] = useState('')
  const [runNotice, setRunNotice] = useState('')
  const [review, setReview] = useState(false)
  const title = useRef<HTMLHeadingElement>(null)
  const opener = useRef<HTMLButtonElement>(null)
  const capture = useRef<MicrophoneCapture | null>(null)
  const playback = useRef<VoicePlayback | null>(null)
  const request = useRef<AbortController | null>(null)
  const epoch = useRef(0)
  const lock = useRef<Phase>('idle')
  const callbacks = useRef({
    onDictated: props.onDictated,
    onSend: props.onSend,
  })
  const options = useRef(props.preferences)

  // Le clavier suit le changement de vue, sans ouvrir le microphone.
  useEffect(() => {
    if (open) title.current?.focus()
  }, [open])

  // Le même chemin libère l'audio lors d'une navigation, d'un changement de profil ou du démontage.
  function cancel() {
    epoch.current++
    request.current?.abort()
    request.current = null
    capture.current?.cancel()
    capture.current = null
    playback.current?.stop()
    playback.current = null
    lock.current = 'idle'
    setPhase('idle')
  }

  useEffect(() => {
    setRunNotice('')
    if (lock.current !== 'idle') {
      setMessage(
        'Contexte modifié : audio annulé. Vérifie l’historique si une demande avait déjà été envoyée.',
      )
    }
    cancel()
  }, [props.contextKey, props.hidden])

  useEffect(() => cancel, [])

  useEffect(() => {
    const leave = () => cancel()
    window.addEventListener('pagehide', leave)
    return () => window.removeEventListener('pagehide', leave)
  }, [])

  // Le panneau dédié affiche les états et les avis de sécurité, sans dupliquer la réponse.
  function close() {
    const wasThinking = lock.current === 'thinking'
    cancel()
    setOpen(false)
    props.onMode(false)
    window.requestAnimationFrame(() => opener.current?.focus())
    setReview(false)
    setRunNotice('')
    setMessage(
      wasThinking
        ? 'Le traitement peut continuer en arrière-plan'
        : '',
    )
  }

  function transition(value: Phase) {
    lock.current = value
    setPhase(value)
  }

  // Seul le second clic envoie un tour vocal ; la dictée ajoute son texte au brouillon.
  async function microphone() {
    if (lock.current !== 'idle' && lock.current !== 'recording') return

    if (lock.current === 'idle') {
      if (!props.preferences || props.blocked || (open && !props.ready)) return
      const ticket = ++epoch.current
      callbacks.current = { onDictated: props.onDictated, onSend: props.onSend }
      options.current = props.preferences
      setMessage('')
      setRunNotice('')
      setReview(false)
      transition('permission')
      const mic = new MicrophoneCapture()
      capture.current = mic
      try {
        if (open && props.preferences.voice_enabled) {
          playback.current = new VoicePlayback()
          await playback.current.prepare()
        }
        if (ticket !== epoch.current) return
        await mic.start(props.preferences.voice_microphone_id, (failure) => {
          if (ticket === epoch.current) {
            cancel()
            setMessage(failure.message)
          }
        })
        if (ticket === epoch.current) transition('recording')
      } catch (failure) {
        if (ticket === epoch.current) {
          cancel()
          setMessage(
            failure instanceof Error
              ? failure.message
              : 'Microphone indisponible.',
          )
        }
      }
      return
    }

    const ticket = epoch.current
    const preferences = options.current!
    const controller = new AbortController()
    request.current = controller
    transition('transcribing')
    try {
      const bytes = await capture.current!.stop()
      if (ticket !== epoch.current) return
      const result = await voiceRequest<{ text: string }>(
        'transcribe',
        { audio: audioBase64(bytes), language: preferences.voice_language },
        controller.signal,
      )
      if (ticket !== epoch.current) return
      if (typeof result.text !== 'string' || !result.text.trim())
        throw new Error('Aucune transcription exploitable.')
      if (!open) {
        callbacks.current.onDictated(result.text)
        setMessage(
          'Dictée ajoutée au brouillon',
        )
        return
      }

      transition('thinking')
      const answer = await callbacks.current.onSend(
        result.text,
        controller.signal,
      )
      if (ticket !== epoch.current) return
      setReview(Boolean(answer.review))
      // L'état de sécurité d'un run reste visible si la lecture est désactivée ou échoue.
      // Ce message d'état ne duplique pas le contenu de la conversation.
      // L'état du run et un éventuel problème audio gardent chacun leur courte phrase.
      setRunNotice(answer.notice ?? '')
      setMessage('')
      if (!preferences.voice_enabled) {
        setMessage('Lecture vocale désactivée')
        return
      }

      transition('synthesizing')
      const status = await voiceRequest<VoiceStatus>(
        'status',
        undefined,
        controller.signal,
      )
      const selectedVoice = status.voices.find(
        (voice) => voice.id === preferences.voice_id,
      )
      if (!status.tts || !selectedVoice) {
        throw new Error(
          'Voix choisie indisponible',
        )
      }
      // Pocket TTS ne gère pas la vitesse ; le réglage Piper sauvegardé reste intact.
      const effectiveRate = effectiveVoiceRate(
        selectedVoice,
        preferences.voice_rate,
      )
      const sound = await voiceRequest<{ audio: string; partial: boolean }>(
        'speak',
        { text: answer.text, voice_id: selectedVoice.id, rate: effectiveRate },
        controller.signal,
      )
      if (ticket !== epoch.current) return
      if (sound.partial)
        setMessage(
          'Lecture audio partielle',
        )
      transition('speaking')
      await playback.current!.play(sound.audio, preferences.voice_volume)
    } catch (failure) {
      if (ticket === epoch.current) {
        setMessage(
          failure instanceof Error ? failure.message : 'Le traitement vocal a échoué.',
        )
      }
    } finally {
      if (ticket === epoch.current) cancel()
    }
  }

  const microphoneLabel =
    phase === 'recording'
      ? open
        ? 'Terminer et envoyer'
        : 'Terminer la dictée'
      : open
        ? 'Parler à Léa'
        : 'Dictée'
  const cancelLabel =
    phase === 'thinking' ? 'Arrêter la réponse'
      : phase === 'speaking' ? 'Arrêter la lecture' : 'Annuler l’audio'

  const controls = (
    <section
      className={open ? 'chat voice-view' : 'voice-controls'}
      hidden={props.hidden}
      aria-label={open ? 'Conversation vocale' : 'Commandes vocales'}
    >
      {open && (
        <h1 ref={title} tabIndex={-1}>
          Conversation vocale
        </h1>
      )}
      {open && (
        <div
          className="voice-orb"
          data-active={phase !== 'idle'}
          aria-hidden="true"
        >
          <Icon name="voice" />
        </div>
      )}
      {open && !props.ready && (
        <p role="status">
          Choisissez un modèle pour parler
        </p>
      )}
      <div className="page-header">
        <button
          type="button"
          className={open ? undefined : 'icon-button'}
          aria-label={microphoneLabel}
          title={microphoneLabel}
          aria-pressed={phase === 'recording'}
          onClick={() => void microphone()}
          disabled={
            review ||
            props.blocked ||
            !props.preferences ||
            (open && !props.ready) ||
            !['idle', 'recording'].includes(phase)
          }
        >
          <Icon name={phase === 'recording' ? 'stop' : 'mic'} />
          {open && microphoneLabel}
        </button>
        {/* Le même emplacement reçoit l'envoi du brouillon ou l'ouverture vocale. */}
        {!open &&
          (props.composerSendButton ?? (
            <button
              ref={opener}
              type="button"
              className="icon-button send-button"
              aria-label="Conversation vocale"
              title="Conversation vocale"
              disabled={phase !== 'idle' || props.blocked}
              onClick={() => {
                setOpen(true)
                props.onMode(true)
                setMessage('')
                setRunNotice('')
              }}
            >
              <Icon name="voice" />
            </button>
          ))}
        {phase !== 'idle' && (
          <button
            type="button"
            className={open ? 'secondary-button' : 'icon-button'}
            aria-label={cancelLabel}
            title={cancelLabel}
            disabled={phase === 'thinking' && props.stopping}
            onClick={() => {
              const thinking = phase === 'thinking'
              // L'arrêt du modèle appartient à App ; attendre son résultat garde l'historique cohérent.
              if (thinking) {
                void props.onStopResponse()
                return
              }
              cancel()
              setMessage('Audio arrêté.')
            }}
          >
            {open ? cancelLabel : <Icon name="close" />}
          </button>
        )}
        {open && (
          <button type="button" className="secondary-button" onClick={close}>
            {review ? 'Examiner le run et le diff' : 'Retour aux conversations'}
          </button>
        )}
      </div>
      {(open || phase !== 'idle') && <p role="status">{labels[phase]}</p>}
      {review && (
        <p role="status">
          Examinez les changements avant toute décision
        </p>
      )}
      {runNotice && <p role="status">{shortNotice(runNotice, 'task')}</p>}
      {message && <p role="status">{shortNotice(message, 'voice')}</p>}
    </section>
  )

  // Seules les commandes compactes rejoignent la saisie. Le contrôleur reste monté
  // hors de la vue masquée pour conserver la capture, l'annulation et le mode vocal.
  return open
    ? controls
    : props.controlsHost
      ? createPortal(controls, props.controlsHost)
      : null
}
