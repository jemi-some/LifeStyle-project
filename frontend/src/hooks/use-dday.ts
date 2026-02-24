import { useCallback, useState } from 'react'
import { supabase } from '../lib/supabase'

export type DdayResult = {
  name: string
  movie_title: string
  release_date: string
  dday: string
  waiting_count?: number
  message?: string
  distributor?: string | null
  director?: string | null
  cast?: string[] | null
  genre?: string[] | null
  poster_url?: string | null
  content_type?: string
}

type HistoryEntry = {
  id: string
  author: 'user' | 'assistant'
  message: string
  pendingConfirmation?: Record<string, unknown>
}

type StageKind = 'analysis' | 'tool_started' | 'tool_result'

type StageEntry = {
  id: string
  message: string
  kind: StageKind
}

const normalizeList = (value: string | string[] | null | undefined): string[] | null => {
  if (Array.isArray(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim()) {
    return value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
  }
  return null
}

type StageGroups = Record<string, StageEntry[]>

export function useDday() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<DdayResult | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stageGroups, setStageGroups] = useState<StageGroups>({})

  const handleConfirm = useCallback(async (messageId: string, payload: Record<string, unknown>) => {
    setIsLoading(true)
    setError(null)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      const response = await fetch('/dday/confirm', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(session ? { Authorization: `Bearer ${session.access_token}` } : {})
        },
        body: JSON.stringify(payload),
      })
      if (!response.ok) {
        throw new Error('등록에 실패했습니다.')
      }
      const data = await response.json()

      const normalizedResult: DdayResult = {
        name: String(data.name ?? payload.query_name),
        movie_title: String(data.movie_title ?? ''),
        release_date: String(data.release_date ?? ''),
        dday: String(data.dday ?? ''),
        waiting_count: typeof data.waiting_count === 'number' ? data.waiting_count : undefined,
        message: typeof data.message === 'string' ? data.message : undefined,
        distributor: typeof data.distributor === 'string' ? data.distributor : null,
        director: typeof data.director === 'string' ? data.director : null,
        cast: normalizeList(data.cast as string | string[] | null | undefined),
        genre: normalizeList(data.genre as string | string[] | null | undefined),
        poster_url: typeof data.poster_url === 'string' ? data.poster_url : null,
        content_type: typeof data.content_type === 'string' ? data.content_type : 'movie',
      }
      setResult(normalizedResult)

      setHistory((prev) => prev.map(entry => {
        if (entry.id === messageId) {
          return { ...entry, message: entry.message + '\n\n✅ 디데이로 등록되었습니다.', pendingConfirmation: undefined }
        }
        return entry
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : '오류가 발생했습니다.')
    } finally {
      setIsLoading(false)
    }
  }, [])

  const handleCancel = useCallback((messageId: string) => {
    setHistory((prev) => prev.map(entry => {
      if (entry.id === messageId) {
        return { ...entry, message: entry.message + '\n\n❌ 등록을 취소했습니다.', pendingConfirmation: undefined }
      }
      return entry
    }))
  }, [])

  const handleSubmit = useCallback(async () => {
    const normalized = query.trim()
    if (!normalized) return

    setQuery('')
    setIsLoading(true)
    setError(null)

    const requestId = crypto.randomUUID()
    setStageGroups((prev) => ({ ...prev, [requestId]: [] }))

    setHistory((prev) => [
      ...prev,
      { id: requestId, author: 'user', message: normalized },
    ])

    const upsertAssistantMessage = (message: string) => {
      if (!message.trim()) return
      setHistory((prev) => {
        const next = [...prev]
        const lastIdx = next.length - 1
        if (lastIdx >= 0 && next[lastIdx].author === 'assistant') {
          next[lastIdx] = { ...next[lastIdx], message }
          return next
        }
        return [...next, { id: crypto.randomUUID(), author: 'assistant', message }]
      })
    }

    const parseEvent = (raw: string) => {
      const lines = raw.split('\n')
      let event = 'message'
      const dataLines: string[] = []
      for (const line of lines) {
        if (line.startsWith('event:')) {
          event = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trim())
        }
      }
      const dataStr = dataLines.join('\n')
      let payload: Record<string, unknown> = {}
      if (dataStr) {
        try {
          payload = JSON.parse(dataStr)
        } catch {
          payload = { message: dataStr }
        }
      }
      return { event, payload }
    }

    const applyDdayPayload = (payload: Record<string, unknown>) => {
      const normalizedResult: DdayResult = {
        name: String(payload.name ?? normalized),
        movie_title: String(payload.movie_title ?? ''),
        release_date: String(payload.release_date ?? ''),
        dday: String(payload.dday ?? ''),
        message: typeof payload.message === 'string' ? payload.message : undefined,
        distributor: typeof payload.distributor === 'string' ? payload.distributor : null,
        director: typeof payload.director === 'string' ? payload.director : null,
        cast: normalizeList(payload.cast as string | string[] | null | undefined),
        genre: normalizeList(payload.genre as string | string[] | null | undefined),
        poster_url: typeof payload.poster_url === 'string' ? payload.poster_url : null,
        content_type: typeof payload.content_type === 'string' ? payload.content_type : 'movie',
      }
      setResult(normalizedResult)
    }

    const appendStage = (kind: StageKind, message: string) => {
      if (!message) return
      setStageGroups((prev) => {
        const target = prev[requestId] ?? []
        if (target.length > 0 && target[target.length - 1].kind === kind) {
          const updated = [...target]
          updated[updated.length - 1] = { ...updated[updated.length - 1], message }
          return { ...prev, [requestId]: updated }
        }
        return {
          ...prev,
          [requestId]: [...target, { id: crypto.randomUUID(), kind, message }],
        }
      })
    }

    try {
      const { data: { session } } = await supabase.auth.getSession()
      const response = await fetch('/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(session ? { Authorization: `Bearer ${session.access_token}` } : {})
        },
        body: JSON.stringify({ query: normalized }),
      })

      if (!response.ok || !response.body) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || '대화를 시작할 수 없습니다.')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let endReached = false

      while (!endReached) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let boundary
        while ((boundary = buffer.indexOf('\n\n')) !== -1) {
          const chunk = buffer.slice(0, boundary)
          buffer = buffer.slice(boundary + 2)
          if (!chunk.trim()) continue
          const { event, payload } = parseEvent(chunk)
          switch (event) {
            case 'analysis':
            case 'tool_started':
            case 'tool_result':
              if (typeof payload.message === 'string') {
                appendStage(event, payload.message)
              }
              break
            case 'token':
              if (typeof payload.message === 'string') {
                upsertAssistantMessage(payload.message)
              }
              break
            case 'assistant_message':
              if (typeof payload.message === 'string') {
                upsertAssistantMessage(payload.message)
              }
              break
            case 'dday':
              applyDdayPayload(payload)
              break
            case 'confirmation_required':
              setHistory((prev) => {
                const next = [...prev]
                const lastIdx = next.length - 1
                if (lastIdx >= 0 && next[lastIdx].author === 'assistant') {
                  next[lastIdx] = { ...next[lastIdx], pendingConfirmation: payload }
                  return next
                }
                return [...next, { id: crypto.randomUUID(), author: 'assistant', message: '', pendingConfirmation: payload }]
              })
              break
            case 'error':
              if (typeof payload.message === 'string') {
                upsertAssistantMessage(payload.message)
                setError(payload.message)
              }
              break
            case 'end':
              endReached = true
              break
            default:
              break
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.'
      upsertAssistantMessage(message)
      setError(message)
    } finally {
      setIsLoading(false)
      setQuery('')
    }
  }, [query])

  return {
    query,
    setQuery,
    result,
    history,
    stageGroups,
    isLoading,
    error,
    handleSubmit,
    handleConfirm,
    handleCancel,
  }
}
