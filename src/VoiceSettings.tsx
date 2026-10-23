import { useEffect, useRef, useState } from 'react'
import type { VoicePreferences } from './preferences'
import { voiceRequest } from './voice'
import type { VoiceStatus } from './voice'

type Props = { value: VoicePreferences; onChange: (value: VoicePreferences) => void; disabled: boolean }

// Only actual installed voices and devices exposed by the browser are offered.
export default function VoiceSettings({ value, onChange, disabled }: Props) {
  const [status, setStatus] = useState<VoiceStatus | null>(null)
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  const [error, setError] = useState('')
  const [scanning, setScanning] = useState(false)
  const alive = useRef(true)
  const selectedVoice = status?.voices.find((voice) => voice.id === value.voice_id)
  useEffect(() => {
    alive.current = true
    const controller = new AbortController()
    void voiceRequest<VoiceStatus>('status', undefined, controller.signal).then(setStatus).catch(() => {
      if (!controller.signal.aborted) setError('État des moteurs vocaux indisponible. Aucun moteur n’a été démarré.')
    })
    return () => { alive.current = false; controller.abort() }
  }, [])

  // Device labels require explicit permission; immediately release the temporary stream.
  async function scan() {
    if (scanning) return
    setScanning(true); setError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((track) => track.stop())
      if (!alive.current) return
      const found = await navigator.mediaDevices.enumerateDevices()
      if (alive.current) setDevices(found.filter((device) => device.kind === 'audioinput' && device.deviceId))
    } catch { if (alive.current) setError('Impossible de lister les microphones : vérifie le branchement et l’autorisation du navigateur.') }
    finally { if (alive.current) setScanning(false) }
  }
  // All fields remain draft until the existing versioned Validate transaction succeeds.
  function change(fields: Partial<VoicePreferences>) { onChange({ ...value, ...fields }) }
  return <fieldset className="settings-group" disabled={disabled}>
    <legend>Microphone et voix locale</legend>
    <div className="voice-settings">
      <p className="settings-note">
        {status ? `STT ${status.stt_engine ?? ''} : ${status.stt ? 'installé' : 'indisponible'} ; TTS local : ${status.tts ? `${status.voices.length} voix disponible${status.voices.length > 1 ? 's' : ''}` : 'indisponible'}.` : error ? 'Installation non vérifiée.' : 'Vérification de l’installation…'}
      </p>

      <div className="settings-field">
        <label htmlFor="voice-language">Langue de transcription</label>
        <select id="voice-language" value={value.voice_language} onChange={(event) => change({ voice_language: event.target.value as 'fr' | 'en' })}>
          <option value="fr">Français</option>
          <option value="en">Anglais</option>
        </select>
      </div>

      <div className="settings-field">
        <label htmlFor="voice-microphone">Microphone</label>
        <select id="voice-microphone" value={value.voice_microphone_id} onChange={(event) => change({ voice_microphone_id: event.target.value })}>
          <option value="">Microphone par défaut du système</option>
          {value.voice_microphone_id && !devices.some((device) => device.deviceId === value.voice_microphone_id) && <option value={value.voice_microphone_id}>Choix mémorisé — disponibilité non confirmée</option>}
          {devices.map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `Microphone ${index + 1}`}</option>)}
        </select>
        <button type="button" className="secondary-button" disabled={scanning} onClick={() => void scan()}>
          Autoriser et lister les microphones
        </button>
        <p className="settings-note">Aucune écoute permanente. Pas de réglage artificiel de sensibilité.</p>
      </div>

      <label className="resource-option">
        <input type="checkbox" checked={value.voice_enabled} onChange={(event) => change({ voice_enabled: event.target.checked })} />
        Lire les réponses en mode conversation vocale
      </label>

      <div className="settings-field">
        <label htmlFor="voice-id">Voix française</label>
        <select id="voice-id" value={value.voice_id} onChange={(event) => change({ voice_id: event.target.value })}>
          {value.voice_id && !status && <option value={value.voice_id}>Choix mémorisé — disponibilité non confirmée</option>}
          {value.voice_id && status && !selectedVoice && <option value={value.voice_id}>Voix mémorisée indisponible</option>}
          {status?.voices.map((voice) => <option key={voice.id} value={voice.id}>{voice.label}</option>)}
        </select>
      </div>

      <div className="settings-field">
        <label htmlFor="voice-volume">Volume : {Math.round(value.voice_volume * 100)} %</label>
        <input id="voice-volume" type="range" min="0" max="1" step="0.05" value={value.voice_volume} onChange={(event) => change({ voice_volume: Number(event.target.value) })} />
      </div>

      <div className="settings-field">
        <label htmlFor="voice-rate">Vitesse : {value.voice_rate.toFixed(2)}×</label>
        <input id="voice-rate" type="range" min="0.75" max="1.5" step="0.05" value={value.voice_rate} disabled={!selectedVoice?.supports_rate} onChange={(event) => change({ voice_rate: Number(event.target.value) })} />
        {selectedVoice && !selectedVoice.supports_rate && <p className="settings-note">Cette voix utilise une vitesse fixe à 1×. Le réglage mémorisé reste disponible pour SIWIS — Voix classique.</p>}
      </div>

      {error && <p className="status-error" role="status">{error}</p>}
    </div>
  </fieldset>
}
