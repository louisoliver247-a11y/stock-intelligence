import { useEffect } from "react";
import { LoginForm } from "./Users";

export function LoginPage({ onLogin, notice }: { onLogin: (token: string) => void; notice: string }) {
  useEffect(() => { document.documentElement.dataset.theme = "dark"; }, []);
  return <main className="signin-page">
    <section className="signin-story" aria-label="Stock Intelligence">
      <div className="signin-brand"><span className="brand-mark">SI</span><span>STOCK INTELLIGENCE<small>INDIAN EQUITIES / RESEARCH</small></span></div>
      <div className="signin-intro">
        <p className="signin-eyebrow">YOUR RESEARCH WORKSPACE</p>
        <h1>A clearer view.<br /><span>A better perspective.</span></h1>
        <p>Bring your market data, charts, and research together in one focused workspace.</p>
        <div className="signin-illustration" aria-hidden="true">
          <div className="signin-grid" />
          <svg viewBox="0 0 500 140" fill="none"><path d="M0 115L45 99L78 107L116 72L150 82L195 60L223 75L263 43L302 55L344 20L381 35L422 12L459 26L500 5" stroke="currentColor" strokeWidth="2" /><path d="M0 138H500M0 93H500M0 48H500" stroke="currentColor" opacity=".12" /></svg>
        </div>
      </div>
      <p className="signin-footnote">Built for focused market research.</p>
    </section>
    <section className="signin-access" aria-labelledby="signin-title">
      <div className="signin-card">
        <span className="signin-badge">WORKSPACE ACCESS</span>
        <h2 id="signin-title">Welcome back</h2>
        <p className="signin-description">Sign in to continue to Stock Intelligence.</p>
        {notice && <p role="status" className="signin-notice">{notice}</p>}
        <LoginForm onLogin={onLogin} />
        <p className="signin-help">Need an account? Contact your workspace administrator.</p>
      </div>
      <p className="signin-access-footer">Stock Intelligence · Indian equities</p>
    </section>
  </main>;
}
