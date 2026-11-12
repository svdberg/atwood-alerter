// Capture screenshots of the built frontend (elm-frontend/dist) for visual review.
//
// Usage: node screenshots/capture.mjs <distDir> <outDir>
//
// No server or AWS needed: Playwright serves dist/ from memory at
// http://localhost:4173 and answers API calls with fixtures/status.json.
// Build first with API_BASE_URL=http://localhost:4173/api ./build.sh

import { chromium } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const [distDir = "dist", outDir = "screenshots/out"] = process.argv.slice(2);
const ORIGIN = "http://localhost:4173";
const here = fileURLToPath(new URL(".", import.meta.url));
const status = await readFile(join(here, "fixtures", "status.json"), "utf8");
const admin = await readFile(join(here, "fixtures", "admin.json"), "utf8");

const TYPES = {
  ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml",
};

const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 800 },
  { name: "mobile", width: 390, height: 844 },
];

// Each scenario returns true if it applied; skipped scenarios produce no image.
const SCENARIOS = [
  { name: "main", run: async () => true },
  {
    name: "signup-dialog",
    run: async (page) => {
      // Pages without a signup dialog (e.g. an inline form) skip this scenario.
      const trigger = page.getByRole("button", { name: /get alerts|sign ?up|notify me/i }).first();
      if (!(await trigger.isVisible().catch(() => false))) return false;
      await trigger.click();
      return page.getByRole("dialog").waitFor({ timeout: 3000 }).then(() => true, () => false);
    },
  },
  {
    name: "admin",
    path: "/admin/index.html",
    run: async (page) => {
      await page.getByLabel("Admin secret").fill("fixture-secret");
      await page.getByRole("button", { name: "Log in" }).click();
      return page.getByRole("heading", { name: "Admin", exact: true }).waitFor({ timeout: 3000 }).then(() => true, () => false);
    },
  },
];

async function route(r) {
  const url = new URL(r.request().url());
  if (url.origin !== ORIGIN) return r.abort(); // no external network: deterministic shots
  if (url.pathname.startsWith("/api/status")) {
    return r.fulfill({ contentType: "application/json", body: status });
  }
  if (url.pathname === "/api/admin" && r.request().method() === "GET") {
    return r.fulfill({ contentType: "application/json", body: admin });
  }
  if (url.pathname.startsWith("/api/")) {
    return r.fulfill({ contentType: "application/json", body: '{"message":"ok"}' });
  }
  const path = url.pathname === "/" ? "/index.html" : url.pathname;
  try {
    const body = await readFile(join(resolve(distDir), path));
    return r.fulfill({ body, contentType: TYPES[extname(path)] ?? "application/octet-stream" });
  } catch {
    return r.fulfill({ status: 404, body: "not found" });
  }
}

await mkdir(outDir, { recursive: true });
const browser = await chromium.launch();
const shots = [];
const errors = [];
for (const vp of VIEWPORTS) {
  for (const sc of SCENARIOS) {
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      serviceWorkers: "block",
      colorScheme: "light",
    });
    const page = await context.newPage();
    page.on("pageerror", (e) => errors.push(`${vp.name}/${sc.name}: ${e.message}`));
    await page.route("**/*", route);
    await page.goto(ORIGIN + (sc.path ?? "/"), { waitUntil: "networkidle" });
    if (await sc.run(page)) {
      await page.waitForTimeout(300); // let transitions settle
      const file = `${vp.name}-${sc.name}.png`;
      await page.screenshot({ path: join(outDir, file), fullPage: true });
      shots.push(file);
    }
    await context.close();
  }
}
await browser.close();
await writeFile(join(outDir, "manifest.json"), JSON.stringify({ shots, errors }, null, 2));
console.log(JSON.stringify({ shots, errors }, null, 2));
