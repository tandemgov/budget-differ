// Runs budget-differ in Pyodide off the main thread, so the page stays responsive during a long comparison.
// Everything is served from this site (runtime/ is assembled by scripts/build_compare_page.py); nothing is fetched from elsewhere.
importScripts("runtime/runtime.js", "runtime/pyodide.js");

const ready = (async () => {
  postMessage({ type: "status", text: "Loading Python in your browser…" });
  const py = await loadPyodide({ indexURL: "runtime/" });
  postMessage({ type: "status", text: "Loading the PDF reader…" });
  await py.loadPackage("runtime/" + RUNTIME.pymupdf);
  const site = "/lib/python3.13/site-packages";
  for (const zip of ["runtime/" + RUNTIME.rapidfuzz, "app.zip"]) {
    py.unpackArchive(await (await fetch(zip)).arrayBuffer(), "zip", { extractDir: site });
  }
  py.FS.mkdirTree("/work");
  py.FS.writeFile("/work/lexicon.json", new Uint8Array(await (await fetch("lexicon.json")).arrayBuffer()));
  py.runPython("import web");
  return py;
})();

ready.then(
  () => postMessage({ type: "ready" }),
  (e) => postMessage({ type: "fatal", text: String(e) }),
);

function run(py, fn, args) {
  // Arguments travel as Python values, never as source text.
  const call = py.runPython("lambda fn, *a: __import__('json').dumps(getattr(__import__('web'), fn)(*a))");
  try {
    return call(fn, ...args);
  } finally {
    call.destroy();
  }
}

onmessage = async (e) => {
  const msg = e.data;
  let py;
  try {
    py = await ready;
  } catch (err) {
    return;
  }
  const t0 = performance.now();
  try {
    let out;
    if (msg.type === "compare") {
      py.FS.writeFile("/work/old.pdf", new Uint8Array(msg.old.bytes));
      py.FS.writeFile("/work/new.pdf", new Uint8Array(msg.new.bytes));
      out = run(py, "compare", ["/work/old.pdf", "/work/new.pdf", msg.old.name, msg.new.name, "/work/lexicon.json"]);
    } else if (msg.type === "selftest") {
      out = run(py, "compare_texts", [msg.oldText, msg.newText, "/work/lexicon.json"]);
    } else {
      return;
    }
    postMessage({ type: "result", result: JSON.parse(out), seconds: (performance.now() - t0) / 1000 });
  } catch (err) {
    const text = String(err.message || err);
    const last = text.trim().split("\n").pop() || text;
    const m = last.match(/^web\.InputError: (.*)$/);
    postMessage({ type: "error", text: m ? m[1] : "Something went wrong while comparing these files. " + last });
  }
};
