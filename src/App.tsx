import { useState } from 'react'
import type { FormEvent } from 'react'

const backendUrl = 'http://127.0.0.1:8000/test-response'
const backendErrorMessage = 'Impossible de contacter le backend de Léa.'

type TestResponse = {
  answer: string
}

function App() {
  const [question, setQuestion] = useState('')
  const [response, setResponse] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    try {
      const backendResponse = await fetch(backendUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question }),
      })

      if (!backendResponse.ok) {
        throw new Error('Backend request failed')
      }

      const data: TestResponse = await backendResponse.json()
      setResponse(data.answer)
    } catch {
      setResponse(backendErrorMessage)
    }
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
