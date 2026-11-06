const $ = (id) => document.getElementById(id);
let findings = [];
const names = { private_person:"Name", private_email:"Email", private_phone:"Phone", private_address:"Address",
  private_url:"Web address", private_date:"Date", account_number:"Account or ID number", secret:"Secret" };

function status(msg, err=false) { $("status").textContent = msg; $("status").className = err ? "err" : ""; }

// Every call to the app gets a time limit, and every way it can fail becomes a sentence the user can act on.
// Without the limit, a stuck app leaves "Reading the document..." on the page forever. 70 s is a little longer than
// Caddy's 60 (see the Caddyfile), so for a stuck app Caddy's clearer 504 arrives first.
const LIMIT_MS = 70000;
async function ask(path, body) {
  try {
    const r = await fetch(path, { method:"POST", body, signal: AbortSignal.timeout(LIMIT_MS) });
    const j = r.ok && r.headers.get("content-type") === "application/pdf" ? null : await r.json().catch(() => ({}));
    return { r, j };
  } catch (e) {      // no answer at all: the time limit ran out, or the network is down
    return { r: null, j: {} };
  }
}
function problem({ r, j }) {
  if (!r) return "Need to Know did not answer in time. Nothing was kept. Try again in a moment.";
  if (r.status === 429) return `${j.detail}. Try again in ${r.headers.get("Retry-After")} seconds.`;
  if (j.detail) return j.detail;   // our own app's explanation (415, 422, 503 while loading, ...)
  return "Need to Know is not answering right now. Nothing was kept. Try again in a minute.";   // 502 or 504
}

$("find").onclick = async () => {
  const f = $("file").files[0];
  if (!f) { status("Choose a PDF first.", true); return; }
  status("Reading the document..."); $("review").hidden = true;
  const body = new FormData(); body.append("file", f);
  const answer = await ask("/api/detect", body);
  if (!answer.r || !answer.r.ok) { status(problem(answer), true); return; }
  const j = answer.j;
  findings = j.findings;
  $("count").textContent = `${findings.length} item${findings.length===1?"":"s"} found`;
  $("meta").textContent = `in ${j.pages} page${j.pages===1?"":"s"}, by the ${j.detector} detector, in ${j.seconds}s. Uncheck anything you want to keep.`;
  $("rows").innerHTML = "";
  for (const x of findings) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><input type="checkbox" checked data-id="${x.id}"></td><td>${names[x.label]||x.label}</td><td class="t"></td><td>${x.page+1}</td>`;
    tr.querySelector(".t").textContent = x.text;
    $("rows").appendChild(tr);
  }
  $("review").hidden = false;
  status(findings.length ? "Review the list, then download." : "Nothing found. That does not mean there is nothing there: check the document yourself.");
};

const boxes = () => [...document.querySelectorAll("#rows input[type=checkbox]")];
$("all").onclick = () => boxes().forEach(b => b.checked = true);
$("none").onclick = () => boxes().forEach(b => b.checked = false);

$("redact").onclick = async () => {
  const f = $("file").files[0];
  const chosen = boxes().filter(b => b.checked).map(b => findings[+b.dataset.id]).map(x => ({ page:x.page, text:x.text }));
  if (!chosen.length) { status("Nothing is selected.", true); return; }
  status("Removing...");
  const body = new FormData(); body.append("file", f); body.append("remove", JSON.stringify(chosen));
  body.append("unchecked", boxes().length - chosen.length);   // how many the user decided weren't personal (a count)
  const answer = await ask("/api/redact", body);
  if (!answer.r || !answer.r.ok) { status(problem(answer), true); return; }
  const blob = await answer.r.blob(); const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = f.name.replace(/\.pdf$/i, "") + "-redacted.pdf"; a.click();
  status(`Removed ${chosen.length} item${chosen.length===1?"":"s"}. Open the download and check it before you share it.`);
};

fetch("/api/stats").then(r => r.json()).then(s => {
  if (s.counting) $("stats").textContent = `So far: ${s.documents.toLocaleString()} documents checked, ${s.items_found.toLocaleString()} items found.`;
});
