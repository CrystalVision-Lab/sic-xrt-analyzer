import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AccessPage, SiteDevices, SiteGate } from "./SiteAccess";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const json = (data: unknown) => Promise.resolve({ ok: true, json: async () => data });
const device = { id: "synthetic-device", status: "PENDING", name: "QA", affiliation: "Synthetic lab", device_name: "QA PC", platform: "Test", user_agent: "Test browser", created: 1, expires: 9999999999, revision: 0, reason: "" };

it("denies protected children and shows an access request instead", async () => {
  vi.stubGlobal("fetch", vi.fn(() => json({ allowed: false, device: null })));
  render(<MemoryRouter><Routes><Route element={<SiteGate />}><Route path="/" element={<p>Protected content</p>} /></Route><Route path="/access" element={<AccessPage />} /></Routes></MemoryRouter>);
  expect(await screen.findByRole("button", { name: "접속 승인 요청" })).toBeTruthy();
  expect(screen.queryByText("Protected content")).toBeNull();
});

it("submits browser information once and retains a pending request", async () => {
  const fetcher = vi.fn((url: string, options?: RequestInit) => json(options?.method === "POST" ? device : { allowed: false, device: url.includes("access") && fetcher.mock.calls.some(c => c[1]?.method === "POST") ? device : null }));
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter><AccessPage /></MemoryRouter>);
  fireEvent.change(await screen.findByLabelText("이름"), { target: { value: "QA" } });
  fireEvent.change(screen.getByLabelText("소속 · 연락처"), { target: { value: "Synthetic lab" } });
  fireEvent.change(screen.getByLabelText("기기 이름"), { target: { value: "QA PC" } });
  fireEvent.click(screen.getByRole("button", { name: "접속 승인 요청" }));
  expect(await screen.findByText("승인 대기")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "접속 승인 요청" })).toBeNull();
  const calls = fetcher.mock.calls.filter(c => c[1]?.method === "POST");
  expect(calls).toHaveLength(1);
  expect(JSON.parse(calls[0][1]!.body as string)).toMatchObject({ name: "QA", device_name: "QA PC", affiliation: "Synthetic lab" });
});

it("requires a reason and submits a CSRF-protected versioned approval", async () => {
  const fetcher = vi.fn((_url: string, options?: RequestInit) => json(options?.method === "POST" ? { status: "UPDATED" } : [device]));
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter><SiteDevices session={{ user: { id: "qa", client_id: "qa", name: "QA", role: "ADMIN" }, csrf: "synthetic-csrf", expires_at: 9999999999 }} /></MemoryRouter>);
  const approve = await screen.findByRole("button", { name: "접속 승인" });
  expect((approve as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText("QA PC 처리 사유"), { target: { value: "Identity verified" } });
  fireEvent.click(approve);
  await waitFor(() => expect(fetcher.mock.calls.some(c => c[1]?.method === "POST")).toBe(true));
  const call = fetcher.mock.calls.find(c => c[1]?.method === "POST")!;
  expect(call[0]).toBe("/portal-api/admin/site-devices/synthetic-device/state");
  expect(call[1]?.headers).toMatchObject({ "X-Xrt-Csrf": "synthetic-csrf" });
  expect(JSON.parse(call[1]!.body as string)).toEqual({ status: "APPROVED", revision: 0, reason: "Identity verified" });
});
