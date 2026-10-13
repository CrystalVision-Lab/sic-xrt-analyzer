import { chromium } from "playwright";
import { readFile, writeFile, mkdir } from "node:fs/promises";
const origin = process.env.XRT_QA_ORIGIN ?? "http://127.0.0.1:18770";
const out =
  process.env.XRT_QA_OUTPUT ?? "../artifacts/distribution120/browser-v1";
await mkdir(out, { recursive: true });
const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
});
const page = await context.newPage();
const errors = [];
const reports = [];
page.on("pageerror", (e) => errors.push(e.message));
try {
  for (const width of [390, 1100, 1440]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    for (const [path, name] of [
      ["/", "download"],
      ["/releases", "releases"],
      ["/guide", "guide"],
      ["/admin", "admin-login"],
    ]) {
      await page.goto(origin + path);
      await page.waitForLoadState("networkidle");
      await page.screenshot({
        path: `${out}/${name}-${width}.png`,
        fullPage: true,
      });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth + 1,
      );
      if (overflow)
        throw new Error("Horizontal page overflow " + path + " " + width);
      reports.push({
        path,
        width,
        title: await page.title(),
        horizontalOverflow: overflow,
      });
    }
  }
  if (process.env.XRT_QA_PUBLIC_ONLY === "1") {
    for (const path of [
      "/portal-api/admin/releases",
      "/portal-api/research/admin/statistics",
      "/api/v1/admin/statistics",
      "/api/v1/admin/portal/projects",
    ]) {
      const r = await page.request.get(origin + path);
      if (r.status() !== 401)
        throw new Error(
          "Anonymous research access: " + path + " " + r.status(),
        );
      reports.push({ path, anonymousStatus: r.status() });
    }
    await writeFile(
      `${out}/report.json`,
      JSON.stringify(
        {
          status: "PASS",
          origin,
          errors,
          reports,
          actualAdminAuthenticated: false,
          credentialRead: false,
        },
        null,
        2,
      ),
    );
    console.log(
      JSON.stringify({
        status: "PASS",
        cases: reports.length,
        errors: errors.length,
        anonymousOnly: true,
      }),
    );
  } else {
    // Private credential is read locally and supplied only to the intended same-origin login.
    // Never print it, put it in a URL, record a trace or save authenticated screenshots to Git.
    if (!["localhost", "127.0.0.1"].includes(new URL(origin).hostname)) throw new Error("Authenticated QA is restricted to localhost; use XRT_QA_PUBLIC_ONLY=1 for public URLs");
    const credential = JSON.parse(
      await readFile("../artifacts/sync106-private/admin.json", "utf8"),
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(origin + "/admin");
    await page.getByLabel("관리자 client ID").fill(credential.client_id);
    await page.getByLabel("관리자 인증키").fill(credential.credential);
    await page.getByRole("button", { name: "관리자 콘솔 접속" }).click();
    await page
      .getByRole("heading", { name: "연구 운영 현황" })
      .waitFor({ timeout: 30000 });
    for (const [path, name] of [
      ["/admin", "overview"],
      ["/admin/releases", "version-manager"],
      ["/admin/models", "model-evidence"],
      ["/admin/projects", "collected-projects"],
      ["/admin/batches", "sync-history"],
      ["/admin/users", "users"],
      ["/admin/audit", "audit"],
    ]) {
      await page.goto(origin + path);
      await page.waitForLoadState("networkidle");
      if (await page.locator("[role=alert]").count())
        throw new Error("Admin data load failed: " + path);
      await page.screenshot({
        path: `${out}/private-${name}.png`,
        fullPage: true,
      });
      reports.push({ path, authenticated: true });
    }
    if (
      (await page.evaluate(
        () =>
          Object.keys(localStorage).filter(k=>k!=="xrt-theme:v1").length + Object.keys(sessionStorage).length,
      )) !== 0
    )
      throw new Error("Unexpected browser credential storage");
    await page.getByRole("button", { name: "로그아웃" }).click();
    await page.getByRole("heading", { name: "연구 관리자 로그인" }).waitFor();
    if (errors.length) throw new Error("Browser errors: " + errors.join(";"));
    await writeFile(
      `${out}/report.json`,
      JSON.stringify(
        {
          status: "PASS",
          origin,
          errors,
          reports,
          actualAdminAuthenticated: true,
          credentialPrinted: false,
        },
        null,
        2,
      ),
    );
    console.log(
      JSON.stringify({
        status: "PASS",
        cases: reports.length,
        errors: errors.length,
      }),
    );
  }
} catch (e) {
  await writeFile(
    `${out}/report.json`,
    JSON.stringify(
      { status: "FAIL", error: String(e), errors, reports },
      null,
      2,
    ),
  );
  throw e;
} finally {
  await browser.close();
}
