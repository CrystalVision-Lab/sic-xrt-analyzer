import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { date, number, useData } from "./api";
import { Empty, ErrorBox, Heading, Loading, Pill } from "./ui";

type Reviewer = { user_id: string; name: string; labels: number; events: number; last_7_days: number; last_at: string | null };
type Week = { week: string } & Record<string, number | string>;
type Conflict = { source_sha256: string; candidate_id: string; decisions: Record<string, string> };
export type LabelSummary = {
  events: number;
  labeled_candidates: number;
  decisions: Record<string, number>;
  class_labels: Record<string, number>;
  not_defect: number;
  unsure: number;
  confusion: Record<string, Record<string, number>>;
  model_agreement: number | null;
  random_sample: { labels: number; model_agreement: number | null };
  crops: number;
  weekly: Week[];
  reviewers: Reviewer[];
  conflicts: number;
  conflict_examples: Conflict[];
};

// Provisional per-class goals for the first retraining round; shown as guidance only.
const TARGET = 500;
const CLASSES = [
  { key: "BPD", label: "◆ BPD", color: "#E69F00" },
  { key: "TED", label: "▲ TED", color: "#56B4E9" },
  { key: "TSD", label: "■ TSD", color: "#CC79A7" },
  { key: "NOT_DEFECT", label: "✕ 결함 아님", color: "#8a979c" },
];
const DECISION_NAMES: Record<string, string> = { BPD: "BPD", TED: "TED", TSD: "TSD", NOT_DEFECT: "결함 아님", UNSURE: "보류" };
const percent = (v: number | null | undefined) => (typeof v === "number" ? `${Math.round(v * 1000) / 10}%` : "—");

export function LabelDashboard() {
  const [rev, setRev] = useState(0);
  const { data, error, loading } = useData<LabelSummary>("research/admin/labels/summary", rev);
  const action = <button className="outline-button" onClick={() => setRev((v) => v + 1)}><RefreshCw size={15} /> 새로고침</button>;
  return (
    <>
      <Heading eyebrow="LABELING" title="라벨 데이터 현황" action={action}>
        Desktop의 빠른 검수에서 보낸 판정이 재학습용 라벨로 얼마나 쌓였는지 봅니다. 실행 취소된 판정은 제외한 유효 판정 기준입니다.
      </Heading>
      {loading ? <Loading /> : error ? <ErrorBox error={error} /> : !data || data.events === 0 ? (
        <Empty title="아직 수집된 라벨이 없습니다">
          Desktop에서 분석 후 결과 패널의 &lsquo;빠른 검수 시작&rsquo;으로 판정하고 &lsquo;서버로 보내기&rsquo;를 누르면 여기에 쌓입니다.
        </Empty>
      ) : <Summary s={data} />}
    </>
  );
}

function Summary({ s }: { s: LabelSummary }) {
  const classTotal = Object.values(s.class_labels).reduce((a, b) => a + b, 0);
  const counts: Record<string, number> = { ...s.class_labels, NOT_DEFECT: s.not_defect };
  const peak = Math.max(1, ...s.weekly.map((w) => weekTotal(w)));
  return (
    <>
      <div className="stats-grid" aria-label="라벨 요약">
        <article className="stat"><div><span>검수된 후보</span></div><strong>{number(s.labeled_candidates)}</strong><small>판정 이벤트 {number(s.events)}건</small></article>
        <article className="stat"><div><span>결함 라벨</span></div><strong>{number(classTotal)}</strong><small>BPD·TED·TSD 확정</small></article>
        <article className="stat"><div><span>결함 아님</span></div><strong>{number(s.not_defect)}</strong><small>오탐을 줄이는 negative 라벨</small></article>
        <article className="stat"><div><span>연구원 간 충돌</span></div><strong>{number(s.conflicts)}</strong><small>같은 후보에 다른 판정</small></article>
      </div>
      <div className="admin-two">
        <section className="panel" aria-label="클래스별 준비도">
          <div className="panel-title"><h2>클래스별 준비도</h2><Pill>목표 {number(TARGET)}건 (임시)</Pill></div>
          {CLASSES.map((c) => {
            const value = counts[c.key] ?? 0;
            const ratio = Math.min(1, value / TARGET);
            return (
              <div className="label-bar" key={c.key}>
                <span style={{ color: c.color }}>{c.label}</span>
                <div className="label-bar-track" role="meter" aria-label={`${c.key} 라벨`} aria-valuemin={0} aria-valuemax={TARGET} aria-valuenow={value}>
                  <div className="label-bar-fill" style={{ width: `${ratio * 100}%`, background: c.color }} />
                </div>
                <strong>{number(value)}</strong>
                {value < TARGET * 0.3 && <small className="label-warn">부족</small>}
              </div>
            );
          })}
          <p className="label-note">보류 {number(s.unsure)}건은 학습에 쓰지 않습니다. 원본 조각 동의 {number(s.crops)}건.</p>
        </section>
        <section className="panel" aria-label="모델 일치율">
          <div className="panel-title"><h2>모델 일치율</h2></div>
          <div className="summary-line"><span>무작위 표본 기준 <small>(편향 없는 추정)</small></span><strong>{percent(s.random_sample.model_agreement)}</strong></div>
          <div className="summary-line"><span>무작위 표본 라벨</span><strong>{number(s.random_sample.labels)}</strong></div>
          <div className="summary-line"><span>전체 판정 기준 <small>(불확실 후보 위주라 낮게 나옴)</small></span><strong>{percent(s.model_agreement)}</strong></div>
          <p className="label-note">모델 점수는 보정된 확률이 아니며, 일치율은 검수자 판정과 모델 예측이 같은 비율입니다.</p>
        </section>
      </div>
      <section className="panel" aria-label="주별 검수 처리량">
        <div className="panel-title"><h2>주별 검수 처리량</h2><small>최근 12주 · 실행 취소 제외 판정 이벤트</small></div>
        <div className="week-chart">
          {s.weekly.map((w) => (
            <div className="week-col" key={w.week} title={`${w.week}: ${weekTotal(w)}건`}>
              <div className="week-stack" style={{ height: `${(weekTotal(w) / peak) * 100}%` }}>
                {[...CLASSES, { key: "UNSURE", label: "보류", color: "#d6ac64" }].map((c) =>
                  Number(w[c.key] || 0) > 0 ? <div key={c.key} style={{ flexGrow: Number(w[c.key]), background: c.color }} /> : null)}
              </div>
              <small>{String(w.week).slice(5)}</small>
              <strong>{number(weekTotal(w))}</strong>
            </div>
          ))}
        </div>
      </section>
      <div className="admin-two">
        <section className="panel" aria-label="연구원 활동">
          <div className="panel-title"><h2>연구원 활동</h2></div>
          <table>
            <thead><tr><th>연구원</th><th>유효 라벨</th><th>최근 7일</th><th>최근 활동</th></tr></thead>
            <tbody>{s.reviewers.map((r) => (
              <tr key={r.user_id}><td>{r.name}</td><td>{number(r.labels)}</td><td>{number(r.last_7_days)}</td><td>{date(r.last_at)}</td></tr>
            ))}</tbody>
          </table>
        </section>
        <section className="panel" aria-label="예측과 판정">
          <div className="panel-title"><h2>모델 예측 × 검수 판정</h2></div>
          <table>
            <thead><tr><th>예측 \ 판정</th>{Object.keys(DECISION_NAMES).map((d) => <th key={d}>{DECISION_NAMES[d]}</th>)}</tr></thead>
            <tbody>{Object.entries(s.confusion).map(([predicted, row]) => (
              <tr key={predicted}><th scope="row">{predicted}</th>{Object.keys(DECISION_NAMES).map((d) => <td key={d}>{number(row[d] || 0)}</td>)}</tr>
            ))}</tbody>
          </table>
        </section>
      </div>
      {s.conflicts > 0 && (
        <section className="panel" aria-label="충돌 목록">
          <div className="panel-title"><h2>판정 충돌</h2><Pill>{number(s.conflicts)}건</Pill></div>
          <p className="label-note">같은 후보에 연구원마다 다른 판정이 있습니다. 학습 반출 전에 합의가 필요합니다. 처음 50건까지 표시합니다.</p>
          <table>
            <thead><tr><th>후보</th><th>원본 SHA</th><th>판정</th></tr></thead>
            <tbody>{s.conflict_examples.map((c) => (
              <tr key={c.source_sha256 + c.candidate_id}>
                <td className="mono">{c.candidate_id}</td>
                <td className="mono">{c.source_sha256.slice(0, 12)}…</td>
                <td>{Object.entries(c.decisions).map(([who, d]) => `${nameOf(s, who)}: ${DECISION_NAMES[d] ?? d}`).join(" · ")}</td>
              </tr>
            ))}</tbody>
          </table>
        </section>
      )}
    </>
  );
}

function weekTotal(w: Week) {
  return Object.entries(w).reduce((sum, [k, v]) => (k === "week" ? sum : sum + Number(v || 0)), 0);
}

function nameOf(s: LabelSummary, id: string) {
  return s.reviewers.find((r) => r.user_id === id)?.name ?? id;
}
