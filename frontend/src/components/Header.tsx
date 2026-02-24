import type { ReactNode } from 'react'
import { useAuth } from '../hooks/use-auth'

type Props = {
  title: string
  statusLabel: string
  icon?: ReactNode
}

export function Header({ title, statusLabel, icon }: Props) {
  const { session, signInWithGoogle, signOut } = useAuth()

  return (
    <header className="top-header">
      <div className="logo">{title}</div>
      <div className="auth-and-status">
        <div className="profile">
          <span className="profile-icon material-symbols-rounded">
            {icon ?? 'ecg_heart'}
          </span>
          <span>{statusLabel}</span>
        </div>

        <div className="auth-section">
          {session ? (
            <div className="auth-profile">
              <img
                src={session.user.user_metadata.avatar_url}
                alt="Profile"
                className="avatar"
                referrerPolicy="no-referrer"
              />
              <button onClick={signOut} className="auth-btn">로그아웃</button>
            </div>
          ) : (
            <button onClick={signInWithGoogle} className="auth-btn">구글 로그인</button>
          )}
        </div>
      </div>
    </header>
  )
}
