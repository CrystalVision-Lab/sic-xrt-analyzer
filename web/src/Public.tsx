import { ResearchBackdrop } from "./ResearchBackdrop";
import { GuideExplorer } from "./Guide";
import { ThemeToggle } from "./Theme";
import { Link, NavLink } from "react-router-dom";
import { ArrowUpRight, Download, Monitor } from "lucide-react";
import { useData, type Release } from "./api";
import { releaseHighlights } from "./releaseNotes";
import { Brand, Empty, ErrorBox, Loading } from "./ui";

function latestRelease(data?: Release[]) {
  return data?.find(r => r.state.channel === "STABLE") ?? data?.[0];
}
export function PublicShell({ children, sourceRelease }: { children: React.ReactNode; sourceRelease?: Release }) {
  return <div className="public-shell">
    <ResearchBackdrop />
    <a href="#content" className="skip">본문으로 이동</a>
    <header className="site-header"><div className="site-width nav">
      <Brand />
      <nav aria-label="주 메뉴">
        <NavLink to="/" end>다운로드</NavLink>
        <NavLink to="/guide">사용 가이드</NavLink>
      </nav>
      <div className="nav-actions"><ThemeToggle /><Link className="admin-link" to="/admin">관리자 <ArrowUpRight size={14} /></Link></div>
    </div></header>
    <main id="content">{children}</main>
    <footer className="site-footer site-width">
      <span>한국세라믹기술원 연구용 · SiC XRT Analyzer</span>
      <nav className="footer-links" aria-label="하단 메뉴">
        <Link to="/notes">개발 노트</Link>
        {sourceRelease && <a className="source-download" href={`/portal-api/releases/${sourceRelease.id}/source`}>GPLv3 소스 다운로드 <ArrowUpRight size={13} /></a>}
      </nav>
    </footer>
  </div>;
}
function InstituteWordmark() {
  return <div className="institute-wordmark">
    <img src="/kicet-logo.png" alt="한국세라믹기술원 KICET" />
    <img src="/kicet-logo.png" alt="" aria-hidden="true" className="wordmark-contrast" />
  </div>;
}
export function DownloadPage() {
  const { data, error, loading } = useData<Release[]>("releases");
  const latest = latestRelease(data);
  return <PublicShell sourceRelease={latest}>
    <section className="download-scene site-width" aria-labelledby="download-title">
      <InstituteWordmark />
      <p className="eyebrow">RESEARCH WORKSPACE</p>
      <h1 id="download-title">SiC XRT <span>Analyzer</span></h1>
      <p className="download-subtitle">연구를 이어가는 하나의 작업 공간.</p>
      <div className="download-action">
        {loading ? <Loading /> : error ? <ErrorBox error={error} /> : latest ? <>
          <a className="download-primary" href={`/portal-api/releases/${latest.id}/download`}><Download size={21} /><span>Windows 다운로드</span><ArrowUpRight size={19} /></a>
          <p className="download-version"><Monitor size={14} /> Windows 10 / 11 · 64-bit <span>v{latest.manifest.version}</span></p>
        </> : <Empty title="설치 파일을 준비 중입니다" />}
      </div>
    </section>
  </PublicShell>;
}
export function NotesPage() {
  const { data, error, loading } = useData<Release[]>("releases");
  // A short, read-only journal. The complete release ledger belongs to admin.
  const notes = data?.filter(r => r.manifest.notes.trim()).slice(0, 3);
  return <PublicShell><section className="notes-page site-width" aria-labelledby="notes-title">
    <p className="eyebrow">DEVELOPMENT NOTES</p><h1 id="notes-title">개발 노트</h1>
    {loading ? <Loading /> : error ? <ErrorBox error={error} /> : notes?.length ? notes.map((release, index) => <article className="latest-note" key={release.id}>
      <h2 className="note-edition"><span>{index === 0 ? "이번 업데이트" : "이전 개선"}</span><span>v{release.manifest.version}</span></h2>
      <ul className="note-highlights">{releaseHighlights(release.manifest.notes).map(note => <li key={note}>{note}</li>)}</ul>
    </article>) : <Empty title="개발 노트를 준비 중입니다" />}
  </section></PublicShell>;
}
export function GuidePage() { return <PublicShell><GuideExplorer /></PublicShell>; }
