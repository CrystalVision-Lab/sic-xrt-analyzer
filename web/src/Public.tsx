import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import {
  ArrowRight,
  Download,
  Monitor,
  ShieldCheck,
  ChevronDown,
  Crosshair,
  Box,
  FolderOpen,
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
            <NavLink to="/guide">시작 가이드</NavLink>
          </nav>
          <Link className="admin-link" to="/admin">
            관리자 <ArrowUpRight size={14} />
          </Link>
        </div>
      </header>
      <main id="content">{children}</main>
      <footer className="site-footer site-width">
        <Brand />
        <div>
          <span>CrystalVision Lab · 연구용 데스크톱 소프트웨어</span>
          <span>원본 데이터는 로컬에. 서버 전송은 사용자가 선택합니다.</span>
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
      <Link to="/releases" className="text-link">
        변경 사항과 이전 버전 <ArrowUpRight size={15} />
      </Link>
    </div>
  );
}
export function DownloadPage() {
  const { data, error, loading } = useData<Release[]>("releases");
  const latest = data?.find((r) => r.state.channel === "STABLE") ?? data?.[0];
  return (
    <PublicShell>
      <section className="hero site-width">
        <div className="hero-copy">
          <p className="eyebrow">
            <span className="status-dot" /> RESEARCH WORKSPACE
          </p>
          <h1>
            XRT 이미지를 읽고,
            <br />
            <span>구조를 살펴보세요.</span>
          </h1>
          <p className="hero-lead">
            SiC XRT 연구를 위한 하나의 작업 공간.
            <br />
            대형 이미지 탐색부터 ROI, 페이지 기반 3D와
            <br className="desktop-only" /> 연구원 검수까지 연결합니다.
          </p>
          <div className="hero-tags">
            <Pill>TIFF / JPG</Pill>
            <Pill>16-bit 원본 유지</Pill>
            <Pill>Windows 데스크톱</Pill>
          </div>
          {loading ? (
            <Loading />
          ) : error ? (
            <ErrorBox error={error} />
          ) : latest ? (
            <DownloadCard release={latest} />
          ) : (
            <Empty title="설치 파일을 준비 중입니다">
              검증된 릴리스가 게시되면 여기에서 다운로드할 수 있습니다.
            </Empty>
          )}
        </div>
        <div className="product-preview">
          <div className="preview-top">
            <span>
              <i />
              <i />
              <i />
            </span>
            <span>SiC XRT Analyzer</span>
            <Box size={15} />
          </div>
          <img
            src="/product-preview.png"
            alt="합성 TIFF에서 페이지와 수동 Track을 탐색하는 실제 3D 작업공간"
          />
          <div className="preview-bottom">
            <span>
              <span className="status-dot" /> TIFF STACK 3D
            </span>
            <span>합성 데이터 데모</span>
          </div>
          <div className="preview-caption">
            <span className="caption-line" />
            <p>
              원본 X/Y 픽셀과 페이지를 함께 탐색합니다.
              <br />
              <strong>실제 물리 Z축은 별도 촬영 근거가 필요합니다.</strong>
            </p>
          </div>
        </div>
      </section>
      <section className="workflow site-width">
        <div className="section-heading">
          <p className="eyebrow">BUILT FOR YOUR WORKFLOW</p>
          <h2>연구 흐름을 끊지 않는 도구.</h2>
          <p>이미지 보기와 분석 근거, 검수 기록을 한 프로젝트에.</p>
        </div>
        <div className="feature-grid">
          {[
            {
              icon: Crosshair,
              title: "원본 기반 이미지 탐색",
              text: "대형 TIFF·JPG를 확대하고, 원본 좌표와 픽셀 값을 확인합니다. 표시 대비는 원본을 바꾸지 않습니다.",
              tag: "VIEWER & ROI",
            },
            {
              icon: Box,
              title: "스택을 여러 방향으로",
              text: "선택한 ROI의 3D 평면과 XY·X–Page·Y–Page 단면에서 관측 위치를 기록합니다.",
              tag: "INDEXED STACK 3D",
            },
            {
              icon: FolderOpen,
              title: "검수 기록과 프로젝트",
              text: "후보·수동 영역·검수 이력을 저장하고, 동의한 데이터를 중앙 서버로 전송합니다.",
              tag: "REVIEW & SYNC",
            },
          ].map((f) => (
            <article key={f.tag}>
              <f.icon size={25} />
              <h3>{f.title}</h3>
              <p>{f.text}</p>
              <span>{f.tag}</span>
            </article>
          ))}
        </div>
      </section>
      <section className="start-strip site-width">
        <BookOpen size={26} />
        <div>
          <h2>처음 시작하시나요?</h2>
          <p>설치부터 이미지 열기, 프로젝트 저장과 서버 연결까지.</p>
        </div>
        <Link className="outline-button" to="/guide">
          시작 가이드 <ArrowRight size={16} />
        </Link>
      </section>
      <section className="faq site-width">
        <div>
          <p className="eyebrow">BEFORE YOU DOWNLOAD</p>
          <h2>알아두면 좋은 점</h2>
        </div>
        <div>
          {[
            [
              "모델 파일도 함께 설치되나요?",
              "원본 연구 데이터와 모델은 설치 파일에 포함되지 않습니다. 분석에는 별도로 선택한 모델 또는 관리자에게 배포 승인된 모델이 필요합니다. 뷰어·ROI·페이지 기반 3D는 모델 없이 사용할 수 있습니다.",
            ],
            [
              "이미지를 열면 서버로 자동 전송되나요?",
              "아니요. 로컬 프로젝트의 저장과 검수는 서버 없이 사용할 수 있습니다. 서버 동기화는 사용자가 실행하며, Crop 전송은 별도 동의를 받습니다.",
            ],
            [
              "3D 화면은 실제 깊이를 보여주나요?",
              "기본 3D는 원본 X/Y 픽셀과 페이지 인덱스를 사용합니다. 촬영 방향·순서·간격과 독립 근거가 확인되기 전에는 실제 깊이나 결함 길이·부피를 확정하지 않습니다.",
            ],
          ].map(([q, a]) => (
            <details key={q}>
              <summary>
                {q}
                <ChevronDown size={17} />
              </summary>
              <p>{a}</p>
            </details>
          ))}
        </div>
      </section>
    </PublicShell>
  );
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
export function GuidePage() {
  return (
    <PublicShell>
      <div className="site-width inner-page guide">
        <Heading eyebrow="GET STARTED" title="연구 작업공간 시작하기">
          설치, 로컬 사용, 서버 연결 순서로 안내합니다.
        </Heading>
        <div className="requirements">
          <Monitor size={23} />
          <div>
            <h2>시스템 요구사항</h2>
            <p>
              Windows 10/11 64-bit · 대용량 스택 작업은 16 GB 이상 메모리와
              충분한 로컬 저장 공간을 권장합니다.
            </p>
            <p>
              Python·Java를 따로 설치하지 않아도 됩니다. 3D 표시는 Qt에서
              지원하는 GPU 드라이버가 필요하며, 미지원 환경에서는 직교 단면을
              사용할 수 있습니다.
            </p>
          </div>
        </div>
        {[
          [
            "01",
            "설치하고 실행하기",
            "다운로드한 설치 프로그램을 실행하고 설치 위치를 선택합니다. 시작 메뉴의 SiC XRT Analyzer를 실행하세요. 설치 해제는 Windows의 설치된 앱 메뉴에서 할 수 있습니다. 원본과 개인 프로젝트는 설치 폴더 바깥에 저장하세요.",
          ],
          [
            "02",
            "이미지와 ROI 탐색",
            "열기에서 JPG 또는 TIFF를 선택하세요. Pan·Zoom·화면 맞춤으로 이동하고 원본 좌표 ROI를 지정합니다. TIFF 페이지는 슬라이더·휠·방향키로 탐색합니다.",
          ],
          [
            "03",
            "선택 영역을 3D로 보기",
            "3D 뷰어에서 TIFF·사각 ROI·페이지 범위를 고른 뒤 3D 생성합니다. 원본 ROI Volume은 최대 64 MiB입니다. 초과하면 영역을 줄이거나 명시적 샘플 간격을 늘리세요.",
          ],
          [
            "04",
            "모델과 검수 근거 연결",
            "분석에 사용할 승인된 모델 또는 연구용 모델 폴더를 선택합니다. 후보와 연구원 판정은 별도 기록입니다. 프로그램 설치만으로 모델의 과학적 정확도가 승인되지는 않습니다.",
          ],
          [
            "05",
            "프로젝트 저장과 동기화",
            "프로젝트를 로컬에 저장합니다. 관리자가 발급한 client ID·인증값·프로젝트 권한으로 중앙 서버에 연결하세요. 서버 주소는 현재 사이트의 HTTPS 주소입니다. 임시 Cloudflare 주소는 재시작하면 달라질 수 있습니다. 데이터 전송은 서버와 동기화 버튼으로 직접 실행합니다.",
          ],
        ].map(([n, t, p]) => (
          <section className="guide-step" key={n}>
            <span>{n}</span>
            <div>
              <h2>{t}</h2>
              <p>{p}</p>
            </div>
          </section>
        ))}
        <div className="notice">
          <ShieldCheck size={20} />
          <p>
            인증키는 계정 권한입니다. 공개 게시물이나 공유 프로젝트에 넣지
            마세요. 수집 자료·모델 평가는 관리자 로그인 후에만 조회할 수
            있습니다.
          </p>
        </div>
        <External href="https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues">
          문제 제보 및 개발 기록
        </External>
      </div>
    </PublicShell>
  );
}
