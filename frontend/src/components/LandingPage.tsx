
type Props = {
    onLogin: () => void;
};

export function LandingPage({ onLogin }: Props) {
    return (
        <div className="landing-page">
            {/* Hero Section */}
            <section className="hero">
                <div className="hero-content">
                    <h1 className="hero-title animate-up">
                        모든 기다림이 <br />
                        <span className="gradient-text">설렘이 되도록,</span>
                        WAITWITH
                    </h1>
                    <p className="hero-subtitle animate-up delay-1">
                        좋아하는 영화와 드라마의 개봉일을 AI로 확인하고, <br />
                        나만의 고유한 디데이 카드로 소중하게 기록하세요.
                    </p>
                    <div className="hero-actions animate-up delay-2">
                        <button onClick={onLogin} className="cta-button primary shadow-pop">
                            구글 로그인으로 시작하기
                            <span className="material-symbols-rounded">arrow_forward</span>
                        </button>
                    </div>
                </div>
                <div className="hero-visual">
                    <div className="gradient-sphere pos-1"></div>
                    <div className="gradient-sphere pos-2"></div>
                    <div className="glass-card-preview animate-float">
                        <div className="preview-header">
                            <span className="preview-label">개봉기다림</span>
                            <span className="preview-pill">Movie</span>
                        </div>
                        <div className="preview-title">프로젝트 헤일메리</div>
                        <div className="preview-dday">D-22</div>
                    </div>
                </div>
            </section>

            {/* Features Section */}
            <section className="features">
                <div className="feature-grid">
                    <div className="feature-card animate-up delay-3">
                        <span className="feature-icon material-symbols-rounded">search_spark</span>
                        <h3>똑똑한 AI 검색</h3>
                        <p>질문만 하세요. AI가 최신 정보를 찾아 개봉일을 정확하게 계산해드립니다.</p>
                    </div>
                    <div className="feature-card animate-up delay-4">
                        <span className="feature-icon material-symbols-rounded">dashboard_customize</span>
                        <h3>나만의 카드 수집</h3>
                        <p>개인화된 디데이 보드에서 내가 사랑하는 작품들을 한눈에 관리하세요.</p>
                    </div>
                    <div className="feature-card animate-up delay-5">
                        <span className="feature-icon material-symbols-rounded">groups</span>
                        <h3>함께 기다리는 즐거움</h3>
                        <p>다른 사람들은 어떤 작품을 기다리고 있는지 실시간으로 확인해보세요.</p>
                    </div>
                </div>
            </section>

            {/* CTA Footer */}
            <section className="cta-footer">
                <div className="cta-content animate-up delay-6">
                    <h2>지금 바로 당신의 <span className="gradient-text">첫 번째 디데이</span>를 기록해보세요.</h2>
                    <button onClick={onLogin} className="cta-button secondary">
                        로그인하고 시작하기
                    </button>
                </div>
            </section>
        </div>
    );
}
