import { ResearchBackdrop } from "./ResearchBackdrop";
import { GuideExplorer } from "./Guide";
import { ThemeToggle } from "./Theme";
import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import {
  ArrowRight,
  Download,
  Monitor,
  ShieldCheck,
  ChevronDown,
  Box,
  Copy,
  Check,
  BookOpen,
  ArrowUpRight,
} from "lucide-react";
import { useData, size, date, type Release } from "./api";
import { Brand, Empty, ErrorBox, External, Heading, Loading, Pill } from "./ui";

export function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a href="#content" className="skip">
        본문으로 이동
      </a>
      <header className="site-header">
        <div className="site-width nav">
          <Brand />
          <nav aria-label="주 메뉴">
            <NavLink to="/" end>
              다운로드
            </NavLink>
            <NavLink to="/releases">버전 이력</NavLink>
            <NavLink to="/guide">사용 가이드</NavLink>
          </nav>
          <div className="nav-actions"><ThemeToggle/><Link className="admin-link" to="/admin">
            관리자 <ArrowUpRight size={14} />
          </Link></div>
        </div>
      </header>
      <main id="content">{children}</main>
      <footer className="site-footer site-width">
        <Brand />
        <div>
          <span>한국세라믹기술원 연구원용 · CrystalVision Lab</span>
          <span>연구 원본은 로컬에 유지하고, 검수 자료는 명시적으로 동기화합니다.</span>
        </div>
        <External href="https://github.com/CrystalVision-Lab/sic-xrt-analyzer">
          GitHub
        </External>
      </footer>
    </>
  );
}
function Hash({ sha }: { sha: string }) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  return (
    <div className="hash">
      <span>SHA-256</span>
      <code>{sha}</code>
      <button
        aria-label="SHA-256 복사"
        onClick={() =>
          navigator.clipboard
            .writeText(sha)
            .then(() => {
              setCopied(true);
              setFailed(false);
            })
            .catch(() => setFailed(true))
        }
      >
        {copied ? <Check size={16} /> : <Copy size={16} />}
      </button>
      {failed && <small>코드를 선택해 복사해 주세요.</small>}
    </div>
  );
}
function DownloadCard({ release }: { release: Release }) {
  const m = release.manifest;
  return (
    <div className="download-card">
      <div className="flex items-center justify-between">
        <span className="platform">
          <Monitor size={19} /> Windows 64-bit
        </span>
        <Pill tone="teal">{release.state.channel}</Pill>
      </div>
      <a
        className="download-button"
        href={`/portal-api/releases/${release.id}/download`}
      >
        <Download size={20} />
        <span>Windows 설치 프로그램 다운로드</span>
        <ArrowRight size={18} />
      </a>
      <p className="download-meta">
        v{m.version} <span>·</span> {size(m.size)} <span>·</span> {m.minimum_os}
      </p>
      <div className="download-note">
        <ShieldCheck size={17} />
        <span>
          프로그램·ImageJ/Fiji 런타임 포함. 연구 원본과 모델 파일은 포함하지
          않습니다.
        </span>
      </div>
      {m.signature === "UNSIGNED" && (
        <p className="quiet">
          현재 연구용 빌드는 코드 서명이 없습니다. 아래 체크섬으로 파일을 확인할
          수 있습니다.
        </p>
      )}
      <Hash sha={m.sha256} />
      <a
        className="text-link"
        href={`/portal-api/releases/${release.id}/source`}
      >
        GPLv3 소스 · 빌드 방법 다운로드 ({size(m.source_archive.size)}){" "}
        <ArrowUpRight size={15} />
      </a>
      <Link to="/releases" className="text-link">
        변경 사항과 이전 버전 <ArrowUpRight size={15} />
      </Link>
    </div>
  );
}
export function DownloadPage() {
  const {data,error,loading}=useData<Release[]>("releases");
  const latest=data?.find(r=>r.state.channel==="STABLE")??data?.[0];
  return <PublicShell><div className="download-stage"><ResearchBackdrop/><section className="research-hero site-width"><div className="research-intro"><div className="institute-label"><img src="/kicet-logo.png" alt="한국세라믹기술원 KICET"/><span>연구원 전용 배포 · 사용 안내</span></div><p className="eyebrow">SiC XRT ANALYZER</p><h1>연구원님의 XRT 작업을<br/><span>한 화면에서 이어갑니다.</span></h1><p className="hero-lead">2D 이미지 분석과 검수, TIFF 스택 탐색을 위한<br/>설치 프로그램과 작업별 사용 가이드입니다.</p><div className="hero-tags"><Pill>2D JPG · 단일 TIFF</Pill><Pill>TIFF 스택 · 3D</Pill><Pill>Windows 64-bit</Pill></div><a className="outline-button" href="#research-guide"><BookOpen size={18}/> 실제 데이터 사용 가이드 <ArrowRight size={16}/></a><div className="format-guide"><div><Monitor size={20}/><strong>2D 이미지</strong><p>JPG와 단일 페이지 TIFF<br/>분석 → 후보 확인 → 연구원 검수</p></div><div><Box size={20}/><strong>TIFF 스택</strong><p>여러 페이지 TIFF<br/>페이지 탐색 → ROI → 3D 보기</p></div></div></div><div className="research-download">{loading?<Loading/>:error?<ErrorBox error={error}/>:latest?<DownloadCard release={latest}/>:<Empty title="설치 파일을 준비 중입니다"/>}<p className="download-support">기존 설치가 있다면 프로그램을 종료한 뒤 새 버전을 설치하세요. 연구 파일과 개인 프로젝트는 설치 폴더 밖에 보관하세요.</p></div></section></div><GuideExplorer/><section className="faq site-width"><div><p className="eyebrow">연구원 안내</p><h2>사용 전에 확인하세요</h2></div><div>{[["2D TIFF도 분석할 수 있나요?","네. 실제 파일의 페이지 수가 1장이면 2D 분석을 준비할 수 있습니다. 여러 페이지 TIFF에는 분석 버튼을 표시하지 않습니다. 데이터 타입·채널은 선택한 모델의 입력 계약과 별도로 확인합니다."],["연구 파일과 모델이 설치 파일에 포함되나요?","설치 프로그램에는 연구 원본과 모델이 포함되지 않습니다. 모델은 관리자에게 전달받은 파일이나 승인된 버전을 선택합니다. 현재 모델 성능은 관리자 화면에서 근거와 함께 확인합니다."],["3D 화면의 페이지가 실제 깊이인가요?","기본 화면은 X/Y 원본 픽셀과 페이지 인덱스를 사용합니다. 촬영 방향·순서·간격 근거를 확인한 뒤에만 물리 좌표를 사용하세요."],["파일을 열면 서버에 자동 전송되나요?","아니요. 저장과 검수는 로컬에서 진행됩니다. 서버 동기화와 Crop 전송은 사용자가 직접 선택합니다."]].map(([q,a])=><details key={q}><summary>{q}<ChevronDown size={17}/></summary><p>{a}</p></details>)}</div></section></PublicShell>;
}
export function ReleasesPage() {
  const { data, error, loading } = useData<Release[]>("releases");
  return (
    <PublicShell>
      <div className="site-width inner-page">
        <Heading eyebrow="RELEASES" title="버전과 변경 이력">
          게시된 설치 프로그램과 파일 무결성 정보를 확인하세요.
        </Heading>
        {loading ? (
          <Loading />
        ) : error ? (
          <ErrorBox error={error} />
        ) : data?.length ? (
          data.map((r) => (
            <article className="release-card" key={r.id}>
              <div className="release-head">
                <h2>v{r.manifest.version}</h2>
                <Pill tone="teal">{r.state.channel}</Pill>
                <span>{date(r.created_at)}</span>
                <a
                  className="outline-button"
                  href={`/portal-api/releases/${r.id}/download`}
                >
                  <Download size={16} /> 다운로드
                </a>
              </div>
              <p className="release-notes">{r.manifest.notes}</p>
              <p className="quiet">
                Windows x64 · {size(r.manifest.size)} · {r.manifest.minimum_os}{" "}
                ·{" "}
                {r.manifest.signature === "UNSIGNED"
                  ? "코드 서명 없음"
                  : "코드 서명 기록 있음"}
              </p>
              <Hash sha={r.manifest.sha256} />
              <a
                className="text-link"
                href={`/portal-api/releases/${r.id}/source`}
              >
                동일 버전 GPLv3 소스 · 빌드 방법 (
                {size(r.manifest.source_archive.size)}){" "}
                <ArrowUpRight size={15} />
              </a>
              <Hash sha={r.manifest.source_archive.sha256} />
              <details className="build-details">
                <summary>빌드 정보</summary>
                <code>Source revision: {r.manifest.source_revision}</code>
                <p>포함 기능: {r.manifest.components.join(" · ")}</p>
              </details>
            </article>
          ))
        ) : (
          <Empty title="게시된 버전이 없습니다">
            검증 중이거나 철회된 설치 파일은 공개 목록에 나타나지 않습니다.
          </Empty>
        )}
      </div>
    </PublicShell>
  );
}
export function GuidePage() { return <PublicShell><GuideExplorer/></PublicShell>; }
