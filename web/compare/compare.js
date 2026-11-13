// Drop page: hands two PDFs to the worker and shows the result in a sandboxed frame.
// The frame has an opaque origin (sandbox without allow-same-origin), so even a rendering bug could not reach this page or the site;
// the only channel back is postMessage, checked against the frame's own window.
(() => {
  const $ = (id) => document.getElementById(id);
  const files = { old: null, new: null };
  let ready = false;
  let busy = false;
  let pages = null;
  let pendingAnchor = "";
  const frame = $("out");
  const worker = new Worker("worker.js");

  function status(text, kind) {
    const el = $("status");
    el.textContent = text;
    el.className = kind || "";
  }

  function refresh() {
    $("go").disabled = !(ready && !busy && files.old && files.new);
  }

  for (const side of ["old", "new"]) {
    const drop = $("drop-" + side);
    const input = $("file-" + side);
    const take = (file) => {
      if (!file) return;
      files[side] = file;
      $("name-" + side).textContent = file.name;
      drop.classList.add("ready");
      refresh();
    };
    input.addEventListener("change", () => take(input.files[0]));
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", (e) => {
      e.preventDefault();
      drop.classList.remove("over");
      take(e.dataTransfer.files[0]);
    });
  }

  function show(view, anchor) {
    if (!pages || !(view in pages)) return;
    pendingAnchor = /^[\w-]*$/.test(anchor || "") ? anchor || "" : "";
    frame.srcdoc = pages[view];
    $("view-index").setAttribute("aria-pressed", String(view === "index"));
    $("view-document").setAttribute("aria-pressed", String(view === "document"));
  }

  frame.addEventListener("load", () => {
    if (pendingAnchor) frame.contentWindow.postMessage({ bd: "scroll", anchor: pendingAnchor }, "*");
    pendingAnchor = "";
  });

  window.addEventListener("message", (e) => {
    if (e.source !== frame.contentWindow || !e.data || e.data.bd !== "view") return;
    show(String(e.data.view), String(e.data.anchor || ""));
  });

  $("view-index").addEventListener("click", () => show("index"));
  $("view-document").addEventListener("click", () => show("document"));

  let onResult = null;
  worker.onmessage = (e) => {
    const m = e.data;
    if (m.type === "status") status(m.text, "busy");
    else if (m.type === "ready") { ready = true; status("Ready. Drop two PDFs."); refresh(); }
    else if (m.type === "fatal") status("The comparison engine could not start in this browser: " + m.text, "err");
    else if (onResult) onResult(m);
  };

  function request(message, transfer) {
    return new Promise((resolve) => {
      onResult = (m) => { onResult = null; resolve(m); };
      worker.postMessage(message, transfer || []);
    });
  }

  async function finish(m) {
    busy = false;
    refresh();
    if (m.type === "error") { status(m.text, "err"); return m; }
    pages = m.result.pages;
    frame.hidden = false;
    $("views").hidden = false;
    show("index");
    const c = m.result.counts;
    status(`Done in ${m.seconds.toFixed(1)}s: ${c.new || 0} new, ${c.dropped || 0} dropped, ${c.substantive || 0} substantively changed sections.`);
    return m;
  }

  $("go").addEventListener("click", async () => {
    busy = true;
    refresh();
    status("Comparing. A long report can take a minute…", "busy");
    const [oldBytes, newBytes] = await Promise.all([files.old.arrayBuffer(), files.new.arrayBuffer()]);
    const m = await request(
      { type: "compare", old: { name: files.old.name, bytes: oldBytes }, new: { name: files.new.name, bytes: newBytes } },
      [oldBytes, newBytes],
    );
    finish(m);
  });

  // Used by scripts/check_compare_page.mjs to push hostile text through the renderer.
  window.bdSelftest = async (oldText, newText) => {
    busy = true;
    refresh();
    return finish(await request({ type: "selftest", oldText, newText }));
  };
})();
