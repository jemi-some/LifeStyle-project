import type { DdayResult } from '../hooks/use-dday'

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
