import { SiteDevices } from "./SiteAccess";
import { ThemeToggle } from "./Theme";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import {
  Activity,
  Archive,
  ArrowLeft,
  Database,
  Download,
  FlaskConical,
  LayoutDashboard,
  LogOut,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  Users,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  AlertCircle,
  Eye,
} from "lucide-react";
import {
  ApiError,
  date,
  number,
  object,
  request,
  rows,
  size,
  text,
  useData,
  type Json,
  type Release,
  type Session,
} from "./api";
import {
  Brand,
  Empty,
  ErrorBox,
  Heading,
  JsonDetails,
  Loading,
  Pill,
  Modal,
} from "./ui";

type Page = { items: Json[]; total: number; offset: number; limit: number };
const menu = [
  { to: "/admin/site-devices", label: "사이트 기기 승인", icon: ShieldCheck },
  { to: "/admin", label: "운영 개요", icon: LayoutDashboard, end: true },
  { to: "/admin/releases", label: "버전 · 배포 이력", icon: Download },
  { to: "/admin/models", label: "모델 성능", icon: FlaskConical },
  { to: "/admin/projects", label: "수집 프로젝트", icon: Database },
  { to: "/admin/batches", label: "동기화 이력", icon: Activity },
  { to: "/admin/users", label: "연구원 · 기기", icon: Users },
  { to: "/admin/audit", label: "감사 기록", icon: ScrollText },
];
export function Login({ onLogin }: { onLogin: (s: Session) => void }) {
  const [id, setId] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <div className="login-page"><div className="login-theme"><ThemeToggle/></div>
      <Link to="/" className="login-back">
        <ArrowLeft size={17} /> 다운로드 사이트로
      </Link>
      <div className="login-card">
        <Brand />
        <span className="login-icon">
          <ShieldCheck size={30} />
        </span>
        <h1>연구 관리자 로그인</h1>
        <p>관리자 아이디와 비밀번호로 접속합니다.</p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              const s = await request<Session>("login", {
                method: "POST",
                body: JSON.stringify({ username: id.trim(), password: key }),
              });
              setKey("");
              onLogin(s);
            } catch (e) {
              setError(
                e instanceof ApiError && e.status === 429
                  ? "로그인 시도 제한에 도달했습니다. 잠시 후 다시 시도하세요."
                  : "아이디와 비밀번호를 확인해 주세요. 서버 연결 상태도 확인할 수 있습니다.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          <label htmlFor="client-id">아이디</label>
          <input
            id="client-id"
            name="username"
            autoComplete="username"
            required
            maxLength={64}
            value={id}
            onChange={(e) => setId(e.target.value)}
            placeholder="관리자 아이디"
          />
          <label htmlFor="admin-key">비밀번호</label>
          <input
            id="admin-key"
            type="password"
            name="password"
            autoComplete="current-password"
            required
            maxLength={256}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="비밀번호"
          />
          {error && (
            <p role="alert" className="form-error">
              {error}
            </p>
          )}
          <button type="submit" className="primary-button" disabled={busy}>
            {busy ? "권한 확인 중…" : "관리자 콘솔 접속"}
          </button>
        </form>
        <p className="login-security">
          로그인은 2시간 유지됩니다. 비밀번호는 브라우저 저장소에 보관하지
          않습니다.
        </p>
      </div>
      <p className="login-foot">SiC XRT Analyzer · Research Administration</p>
    </div>
  );
}
export default function Admin() {
  const initial = useData<Session>("session");
  const [session, setSession] = useState<Session>();
  const [signedOut, setSignedOut] = useState(false);
  const candidate = session ?? (!signedOut ? initial.data : undefined);
  const active = candidate?.user.role === "ADMIN" ? candidate : undefined;
  const location = useLocation();
  if (initial.loading && !active) return <Loading />;
  if (!active) {
    return (
      <>
        {initial.error &&
          !(
            initial.error instanceof ApiError && initial.error.status === 401
          ) && <ErrorBox error={initial.error} />}
        <Login
          onLogin={(s) => {
            setSession(s);
            setSignedOut(false);
          }}
        />
      </>
    );
  }
  const title =
    menu.find((m) =>
      m.end ? location.pathname === m.to : location.pathname.startsWith(m.to),
    )?.label ?? "관리자";
  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <Brand inverse />
        <p className="sidebar-section">RESEARCH CONSOLE</p>
        <nav aria-label="관리자 메뉴">
          {menu.map((m) => (
            <NavLink key={m.to} to={m.to} end={m.end}>
              <m.icon size={18} />
              {m.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <ShieldCheck size={18} />
          <div>
            관리자 전용<p className="quiet">연구 자료 접근이 기록됩니다.</p>
          </div>
          <Link to="/">
            다운로드 사이트 <Eye size={15} />
          </Link>
        </div>
      </aside>
      <div className="admin-body">
        <header className="admin-header">
          <div>
            <span>관리자 콘솔</span>
            <ChevronRight size={14} />
            <strong>{title}</strong>
          </div>
          <div>
            <ThemeToggle/><Pill tone="teal">ADMIN</Pill>
            <span className="admin-user">{active.user.name}</span>
            <button
              className="icon-button"
              aria-label="로그아웃"
              onClick={async () => {
                try {
                  await request("logout", {
                    method: "POST",
                    headers: { "X-Xrt-Csrf": active.csrf },
                    body: "{}",
                  });
                } finally {
                  setSession(undefined);
                  setSignedOut(true);
                }
              }}
            >
              <LogOut size={17} />
            </button>
          </div>
        </header>
        <main className="admin-content">
          <Routes>
            <Route index element={<Overview />} />
            <Route path="site-devices" element={<SiteDevices session={active} />} />
            <Route
              path="releases"
              element={<ManageReleases session={active} />}
            />
            <Route path="models" element={<Models />} />
            <Route path="projects" element={<Projects />} />
            <Route path="batches" element={<Feed kind="batches" />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="audit" element={<Feed kind="audit" />} />
            <Route
              path="*"
              element={
                <Empty title="없는 관리자 화면입니다">
                  주소를 확인하거나 <Link to="/admin">운영 개요</Link>로
                  돌아가세요.
                </Empty>
              }
            />
          </Routes>
        </main>
      </div>
    </div>
  );
}
function Reload({ onClick }: { onClick: () => void }) {
  return (
    <button className="outline-button" onClick={onClick}>
      <RefreshCw size={15} /> 새로고침
    </button>
  );
}
function Stat({
  label,
  value,
  note,
  icon: Icon,
}: {
  label: string;
  value: unknown;
  note: string;
  icon: typeof Activity;
}) {
  return (
    <article className="stat">
      <div>
        <span>{label}</span>
        <Icon size={19} />
      </div>
      <strong>{number(value)}</strong>
      <small>{note}</small>
    </article>
  );
}
function Overview() {
  const [rev, setRev] = useState(0);
  const s = useData<Json>("research/admin/statistics", rev);
  const releases = useData<Release[]>("admin/releases", rev);
  const batches = useData<Page>("research/admin/portal/batches?limit=5", rev);
  const models = useData<Json[]>("research/admin/models/candidates", rev);
  return (
    <>
      <Heading
        eyebrow="SERVER OVERVIEW"
        title="연구 운영 현황"
        action={<Reload onClick={() => setRev((v) => v + 1)} />}
      >
        실제 서버에 수집된 기록과 배포 상태를 확인합니다.
      </Heading>
      {s.loading ? (
        <Loading />
      ) : s.error ? (
        <ErrorBox error={s.error} />
      ) : (
        <div className="stats-grid">
          <Stat
            label="수집 프로젝트"
            value={s.data?.projects}
            note="서버에 저장된 프로젝트"
            icon={Database}
          />
          <Stat
            label="검수된 대상"
            value={s.data?.reviewed_targets}
            note="개별 연구원 검수 기록"
            icon={CheckCircle2}
          />
          <Stat
            label="검수 충돌"
            value={s.data?.conflict_targets}
            note="일치하지 않는 연구원 판정"
            icon={AlertCircle}
          />
          <Stat
            label="전송된 Crop"
            value={s.data?.crops}
            note="별도 동의로 수집된 이미지"
            icon={Archive}
          />
        </div>
      )}
      <div className="admin-two">
        <section className="panel">
          <div className="panel-title">
            <h2>최근 동기화</h2>
            <Link to="/admin/batches">전체 보기 →</Link>
          </div>
          {batches.loading ? (
            <Loading />
          ) : batches.error ? (
            <ErrorBox error={batches.error} />
          ) : batches.data?.items.length ? (
            <table>
              <thead>
                <tr>
                  <th>프로젝트</th>
                  <th>기기</th>
                  <th>수신 시간</th>
                </tr>
              </thead>
              <tbody>
                {batches.data.items.map((b) => (
                  <tr key={text(b.id)}>
                    <td className="mono short-id">{text(b.project_id)}</td>
                    <td>{text(b.client_id)}</td>
                    <td>{date(b.received_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty title="수신한 동기화가 없습니다">
              Desktop에서 명시적으로 동기화한 자료가 여기에 표시됩니다.
            </Empty>
          )}
        </section>
        <section className="panel">
          <div className="panel-title">
            <h2>배포와 모델</h2>
            <Link to="/admin/releases">관리 →</Link>
          </div>
          <div className="summary-line">
            <span>게시된 프로그램</span>
            <strong>
              {releases.error
                ? "조회 실패"
                : releases.data?.filter((r) => r.state.status === "PUBLISHED")
                    .length ?? "—"}
            </strong>
          </div>
          <div className="summary-line">
            <span>등록된 모델 후보</span>
            <strong>
              {models.error ? "조회 실패" : models.data?.length ?? "—"}
            </strong>
          </div>
          {(releases.error || models.error) && (
            <ErrorBox error={(releases.error ?? models.error) as Error} />
          )}
          <div className="summary-line">
            <span>최근 서버 수신</span>
            <span>{date(s.data?.recent_received_at)}</span>
          </div>
          <div className="notice compact">
            <FlaskConical size={19} />
            <p>
              검수 기록 수는 승인된 학습 정답 수와 다릅니다. 모델 성능은 독립
              평가 근거가 있을 때만 해석합니다.
            </p>
          </div>
        </section>
      </div>
      <section className="panel">
        <div className="panel-title">
          <h2>연구 데이터 구성</h2>
          <Pill>실제 집계</Pill>
        </div>
        <div className="count-grid">
          {Object.entries(object(s.data?.counts)).map(([key, v]) => (
            <div key={key}>
              <span>{labels[key] ?? key}</span>
              <strong>{number(v)}</strong>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
const labels: Record<string, string> = {
  image_sources: "원본 메타데이터",
  analysis_runs: "분석 실행",
  observations: "후보 관측",
  predictions: "모델 예측",
  geometries: "영역 · 도형",
  defect_instances: "결함 객체",
  review_events: "검수 이벤트",
  model_provenance: "모델 출처",
  image_relationships: "이미지 관계",
};
function ManageReleases({ session }: { session: Session }) {
  const [rev, setRev] = useState(0);
  const { data, error, loading } = useData<Release[]>("admin/releases", rev);
  const [selected, setSelected] = useState<Release>();
  const [historyId, setHistoryId] = useState<string>();
  const historyRelease = data?.find(r => r.id === historyId);
  const [reason, setReason] = useState("");
  const [channel, setChannel] = useState("BETA");
  const [status, setStatus] = useState("PUBLISHED");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Error>();
  return (
    <>
      <Heading
        eyebrow="APPLICATION RELEASES"
        title="버전 · 배포 · 검증 이력"
        action={<Reload onClick={() => setRev((v) => v + 1)} />}
      >
        설치 파일의 공개·철회 상태를 관리합니다. 모델 릴리스는 별도 운영
        절차입니다.
      </Heading>
      <div className="notice">
        <ShieldCheck size={20} />
        <p>
          새 설치 파일은 로컬 등록 도구가 SHA를 확인한 뒤 DRAFT로 추가합니다.
          웹은 원본 바이너리를 교체하거나 모델을 활성화하지 않습니다.
        </p>
      </div>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBox error={error} />
      ) : data?.length ? (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>버전 · 파일</th>
                <th>채널</th>
                <th>상태</th>
                <th>다운로드 요청</th>
                <th>등록일</th>
                <th>관리</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>v{r.manifest.version}</strong>
                    {r.manifest.distribution_clearance?.status !==
                      "APPROVED" && <small>배포 라이선스 확인 대기</small>}
                    <small>{size(r.manifest.size)} · Windows x64</small>
                  </td>
                  <td>{r.state.channel}</td>
                  <td>
                    <Pill
                      tone={r.state.status === "PUBLISHED" ? "teal" : "neutral"}
                    >
                      {r.state.status}
                    </Pill>
                  </td>
                  <td>{r.download_requests.toLocaleString()}</td>
                  <td>{date(r.created_at)}</td>
                  <td>
                    <div className="table-actions">
                      <button
                        disabled={
                          r.manifest.distribution_clearance?.status !==
                          "APPROVED"
                        }
                        onClick={() => {
                          setSelected(r);
                          setReason("");
                          setChannel(r.state.channel);
                          setStatus(
                            r.state.status === "PUBLISHED"
                              ? "WITHDRAWN"
                              : "PUBLISHED",
                          );
                          setFailure(undefined);
                        }}
                      >
                        상태 변경
                      </button>
                      <button onClick={() => setHistoryId(r.id)}>배포·검증 이력</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty title="등록된 설치 파일이 없습니다">
          로컬 빌드·무결성 검사·등록 완료 후 관리할 수 있습니다.
        </Empty>
      )}
      {historyRelease && (
        <ReleaseHistory
          release={historyRelease}
          onClose={() => setHistoryId(undefined)}
        />
      )}{" "}
      {selected && (
        <Modal
          labelId="release-dialog-title"
          onClose={() => setSelected(undefined)}
          disabled={busy}
        >
          <h2 id="release-dialog-title">
            v{selected.manifest.version} 상태 변경
          </h2>
          <p className="quiet">
            기존 파일과 이력은 유지되고 새 revision이 추가됩니다.
          </p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                await request(`admin/releases/${selected.id}/state`, {
                  method: "POST",
                  headers: { "X-Xrt-Csrf": session.csrf },
                  body: JSON.stringify({
                    status,
                    channel,
                    reason,
                    previous_event_id: selected.event_id,
                  }),
                });
                setSelected(undefined);
                setRev((v) => v + 1);
              } catch (e) {
                setFailure(e as Error);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              상태
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="PUBLISHED">공개</option>
                <option value="WITHDRAWN">철회</option>
              </select>
            </label>
            <label>
              채널
              <select
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
              >
                <option>BETA</option>
                <option>STABLE</option>
              </select>
            </label>
            <label>
              변경 근거
              <textarea
                required
                minLength={10}
                maxLength={2000}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="검증 결과 또는 철회 사유를 10자 이상 기록"
              />
            </label>
            {failure && (
              <div role="alert" className="error">
                상태 변경을 완료하지 못했습니다. 이력 변경·파일 무결성·버전 채널
                조건을 확인하고 새로고침하세요.
              </div>
            )}
            <div className="modal-actions">
              <button
                type="button"
                className="outline-button"
                onClick={() => setSelected(undefined)}
              >
                취소
              </button>
              <button className="primary-button" disabled={busy}>
                변경 기록
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
export function ReleaseHistory({ release, onClose }: { release: Release; onClose: () => void }) {
  const { data, error, loading } = useData<ReleaseEvent[]>(
    `admin/releases/${release.id}/history`,
  );
  const m = release.manifest;
  return (
    <section className="panel release-history" aria-labelledby="release-history-title">
      <div className="panel-title">
        <h2 id="release-history-title">v{m.version} 배포·검증 이력</h2>
        <button onClick={onClose}>닫기</button>
      </div>
      <h3>등록 파일과 검증 정보</h3>
      <dl className="release-evidence">
        <dt>설치 파일</dt><dd>{m.filename} · {size(m.size)}</dd>
        <dt>설치 SHA-256</dt><dd><code>{m.sha256}</code></dd>
        <dt>대응 소스</dt><dd>{m.source_archive.filename} · {size(m.source_archive.size)}</dd>
        <dt>소스 SHA-256</dt><dd><code>{m.source_archive.sha256}</code></dd>
        <dt>소스 리비전</dt><dd><code>{m.source_revision}</code></dd>
        <dt>배포 승인</dt><dd>{m.distribution_clearance.status} · {m.distribution_clearance.reference}</dd>
        <dt>코드 서명</dt><dd>{m.signature}</dd>
        <dt>게시 시 검사</dt><dd>서버가 설치 파일·대응 소스의 SHA-256을 대조합니다. 기능 검증은 아래 변경 근거를 확인하세요.</dd>
      </dl>
      <details><summary>전체 변경 내용</summary><p className="release-full-notes">{m.notes}</p></details>
      <h3>상태 변경과 검증 근거</h3>
      {loading ? <Loading /> : error ? <ErrorBox error={error} /> : data?.length ? <div className="release-events"><table>
        <thead><tr><th>순서 · 일시</th><th>상태 · 채널</th><th>실행자</th><th>변경·검증 근거</th></tr></thead>
        <tbody>{data.map(event => <tr key={event.id}>
          <td>#{event.revision}<small>{date(event.created_at)}</small></td>
          <td>{event.state.status}<small>{event.state.channel}</small></td>
          <td>{event.actor}</td><td>{event.state.reason}</td>
        </tr>)}</tbody>
      </table></div> : <Empty title="상태 변경 기록이 없습니다" />}
      <JsonDetails value={{ manifest: m, events: data }} label="원본 기록 보기" />
    </section>
  );
}
type ReleaseEvent = {
  id: string; revision: number; created_at: number; actor: string;
  state: { status: string; channel: string; reason: string };
};
function Models() {
  const [rev, setRev] = useState(0);
  const { data, error, loading } = useData<Json[]>(
    "research/admin/models/candidates",
    rev,
  );
  const [selected, setSelected] = useState<string>();
  return (
    <>
      <Heading
        eyebrow="MODEL EVIDENCE"
        title="모델 성능과 평가 근거"
        action={<Reload onClick={() => setRev((v) => v + 1)} />}
      >
        등록된 평가 산출물과 CPU 비교를 조회합니다. 이 화면은 모델을
        승인·서명·활성화하지 않습니다.
      </Heading>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBox error={error} />
      ) : data?.length ? (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>모델 · 버전</th>
                <th>입력 계약</th>
                <th>현재 상태</th>
                <th>평가</th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={text(c.candidate_id)}>
                  <td>
                    <strong>{text(c.model_id)}</strong>
                    <small>{text(c.version)}</small>
                  </td>
                  <td>
                    <JsonDetails
                      value={object(c.manifest).input}
                      label="계약 보기"
                    />
                  </td>
                  <td>
                    {text(object(c.state).status ?? object(c.state).action)}
                  </td>
                  <td>
                    <button
                      className="outline-button"
                      onClick={() => setSelected(text(c.candidate_id))}
                    >
                      성능 근거 확인
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty title="등록된 평가 모델이 없습니다">
          독립 평가·Dataset 근거가 포함된 ML 산출물을 관리자 운영 도구로
          등록하면 비교할 수 있습니다. 정확도를 임의의 수치로 채우지 않습니다.
        </Empty>
      )}
      {selected && <Evaluation id={selected} />}
      <div className="notice">
        <FlaskConical size={20} />
        <p>
          ARTIFACT 검사, CPU 속도, 독립 Test 정확도, 관리자 승인과 서명은 서로
          다른 근거입니다. 합성 데이터의 기능 검사를 실제 연구 성능으로 해석하지
          마세요.
        </p>
      </div>
    </>
  );
}
function Evaluation({ id }: { id: string }) {
  const { data, error, loading } = useData<Json>(
    `research/admin/portal/models/${id}/evaluation`,
  );
  const e = object(data?.evaluation);
  const c = object(e.candidate);
  const b = object(e.baseline);
  const percent = (v: unknown) =>
    typeof v === "number" ? `${(v * 100).toFixed(2)}%` : "미제공";
  return (
    <section className="panel">
      <div className="panel-title">
        <h2>평가 결과 · {text(data?.version)}</h2>
        <Pill tone={e.scientific_metrics === true ? "teal" : "amber"}>
          {e.scientific_metrics === true
            ? "독립 평가 산출물"
            : "과학 성능 미검증"}
        </Pill>
      </div>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBox error={error} />
      ) : (
        <>
          <p className="quiet">
            상태 {text(e.status)} · 평가 SHA{" "}
            <code>{text(data?.evaluation_sha256)}</code>
          </p>
          <table>
            <thead>
              <tr>
                <th>지표</th>
                <th>후보 모델</th>
                <th>동일 입력 Baseline</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["accuracy", "정확도"],
                ["balanced_accuracy", "균형 정확도"],
                ["macro_f1", "Macro F1"],
              ].map(([key, label]) => (
                <tr key={key}>
                  <td>{label}</td>
                  <td>{percent(c[key])}</td>
                  <td>{percent(b[key])}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <JsonDetails
            value={c.per_class}
            label="BPD / TED / TSD Precision·Recall·F1·Support"
          />
          <JsonDetails
            value={c.confusion_matrix}
            label="혼동 행렬 (BPD·TED·TSD 순서)"
          />
          <JsonDetails
            value={data?.cpu_comparisons}
            label="CPU 실측 비교 이벤트"
          />
          <JsonDetails
            value={e}
            label="평가 출처·입력 동일성·Dataset 전체 근거"
          />
          <JsonDetails
            value={data?.deployment_gate}
            label="현재 배포 요건·Dataset 사용 상태·미충족 근거"
          />
        </>
      )}
    </section>
  );
}
function Pagination({
  offset,
  total,
  limit,
  onChange,
}: {
  offset: number;
  total: number;
  limit: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        {total
          ? `${offset + 1}–${Math.min(total, offset + limit)} / ${total.toLocaleString()}`
          : "0개"}
      </span>
      <button
        aria-label="이전 페이지"
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}
      >
        <ChevronLeft size={17} />
      </button>
      <button
        aria-label="다음 페이지"
        disabled={offset + limit >= total}
        onClick={() => onChange(offset + limit)}
      >
        <ChevronRight size={17} />
      </button>
    </div>
  );
}
function Projects() {
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string>();
  const { data, error, loading } = useData<Page>(
    `research/admin/portal/projects?offset=${offset}&limit=25`,
  );
  return (
    <>
      <Heading eyebrow="COLLECTED RESEARCH" title="수집 프로젝트">
        프로그램에서 동기화한 원본 메타데이터·분석·검수 이력을 조회합니다.
      </Heading>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBox error={error} />
      ) : data?.items.length ? (
        <section className="panel">
          <table>
            <thead>
              <tr>
                <th>프로젝트</th>
                <th>Schema</th>
                <th>서버 수신</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <tr key={text(p.id)}>
                  <td>
                    <strong>{text(p.name)}</strong>
                    <small className="mono">{text(p.id)}</small>
                  </td>
                  <td>{text(p.schema_version)}</td>
                  <td>{date(p.received_at)}</td>
                  <td>
                    <button
                      className="outline-button"
                      onClick={() => setSelected(text(p.id))}
                    >
                      자료 보기
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination
            offset={offset}
            total={data.total}
            limit={25}
            onChange={setOffset}
          />
        </section>
      ) : (
        <Empty title="수집된 프로젝트가 없습니다">
          Desktop에서 프로젝트를 저장하고 서버 동기화를 실행하세요.
        </Empty>
      )}
      {selected && <ProjectDetail key={selected} id={selected} />}
    </>
  );
}
function ProjectDetail({ id }: { id: string }) {
  const [kind, setKind] = useState("analysis_runs");
  const [offset, setOffset] = useState(0);
  const summary = useData<Json>(`research/projects/${id}/summary`);
  const data = useData<Page>(
    `research/admin/portal/projects/${id}/entities/${kind}?offset=${offset}&limit=50`,
  );
  const eligibility = useData<Json>(
    `research/admin/datasets/eligibility?project_id=${id}`,
  );
  const crops = useData<Json[]>(`research/admin/portal/projects/${id}/crops`);
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    // The detail opens below the table; bring it into view so the click visibly responds.
    panel.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    panel.current?.focus({ preventScroll: true });
  }, [id]);
  return (
    <section
      className="panel"
      ref={panel}
      tabIndex={-1}
      aria-label="선택한 프로젝트 자료"
    >
      <div className="panel-title">
        <h2>프로젝트 자료</h2>
        <Pill>읽기 전용</Pill>
      </div>
      {summary.error ? (
        <ErrorBox error={summary.error} />
      ) : (
        <JsonDetails value={summary.data} label="프로젝트·검수·충돌 집계" />
      )}
      <div className="table-toolbar">
        <label>
          기록 종류
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setOffset(0);
            }}
          >
            {Object.entries(labels).map(([k, v]) => (
              <option value={k} key={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <span className="quiet">
          모델 예측과 연구원 검수는 분리된 기록입니다.
        </span>
      </div>
      {data.loading ? (
        <Loading />
      ) : data.error ? (
        <ErrorBox error={data.error} />
      ) : data.data?.items.length ? (
        <>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>기기 · 실행자</th>
                <th>수신 시간</th>
                <th>원본 기록</th>
              </tr>
            </thead>
            <tbody>
              {data.data.items.map((r) => (
                <tr key={text(r.id)}>
                  <td className="mono short-id">{text(r.id)}</td>
                  <td>
                    {text(r.client_id)}
                    <small>{text(r.actor_id)}</small>
                  </td>
                  <td>{date(r.received_at)}</td>
                  <td>
                    <JsonDetails value={r.payload} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination
            offset={offset}
            total={data.data.total}
            limit={50}
            onChange={setOffset}
          />
        </>
      ) : (
        <Empty title="이 종류의 기록이 없습니다" />
      )}
      <JsonDetails
        value={eligibility.data}
        label="Dataset 사용 권한·정답 승인 적격성"
      />
      {eligibility.error && <ErrorBox error={eligibility.error} />}
      <div className="panel-title">
        <h3>동의받아 수집한 Crop</h3>
      </div>
      {crops.error ? (
        <ErrorBox error={crops.error} />
      ) : crops.data?.length ? (
        <div className="crop-grid">
          {crops.data.map((a) => (
            <figure key={text(a.id)}>
              <img
                loading="lazy"
                src={`/portal-api/research/admin/portal/projects/${id}/crops/${text(a.id)}`}
                alt="동의받아 전송한 연구 Crop"
              />
              <figcaption className="mono">
                {text(a.digest).slice(0, 16)}…
              </figcaption>
              <JsonDetails value={a.metadata} />
            </figure>
          ))}
        </div>
      ) : (
        <p className="quiet">
          전송된 Crop이 없습니다. 원본 TIFF/JPG 전체는 이 경로로 수집하지
          않습니다.
        </p>
      )}
    </section>
  );
}
function Feed({ kind }: { kind: "batches" | "audit" }) {
  const [offset, setOffset] = useState(0);
  const { data, error, loading } = useData<Page>(
    `research/admin/portal/${kind}?offset=${offset}&limit=25`,
  );
  return (
    <>
      <Heading
        eyebrow={kind === "batches" ? "SYNC RECEIPTS" : "AUDIT TRAIL"}
        title={kind === "batches" ? "동기화 수신 이력" : "서버 감사 기록"}
      >
        현재 서버에 기록된 실행자·기기·수신 결과를 조회합니다.
      </Heading>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBox error={error} />
      ) : data?.items.length ? (
        <section className="panel">
          <table>
            <thead>
              <tr>
                <th>시간</th>
                <th>기록</th>
                <th>실행자 · 기기</th>
                <th>상세</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={text(r.id)}>
                  <td>{date(r.received_at ?? r.created_at)}</td>
                  <td>
                    {kind === "audit" ? text(r.action) : text(r.project_id)}
                  </td>
                  <td>
                    {text(r.actor_id)}
                    <small>{text(r.client_id)}</small>
                  </td>
                  <td>
                    <JsonDetails
                      value={kind === "audit" ? r.detail : r.receipt}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination
            offset={offset}
            total={data.total}
            limit={25}
            onChange={setOffset}
          />
        </section>
      ) : (
        <Empty title="조회할 기록이 없습니다" />
      )}
    </>
  );
}
function UsersPage() {
  const { data, error, loading } = useData<Json[]>(
    "research/admin/portal/users",
  );
  return (
    <>
      <Heading eyebrow="RESEARCHERS & DEVICES" title="연구원과 연결 기기">
        계정 상태와 발급 기록을 조회합니다. 인증값 원문은 표시하지 않습니다.
      </Heading>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBox error={error} />
      ) : (
        <section className="panel">
          <table>
            <thead>
              <tr>
                <th>연구원</th>
                <th>역할</th>
                <th>상태</th>
                <th>기기</th>
              </tr>
            </thead>
            <tbody>
              {data?.map((u) => (
                <tr key={text(u.id)}>
                  <td>
                    <strong>{text(u.name)}</strong>
                    <small>{text(u.id)}</small>
                  </td>
                  <td>
                    <Pill>{text(u.role)}</Pill>
                  </td>
                  <td>{u.active ? "활성" : "비활성"}</td>
                  <td>
                    {rows(u.devices).map((d) => (
                      <div key={text(d.client_id)}>
                        {text(d.client_id)}
                        <JsonDetails
                          value={d.credentials}
                          label="발급·철회 기록 (인증값 없음)"
                        />
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <div className="notice">
        <ShieldCheck size={19} />
        <p>
          계정 발급·권한 부여·인증키 철회는 기존 관리자 운영 절차에서
          실행합니다. 포털은 계정 권한을 변경하지 않습니다.
        </p>
      </div>
    </>
  );
}
