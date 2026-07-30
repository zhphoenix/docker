const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

export interface ChatRequestMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export interface ChatCompletionChunk {
  id: string
  object: string
  choices: {
    index: number
    delta: { content?: string; role?: string }
    finish_reason: string | null
  }[]
}

export interface StreamChatOptions {
  model?: string
  messages: ChatRequestMessage[]
  temperature?: number
  maxTokens?: number
  onChunk: (content: string) => void
  onDone: () => void
  onError: (error: Error) => void
  signal?: AbortSignal
}

export async function streamChatCompletion({
  model = 'qwen3',
  messages,
  temperature = 0.7,
  maxTokens = 4096,
  onChunk,
  onDone,
  onError,
  signal,
}: StreamChatOptions): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        messages,
        stream: true,
        temperature,
        max_tokens: maxTokens,
      }),
      signal,
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No response body')
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('data: ')) continue

        const data = trimmed.slice(6)
        if (data === '[DONE]') {
          onDone()
          return
        }

        try {
          const chunk: ChatCompletionChunk = JSON.parse(data)
          const content = chunk.choices[0]?.delta?.content
          if (content) {
            onChunk(content)
          }
        } catch {
          // skip malformed chunks
        }
      }
    }

    onDone()
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      onDone()
      return
    }
    onError(error instanceof Error ? error : new Error(String(error)))
  }
}
