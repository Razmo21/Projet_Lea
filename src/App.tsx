import { useState } from 'react'
import type { FormEvent } from 'react'

const responseMessage = "Léa n'est pas encore connectée à son modèle."

function App() {
  const [question, setQuestion] = useState('')
  const [response, setResponse] = useState('')

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setResponse(responseMessage)
  }

  return (
    <main>
      <section className="chat" aria-labelledby="page-title">
        <h1 id="page-title">Léa</h1>

        <form onSubmit={handleSubmit}>
          <label htmlFor="question">Votre question</label>
          <textarea
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Écrivez votre question"
            rows={5}
          />
          <button type="submit">Envoyer</button>
        </form>

        <section className="response" aria-live="polite" aria-label="Réponse">
          {response}
        </section>
      </section>
    </main>
  )
}

export default App
