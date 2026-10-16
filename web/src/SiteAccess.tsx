import { useEffect, useState } from "react";
import { Link, Navigate, Outlet, useLocation } from "react-router-dom";
import { ShieldCheck, LockKeyhole, RefreshCw } from "lucide-react";
import { date, request, useData, type Session } from "./api";
import { Brand, Empty, ErrorBox, Heading, Loading, Pill } from "./ui";
import { ThemeToggle } from "./Theme";

type Device = { id: string; status: string; created: number; expires: number; reason: string };
type Access = { allowed: boolean; device: Device | null };
type ManagedDevice = Device & { name: string; affiliation: string; device_name: string; user_agent: string; platform: string; revision: number; decided_at: number | null };
const labels: Record<string, string> = { PENDING: "승인 대기", APPROVED: "승인됨", REJECTED: "요청 거절", REVOKED: "권한 철회" };

export function SiteGate() {
  const location = useLocation();
  const [data, setData] = useState<Access>();
  const [error, setError] = useState<Error>();
  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => {
      request<Access>("access", { signal: controller.signal }).then(value => {
        if (!controller.signal.aborted) { setData(value); setError(undefined); }
      }).catch(err => { if (!controller.signal.aborted) setError(err); });
    };
    refresh();
    const timer = window.setInterval(refresh, 60000);
    window.addEventListener("focus", refresh);
    return () => { controller.abort(); clearInterval(timer); window.removeEventListener("focus", refresh); };
  }, []);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  if (!data.allowed) return <Navigate to="/access" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

export function AccessPage() {
  const [rev, setRev] = useState(0);
  const { data, error, loading } = useData<Access>("access", rev);
  const [submitted, setSubmitted] = useState<Device>();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Error>();
  const device = data?.device ?? submitted;
  useEffect(() => {
    if (device?.status !== "PENDING") return;
    const timer = window.setInterval(() => setRev(v => v + 1), 15000);
    return () => clearInterval(timer);
  }, [device?.status]);
  return <main className="access-page"><section className="access-card">
    <Brand /><div className="access-actions"><ThemeToggle /><Pill>승인된 기기 전용</Pill></div>
    {data?.allowed ? <>
      <ShieldCheck size={32} /><h1>사이트 접속이 승인되었습니다</h1>
      <p>이 브라우저에서 사용 가이드와 프로그램 다운로드를 이용할 수 있습니다.</p>
      <a className="primary-button" href="/">사이트 입장</a>
    </> : <>
      <h1><LockKeyhole size={25} /> 기기 승인이 필요합니다</h1>
      <p>연구 자료와 프로그램은 승인된 기기에서만 이용할 수 있습니다. 아래 정보를 보내면 관리자가 확인 후 접속 권한을 부여합니다.</p>
      {loading && !data && !submitted ? <Loading /> : error ? <ErrorBox error={error} /> : device ? <div className="access-status" role="status">
        <strong>{labels[device.status] ?? device.status}</strong>
        <p>요청 번호: {device.id}<br />요청일: {date(device.created)}</p>
        {device.reason && <p>관리자 안내: {device.reason}</p>}
        <p>{device.status === "PENDING" ? "승인 상태는 15초마다 확인합니다. 이 브라우저에서 다시 방문해도 요청이 유지됩니다." : "추가 확인이 필요하면 요청 번호와 함께 관리자에게 문의해 주세요."}</p>
      </div> : <form onSubmit={async e => {
        e.preventDefault(); setBusy(true); setFailure(undefined);
        const fields = new FormData(e.currentTarget);
        try {
          const result = await request<Device>("access/request", { method: "POST", body: JSON.stringify({ name: fields.get("name"), affiliation: fields.get("affiliation"), device_name: fields.get("device_name"), platform: navigator.platform || "알 수 없음" }) });
          setSubmitted(result); setRev(v => v + 1);
        } catch (err) { setFailure(err as Error); } finally { setBusy(false); }
      }}>
        <label>이름<input name="name" autoComplete="name" maxLength={120} required placeholder="홍길동" /></label>
        <label>소속 · 연락처<input name="affiliation" maxLength={120} required placeholder="연구실 / 관리자에게 알려진 연락처" /></label>
        <label>기기 이름<input name="device_name" maxLength={120} required placeholder="연구실 PC / 개인 노트북" /></label>
        <p>입력한 정보와 브라우저·운영체제 정보를 관리자에게 전달합니다. 승인은 이 브라우저에 저장된 기기 키에 연결됩니다. 쿠키 삭제, 다른 브라우저 또는 새 기기는 다시 승인이 필요합니다. 승인 유효기간은 요청일부터 180일입니다.</p>
        <button className="primary-button" disabled={busy}>{busy ? "요청 중…" : "접속 승인 요청"}</button>
      </form>}
      {failure && <ErrorBox error={failure} />}
    </>}
    <div className="access-actions"><button className="outline-button" disabled={loading || busy} onClick={() => setRev(v => v + 1)}><RefreshCw size={15} /> 승인 상태 확인</button><Link to="/admin/site-devices">관리자 로그인</Link></div>
  </section></main>;
}

export function SiteDevices({ session }: { session: Session }) {
  const [rev, setRev] = useState(0);
  const [filter, setFilter] = useState("PENDING");
  const { data, error, loading } = useData<ManagedDevice[]>("admin/site-devices", rev);
  const filtered = data?.filter(d => filter === "ALL" || d.status === filter);
  return <><Heading title="사이트 기기 승인" action={<button className="outline-button" onClick={() => setRev(v => v + 1)}><RefreshCw size={15} /> 새로고침</button>}>요청자의 이름·소속과 기기를 확인한 뒤 승인하세요. 사이트 승인은 프로그램의 연구 데이터 동기화 등록과 별개입니다.</Heading>
    <label>요청 상태 <select aria-label="요청 상태" value={filter} onChange={e => setFilter(e.target.value)}><option value="PENDING">승인 대기</option><option value="ALL">전체</option><option value="APPROVED">승인됨</option><option value="REJECTED">거절됨</option><option value="REVOKED">철회됨</option></select></label>
    {loading ? <Loading /> : error ? <ErrorBox error={error} /> : !filtered?.length ? <Empty title="해당 기기 요청이 없습니다" /> : <div className="device-list">{filtered.map(device => <DeviceReview key={`${device.id}-${device.revision}`} device={device} session={session} onChange={() => setRev(v => v + 1)} />)}</div>}
  </>;
}

function DeviceReview({ device: d, session, onChange }: { device: ManagedDevice; session: Session; onChange: () => void }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  const expired = d.expires * 1000 <= Date.now();
  async function decide(status: string) {
    setBusy(true); setError(undefined);
    try {
      await request(`admin/site-devices/${d.id}/state`, { method: "POST", headers: { "X-Xrt-Csrf": session.csrf }, body: JSON.stringify({ status, revision: d.revision, reason: reason.trim() }) });
      onChange();
    } catch (err) { setError(err as Error); } finally { setBusy(false); }
  }
  return <article className="device-review"><Pill>{expired ? "만료됨" : labels[d.status]}</Pill><h2>{d.name} · {d.device_name}</h2><p>{d.affiliation}</p>
    <dl><dt>요청 번호</dt><dd>{d.id}</dd><dt>운영체제</dt><dd>{d.platform}</dd><dt>브라우저</dt><dd>{d.user_agent}</dd><dt>요청일</dt><dd>{date(d.created)}</dd><dt>유효기간</dt><dd>{date(d.expires)}</dd></dl>
    <p>브라우저 정보는 요청자가 보내는 참고 정보입니다. 이름·소속을 별도로 확인하세요.</p>
    {d.reason && <p>이전 처리: {d.reason}</p>}
    {!expired && <><label>처리 사유 · 요청자에게 표시<textarea aria-label={`${d.device_name} 처리 사유`} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} placeholder="예: 연구실 소속과 사용자 확인 완료" /></label><div className="access-actions">
      {d.status !== "APPROVED" && <button className="primary-button" disabled={busy || !reason.trim()} onClick={() => decide("APPROVED")}>접속 승인</button>}
      {d.status === "PENDING" && <button className="outline-button" disabled={busy || !reason.trim()} onClick={() => decide("REJECTED")}>요청 거절</button>}
      {d.status === "APPROVED" && <button className="outline-button" disabled={busy || !reason.trim()} onClick={() => decide("REVOKED")}>접속 권한 철회</button>}
    </div></>}{error && <ErrorBox error={error} />}
  </article>;
}
