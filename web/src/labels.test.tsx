import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { LabelDashboard, type LabelSummary } from "./Labels";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const json = (data: unknown) => Promise.resolve({ ok: true, json: async () => data });

const summary: LabelSummary = {
  events: 9, labeled_candidates: 6, decisions: { TED: 3, TSD: 1, NOT_DEFECT: 2 },
  class_labels: { BPD: 0, TED: 3, TSD: 1 }, not_defect: 2, unsure: 0,
  confusion: { TED: { TED: 3, NOT_DEFECT: 2 }, TSD: { TSD: 1 } },
  model_agreement: 0.6667, random_sample: { labels: 4, model_agreement: 0.75 }, crops: 3,
  weekly: [{ week: "2026-W42", TED: 3, TSD: 1, NOT_DEFECT: 2 }],
  reviewers: [{ user_id: "u1", name: "Synthetic reviewer", labels: 6, events: 9, last_7_days: 6, last_at: "2026-10-18T01:00:00+00:00" }],
  conflicts: 1, conflict_examples: [{ source_sha256: "a".repeat(64), candidate_id: "cand-1", decisions: { u1: "TED", u2: "NOT_DEFECT" } }],
};

it("reads the label summary through the research proxy and shows readiness", async () => {
  const fetcher = vi.fn(() => json(summary));
  vi.stubGlobal("fetch", fetcher);
  render(<LabelDashboard />);
  expect(await screen.findByText("Synthetic reviewer")).toBeTruthy();
  expect(String((fetcher.mock.calls[0] as unknown[])[0])).toBe("/portal-api/research/admin/labels/summary");
  expect(screen.getByRole("meter", { name: "TED 라벨" }).getAttribute("aria-valuenow")).toBe("3");
  expect(screen.getByText("75%")).toBeTruthy();
  expect(screen.getByText(/Synthetic reviewer: TED · u2: 결함 아님/)).toBeTruthy();
});

it("explains how labels arrive when none exist yet", async () => {
  vi.stubGlobal("fetch", vi.fn(() => json({ ...summary, events: 0 })));
  render(<LabelDashboard />);
  expect(await screen.findByText("아직 수집된 라벨이 없습니다")).toBeTruthy();
});
