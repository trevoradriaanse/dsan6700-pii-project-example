const $ = (id) => document.getElementById(id);
let findings = [];
const names = { private_person:"Name", private_email:"Email", private_phone:"Phone", private_address:"Address",
  private_url:"Web address", private_date:"Date", account_number:"Account or ID number", secret:"Secret" };

function status(msg, err=false) { $("status").textContent = msg; $("status").className = err ? "err" : ""; }

$("find").onclick = async () => {
  const f = $("file").files[0];
  if (!f) { status("Choose a PDF first.", true); return; }
  status("Reading the document..."); $("review").hidden = true;
  const body = new FormData(); body.append("file", f);
  const r = await fetch("/api/detect", { method:"POST", body });
  const j = await r.json();
  if (!r.ok) { status(j.detail || "Something went wrong.", true); return; }
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
  const r = await fetch("/api/redact", { method:"POST", body });
  if (!r.ok) { const j = await r.json(); status(j.detail || "Something went wrong.", true); return; }
  const blob = await r.blob(); const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = f.name.replace(/\.pdf$/i, "") + "-redacted.pdf"; a.click();
  status(`Removed ${chosen.length} item${chosen.length===1?"":"s"}. Open the download and check it before you share it.`);
};

fetch("/api/stats").then(r => r.json()).then(s => {
  if (s.counting) $("stats").textContent = `So far: ${s.documents.toLocaleString()} documents checked, ${s.items_found.toLocaleString()} items found.`;
});
