import { ResearchBackdrop } from "./ResearchBackdrop";
import { GuideExplorer } from "./Guide";
import { ThemeToggle } from "./Theme";
import { Link, NavLink } from "react-router-dom";
import { ArrowUpRight, Download, Monitor, Sparkles, Image, RefreshCw } from "lucide-react";
import { useData, type Release } from "./api";
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
        <NavLink to="/notes">개발노트</NavLink>
      </nav>
      <div className="nav-actions"><ThemeToggle /><Link className="admin-link" to="/admin">관리자 <ArrowUpRight size={14} /></Link></div>
    </div></header>
    <main id="content">{children}</main>
    <footer className="site-footer site-width">
      <span>한국세라믹기술원 연구용 · SiC XRT Analyzer</span>
      {sourceRelease && <a className="source-download" href={`/portal-api/releases/${sourceRelease.id}/source`}>GPLv3 소스 다운로드 <ArrowUpRight size={13} /></a>}
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
const improvements = [
  { icon: Image, title: "대형 JPG를 안정적으로 열어요", text: "설치 버전에서 일부 JPG가 열리지 않던 문제를 수정했습니다." },
  { icon: Sparkles, title: "2D TIFF도 분석할 수 있어요", text: "단일 페이지 TIFF에서 분석·저장·검수를 연결했습니다. 여러 페이지 TIFF는 스택·3D 탐색으로 구분합니다." },
  { icon: RefreshCw, title: "새 버전을 프로그램에서 확인해요", text: "업데이트 알림과 설치 파일 다운로드를 추가했습니다." },
];
const workflowImprovements = [
  { icon: Image, title: "분석 결과를 이어서 봐요", text: "창을 닫거나 다른 화면을 다녀와도 이미지별 결과를 다시 열 수 있습니다." },
  { icon: Sparkles, title: "찾는 과정을 영상에서 확인해요", text: "처리 영역과 완료된 후보를 실시간으로 표시하고, BPD 영역 제안·ROI 레이어·선택 신고를 연결했습니다." },
  { icon: RefreshCw, title: "작업 화면을 간단하게 정리했어요", text: "폴더로 여는 Wafer Map, 전·후 비교, TIFF 선택 영역의 3D 보기로 작업을 줄였습니다." },
];
export function NotesPage() {
  const { data, error, loading } = useData<Release[]>("releases");
  const latest = latestRelease(data);
  return <PublicShell><section className="notes-page site-width" aria-labelledby="notes-title">
    <p className="eyebrow">DEVELOPMENT NOTES</p><h1 id="notes-title">조금 더 편한 연구를 위해.</h1>
    {loading ? <Loading /> : error ? <ErrorBox error={error} /> : latest ? <article className="latest-note">
      <div className="note-edition"><span>이번 업데이트</span><span>v{latest.manifest.version}</span></div>
      {(latest.manifest.version === "0.1.1" || latest.manifest.version.startsWith("0.2.")) ? <div className="note-improvements">{(latest.manifest.version.startsWith("0.2.") ? workflowImprovements : improvements).map(({icon: Icon, title, text}) => <section key={title}><Icon size={22} aria-hidden="true" /><div><h2>{title}</h2><p>{text}</p></div></section>)}</div> : <p className="note-summary">{latest.manifest.notes}</p>}
    </article> : <Empty title="개발노트를 준비 중입니다" />}
  </section></PublicShell>;
}
export function GuidePage() { return <PublicShell><GuideExplorer /></PublicShell>; }
