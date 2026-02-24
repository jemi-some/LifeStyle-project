import { useCallback, useEffect, useState } from 'react'
import type { DdayResult } from '../hooks/use-dday'
import { supabase } from '../lib/supabase'
import { SharedDdayCard } from './SharedDdayCard'

type Props = {
  result: DdayResult | null
  isLoading: boolean
}

const menus = [
  { id: 'shared', label: '공유 디데이' },
  { id: 'my-dday', label: '즐겨찾기' },
  { id: 'records', label: '내 기록' },
  { id: 'settings', label: '설정' },
]

export function DdayPanel({ result, isLoading }: Props) {
  const [activeMenu, setActiveMenu] = useState('shared')
  const [sharedList, setSharedList] = useState<DdayResult[]>([])
  const [sharedLoading, setSharedLoading] = useState(false)
  const [sharedError, setSharedError] = useState<string | null>(null)

  const normalize = (
    raw: DdayResult & { cast?: string | string[] | null; genre?: string | string[] | null },
  ): DdayResult => ({
    ...raw,
    cast: typeof raw.cast === 'string' ? raw.cast.split(',').map((item) => item.trim()) : raw.cast ?? null,
    genre: typeof raw.genre === 'string' ? raw.genre.split(',').map((item) => item.trim()) : raw.genre ?? null,
  })

  const fetchShared = useCallback(async () => {
    try {
      setSharedLoading(true)
      setSharedError(null)
      const { data: { session } } = await supabase.auth.getSession()
      const res = await fetch('/dday', {
        headers: {
          ...(session ? { Authorization: `Bearer ${session.access_token}` } : {})
        }
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || '디데이 목록을 불러오지 못했어요.')
      }
      const data = (await res.json()) as Array<
        DdayResult & { cast?: string | string[] | null; genre?: string | string[] | null }
      >
      setSharedList(data.map(normalize))
    } catch (err) {
      const message = err instanceof Error ? err.message : '알 수 없는 오류'
      setSharedError(message)
    } finally {
      setSharedLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchShared()
  }, [fetchShared])

  useEffect(() => {
    if (result) {
      fetchShared()
    }
  }, [result, fetchShared])

  const renderShared = () => {
    const handleReact = (item: DdayResult) => {
      console.log('같이 기다려요 클릭', item.movie_title)
    }

    if (sharedLoading) {
      return <p className="dday-placeholder">공유 디데이를 불러오는 중...</p>
    }
    if (sharedError) {
      return <p className="error-text">{sharedError}</p>
    }
    if (sharedList.length === 0) {
      return <p className="dday-placeholder">아직 공유된 디데이가 없어요.</p>
    }
    return (
      <div className="shared-list">
        {sharedList.map((item) => (
          <SharedDdayCard key={item.name} item={item} onReact={handleReact} />
        ))}
      </div>
    )
  }

  const renderFavorite = () => {
    if (isLoading) {
      return <p className="dday-placeholder">디데이를 불러오는 중...</p>
    }
    if (!result) {
      return (
        <div className="dday-placeholder">
          <p>디데이를 기록하면 이곳에서 확인할 수 있어요.</p>
        </div>
      )
    }
    const typeLabel = result.content_type === 'tv' ? '드라마' : '영화'
    return (
      <div className="dday-card">
        <div className="dday-header-row">
          <p className="dday-label">선택한 디데이</p>
          <span className="content-type-pill">{typeLabel}</span>
          {result.waiting_count && (
            <span className="wait-pill">👥 {result.waiting_count}명이 기다려요</span>
          )}
        </div>
        <h2>{result.movie_title}</h2>
        <p className="release-date">개봉일 {result.release_date}</p>
        <div className="dday-value">{result.dday}</div>
        {result.message && <p className="message">{result.message}</p>}
        <div className="meta">
          {result.director && (
            <p>
              <span>감독</span>
              {result.director}
            </p>
          )}
          {result.distributor && (
            <p>
              <span>배급</span>
              {result.distributor}
            </p>
          )}
          {result.cast && result.cast.length > 0 && (
            <p>
              <span>출연</span>
              {result.cast.join(', ')}
            </p>
          )}
          {result.genre && result.genre.length > 0 && (
            <p>
              <span>장르</span>
              {result.genre.join(', ')}
            </p>
          )}
        </div>
      </div>
    )
  }

  const renderRecords = () => (
    <div className="dday-placeholder">
      <p>아직 내가 기록한 디데이가 없습니다.</p>
    </div>
  )

  const renderSettings = () => (
    <div className="dday-placeholder">
      <p>캘린더 연동 등 확장 기능이 추가될 예정입니다.</p>
    </div>
  )

  const renderBody = () => {
    switch (activeMenu) {
      case 'shared':
        return renderShared()
      case 'my-dday':
        return renderFavorite()
      case 'records':
        return renderRecords()
      case 'settings':
        return renderSettings()
      default:
        return null
    }
  }

  return (
    <div className="dday-panel simple">
      <nav className="gnb">
        {menus.map((menu, index) => (
          <div key={menu.id} className="gnb-group">
            <button
              type="button"
              className={`gnb-item ${activeMenu === menu.id ? 'active' : ''}`}
              onClick={() => setActiveMenu(menu.id)}
            >
              {menu.label}
            </button>
            {index < menus.length - 1 && <span className="gnb-divider" />}
          </div>
        ))}
      </nav>
      <div className="gnb-body">{renderBody()}</div>
    </div>
  )
}
