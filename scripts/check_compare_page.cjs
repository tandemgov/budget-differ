// Browser check for the in-browser comparison page (demo/compare/), run before every Pages deploy.
//
//   uv run budget-differ compare-page --runtime && node scripts/check_compare_page.cjs
//
// Serves demo/ locally, loads the page in Chromium, and checks that:
//   - the S. 2257 -> FY2027 committee print comparison matches the command-line result;
//   - a bill paired with a report, and a non-GPO PDF, are refused with a message;
//   - hostile text pushed through the renderer runs no script, and nothing violates the page's Content-Security-Policy;
//   - the results frame is sandboxed without same-origin access, and its view links work through the message bridge.
const http = require("http");
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "..");
const DEMO = path.join(ROOT, "demo");
const PRE = path.join(ROOT, "prerelease");
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".wasm": "application/wasm", ".zip": "application/zip", ".whl": "application/zip" };

function serve() {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(new URL(req.url, "http://x").pathname).replace(/\/$/, "/index.html");
    const file = path.join(DEMO, rel);
    if (!file.startsWith(DEMO) || !fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

// A one-page PDF set in Helvetica: valid, but not GPO typesetting.
function plainPdf() {
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    null,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  const stream = "BT /F1 12 Tf 72 720 Td (Quarterly newsletter, not an appropriations report.) Tj ET";
  objs[3] = `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`;
  let out = "%PDF-1.4\n";
  const offsets = [];
  objs.forEach((o, i) => { offsets.push(out.length); out += `${i + 1} 0 obj\n${o}\nendobj\n`; });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1");
}

const failures = [];
const check = (ok, what) => { console.log(`${ok ? "ok  " : "FAIL"} ${what}`); if (!ok) failures.push(what); };

(async () => {
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const cspViolations = [];
  let dialogs = 0;
  page.on("console", (m) => { if (/Content Security Policy|Refused to/.test(m.text())) cspViolations.push(m.text()); });
  page.on("dialog", (d) => { dialogs += 1; d.dismiss(); });
  page.on("frameattached", (f) => f.page().on("dialog", () => {}));

  await page.goto(`${base}/compare/index.html`);
  await page.waitForFunction(() => /Ready|could not start/.test(document.getElementById("status").textContent), null, { timeout: 180000 });
  check((await page.textContent("#status")).startsWith("Ready"), "page loads the Python runtime from the site");

  const compare = async (oldFile, newFile) => {
    await page.setInputFiles("#file-old", oldFile);
    await page.setInputFiles("#file-new", newFile);
    await page.click("#go");
    await page.waitForFunction(() => {
      const s = document.getElementById("status");
      return s.className === "err" || s.textContent.startsWith("Done");
    }, null, { timeout: 300000 });
    return page.textContent("#status");
  };

  const bill = await compare(path.join(PRE, "BILLS-119s2257rs.pdf"), path.join(PRE, "SAPPR-FY2027-LEGBRANCH-BILL.pdf"));
  console.log("     " + bill);
  check(/3 new, 6 dropped, 10 substantively changed/.test(bill), "bill comparison matches the command-line result (3 new, 6 dropped, 10 substantive)");

  const sandbox = await page.getAttribute("#out", "sandbox");
  check(sandbox === "allow-scripts", "results frame is sandboxed without allow-same-origin");
  const frameIsolated = await page.evaluate(() => {
    try { void document.getElementById("out").contentWindow.document.body; return false; } catch (e) { return true; }
  });
  check(frameIsolated, "host page cannot reach into the results frame (opaque origin)");

  await page.frameLocator("#out").locator("a.viewtab", { hasText: "Full" }).click();
  await page.waitForFunction(() => document.getElementById("view-document").getAttribute("aria-pressed") === "true", null, { timeout: 10000 });
  check(true, "view links inside the frame switch views through the message bridge");

  const mixed = await compare(path.join(PRE, "BILLS-119s2257rs.pdf"), path.join(PRE, "SAPPR-FY2027-LEGBRANCH-ES.pdf"));
  check(/bill and the other a report/.test(mixed), "a bill paired with a report is refused");

  const plain = path.join(require("os").tmpdir(), "not-gpo.pdf");
  fs.writeFileSync(plain, plainPdf());
  const refused = await compare(plain, path.join(PRE, "SAPPR-FY2027-LEGBRANCH-BILL.pdf"));
  check(/not GPO's report or bill type/.test(refused), "a non-GPO PDF is refused");

  const payloads = [
    "<script>parent.__pwned=1;alert(1)</script>",
    "<img src=x onerror=\"parent.__pwned=1;alert(2)\">",
    "\"><svg onload=alert(3)>",
    "javascript:alert(4)",
  ];
  const hostile = (n) => `
                                TITLE I

                          SENATE ${payloads[0]}

                     Expense Allowances ${payloads[2]}

    The Committee recommends $${n},000 for ${payloads[1]} allowances.
    Directive ${payloads[3]}.--The Committee directs ${payloads.join(" ")} within ${n} days.
`;
  const result = await page.evaluate(([a, b]) => window.bdSelftest(a, b).then((m) => m.type), [hostile(30), hostile(60)]);
  check(result === "result", "hostile text renders as a comparison");
  await page.waitForTimeout(1500);
  const pwned = await page.evaluate(() => window.__pwned === 1);
  check(!pwned && dialogs === 0, "no script from document text ran (no dialogs, host page untouched)");
  const escaped = await page.frameLocator("#out").locator("body").innerText();
  check(escaped.includes("<script>parent.__pwned=1"), "hostile markup is shown as text");
  check(cspViolations.length === 0, "no Content-Security-Policy violations" + (cspViolations.length ? `: ${cspViolations[0]}` : ""));

  await browser.close();
  server.close();
  if (failures.length) { console.error(`${failures.length} check(s) failed`); process.exit(1); }
  console.log("all checks passed");
})().catch((e) => { console.error(e); process.exit(1); });
