import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChatPanel } from './components/ChatPanel'
import { DdayPanel } from './components/DdayPanel'
import { Header } from './components/Header'
import { LandingPage } from './components/LandingPage'
import { useAuth } from './hooks/use-auth'
import { useDday } from './hooks/use-dday'

function App() {
  const { session, loading, signInWithGoogle } = useAuth()
  const {
    query,
    setQuery,
    isLoading,
    result,
    error,
    handleSubmit,
    handleConfirm,
    handleCancel,
    history,
    stageGroups,
  } = useDday()

  const [longestRaw, setLongestRaw] = useState('D-0')

  const fetchLongest = useCallback(async () => {
    try {
      if (!session) return
      const res = await fetch('/dday/longest', {
        headers: {
          Authorization: `Bearer ${session.access_token}`
        }
      })
      if (!res.ok) return
      const data = (await res.json()) as { dday: string } | null
      if (data?.dday) {
        setLongestRaw(data.dday)
      }
    } catch {
      // ignore
    }
  }, [session])

  useEffect(() => {
    fetchLongest()
  }, [fetchLongest])

  useEffect(() => {
    if (!session && !loading) {
      document.body.classList.add('dark-theme')
    } else {
      document.body.classList.remove('dark-theme')
    }
  }, [session, loading])

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 900) {
        window.scrollTo({ top: 0 })
      }
    }
    window.addEventListener('resize', handleResize)
    handleResize()
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    if (result) {
      fetchLongest()
    }
  }, [result, fetchLongest])

  const displayLongest = useMemo(() => {
    if (longestRaw.startsWith('D-')) {
      return `+${longestRaw.slice(2)}`
    }
    if (longestRaw.startsWith('D+')) {
      return `+0`
    }
    return longestRaw
  }, [longestRaw])

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
      </div>
    )
  }

  if (!session) {
    return <LandingPage onLogin={signInWithGoogle} />
  }

  return (
    <div className="page">
      <Header title="WAITWITH" statusLabel={displayLongest} />
      <main className="layout">
        <div className="panel chat-panel">
          <ChatPanel
            query={query}
            setQuery={setQuery}
            isLoading={isLoading}
            error={error}
            onSubmit={handleSubmit}
            history={history}
            stageGroups={stageGroups}
            onConfirm={handleConfirm}
            onCancel={handleCancel}
          />
        </div>
        <div className="panel dday-panel">
          <DdayPanel result={result} isLoading={isLoading} />
        </div>
      </main>
    </div>
  )
}

export default App
