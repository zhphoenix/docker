const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

export class ApiError extends Error {
  status: number
  type: string

  constructor(status: number, type: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.type = type
  }
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`

  const response = await fetch(url, {
    headers: {
      // FormData 由浏览器自动设置 multipart boundary，不能手动指定 Content-Type
      ...(options?.body instanceof FormData
        ? {}
        : { 'Content-Type': 'application/json' }),
      ...options?.headers,
    },
    ...options,
  })

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`
    let errorType = 'server_error'

    try {
      const errorBody = await response.json()
      if (errorBody.error) {
        errorMessage = errorBody.error.message || errorMessage
        errorType = errorBody.error.type || errorType
      }
    } catch {
      // ignore parse errors
    }

    throw new ApiError(response.status, errorType, errorMessage)
  }

  return response.json()
}
