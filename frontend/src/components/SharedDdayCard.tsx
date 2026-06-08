import type { DdayResult } from '../hooks/use-dday'

const OTT_COLORS: Record<string, { bg: string; color: string }> = {
  Netflix: { bg: '#e50914', color: '#fff' },
  'Disney+': { bg: '#113ccf', color: '#fff' },
  'Disney Plus': { bg: '#113ccf', color: '#fff' },
  'Apple TV+': { bg: '#1c1c1e', color: '#fff' },
  Wavve: { bg: '#0056ff', color: '#fff' },
  TVING: { bg: '#ff153c', color: '#fff' },
  Tving: { bg: '#ff153c', color: '#fff' },
  'Coupang Play': { bg: '#c0ea00', color: '#111' },
  'Amazon Prime Video': { bg: '#00a8e0', color: '#fff' },
  'Prime Video': { bg: '#00a8e0', color: '#fff' },
}

function getOttStyle(distributor: string): { background: string; color: string } | undefined {
  const match = Object.keys(OTT_COLORS).find((key) =>
    distributor.toLowerCase().includes(key.toLowerCase()),
  )
  return match ? { background: OTT_COLORS[match].bg, color: OTT_COLORS[match].color } : undefined
}

type Props = {
  item: DdayResult
  onReact?: (item: DdayResult) => void
}

export function SharedDdayCard({ item, onReact }: Props) {
  const typeBadge = item.content_type === 'tv' ? '드라마' : '영화'
  return (
    <div className="shared-item simple-card">
      <div
        className={`poster full ${item.poster_url ? 'has-image' : ''}`}
        aria-hidden
        style={item.poster_url ? { backgroundImage: `url(${item.poster_url})` } : undefined}
      >
        <div className="overlay">
          <div className="content-type">{typeBadge}</div>
          {item.content_type === 'tv' && item.distributor && (
            <p className="shared-ott" style={getOttStyle(item.distributor)}>{item.distributor}</p>
          )}
          <div className="shared-dday">{item.dday}</div>
          <p className="shared-title">{item.movie_title}</p>
          <p className="shared-meta">{item.release_date}</p>
          {item.genre && item.genre.length > 0 && <p className="shared-genre">{item.genre.join(', ')}</p>}
        </div>
        {!item.poster_url && <span>{item.movie_title[0]}</span>}
      </div>
      <button
        type="button"
        className="audience-badge"
        aria-label={`같이 기다려요 ${item.waiting_count ?? 1}명`}
        onClick={() => onReact?.(item)}
      >
        👥 {item.waiting_count ?? 1}
      </button>
    </div>
  )
}
