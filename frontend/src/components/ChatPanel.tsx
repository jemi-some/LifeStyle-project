import { type FormEvent, useEffect, useRef } from 'react'
import sendIcon from '../assets/send.svg'

const STARTER_QUESTIONS = [
  '어벤져스: 둠스데이 개봉일',
  '아바타 개봉일',
  '해리 포터 드라마 개봉일',
  '웬즈데이 개봉일',
]

type Props = {
  query: string
  setQuery: (value: string) => void
  isLoading: boolean
  error: string | null
  onSubmit: (directQuery?: string) => Promise<void>
  history: { id: string; author: 'user' | 'assistant'; message: string; pendingConfirmation?: Record<string, unknown> }[]
  stageGroups: Record<string, { id: string; message: string; kind: 'analysis' | 'tool_started' | 'tool_result' }[]>
  onConfirm: (messageId: string, payload: Record<string, unknown>) => void
  onCancel: (messageId: string) => void
}

export function ChatPanel({ query, setQuery, isLoading, error, onSubmit, history, stageGroups, onConfirm, onCancel }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const historyContainerRef = useRef<HTMLDivElement | null>(null)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    await onSubmit()
    inputRef.current?.focus()
  }

  useEffect(() => {
    const container = historyContainerRef.current

    if (!container) return
    container.scrollTop = container.scrollHeight
  }, [history, stageGroups])

  useEffect(() => {
    if (!isLoading) {
      inputRef.current?.focus()
    }
  }, [isLoading])

  const conversationNodes: React.ReactNode[] = []


  history.forEach((entry) => {
    conversationNodes.push(
      <div key={entry.id} className={`bubble ${entry.author}`}>
        <div className="bubble-content" style={{ whiteSpace: 'pre-wrap' }}>{entry.message}</div>
        {entry.pendingConfirmation && (
          <div className="confirmation-actions">
            <p className="confirmation-text">디데이로 등록할까요?</p>
            <div className="button-group">
              <button
                className="confirm-button"
                onClick={() => onConfirm(entry.id, entry.pendingConfirmation!)}
                disabled={isLoading}
              >
                확인
              </button>
              <button
                className="cancel-button"
                onClick={() => onCancel(entry.id)}
                disabled={isLoading}
              >
                취소
              </button>
            </div>
          </div>
        )}
      </div>
    )
    if (entry.author === 'user') {
      const group = stageGroups[entry.id]
      if (group && group.length > 0) {
        conversationNodes.push(
          <div key={`stage-${entry.id}`} className="stage-list" aria-live="polite">
            {group.map((stage) => (
              <div key={stage.id} className="stage-item">
                <span className="stage-dot" />
                <span>{stage.message}</span>
              </div>
            ))}
          </div>
        )
      }
    }
  })

  return (
    <div className="chat-panel-inner">
      <div className="chat-history" ref={historyContainerRef}>
        {history.length === 0 && (
          <div className="starter-questions">
            <p className="starter-label">이런 걸 물어볼 수 있어요</p>
            <div className="starter-grid">
              {STARTER_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  className="starter-card"
                  onClick={() => onSubmit(q)}
                  disabled={isLoading}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {conversationNodes}
      </div>

      <form className="chat-input" onSubmit={handleSubmit}>
        <div className="input-block">
          <div className="input-wrapper">
            <input
              type="text"
              placeholder="예: 프로젝트 헤일메리 개봉일"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={isLoading}
              ref={inputRef}
            />
            <button type="submit" className="send-button" disabled={isLoading}>
              <img src={sendIcon} alt="send" />
            </button>
          </div>
          {error && <p className="error-text">{error}</p>}
          <p className="chat-disclaimer">AI는 실수를 할 수 있습니다. 중요한 정보는 재차 확인하세요.</p>
        </div>
      </form>
    </div>
  )
}

