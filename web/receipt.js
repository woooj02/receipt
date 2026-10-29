"use strict";
const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const lines = (id) => $(id).value.split("\n").map((value) => value.trim()).filter(Boolean);
// Image failures do not bubble; capture also covers receipt cards added later.
document.addEventListener("error", (event) => {
  if (event.target instanceof HTMLImageElement && event.target.classList.contains("place-image")) event.target.remove();
}, true);
let current = null, revisionOf = null, issuedReceipt = null, batchResult = null;
let busy = false, activeJob = null, view = "audit", liveConfigured = false;
const contextInputs = ["anchors", "city", "policy", "demo", "category", "useVenue", "venueLabel", "venueLat", "venueLon", "venueRadius"];

async function api(path, options) {
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); }
  catch (_) { throw new Error("The service returned an unreadable response."); }
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((row) => row.msg).join(" · ") : data.detail;
    throw new Error(detail || "The request could not complete.");
  }
  return data;
}
const post = (path, payload) => api(path, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});

function setBusy(value) {
  busy = value;
  contextInputs.forEach((id) => { $(id).disabled = value || Boolean(revisionOf); });
  ["candidates", "loadSample", "loadLiveExample", "heroLiveExample", "applySuggestions", "beginRevision", "approve", "auditButton", "runBatch", "loadBatchSample", "importBatch", "batchFile", "batchJSON", "agentMode", "agentGoal", "tabAudit", "tabAgent", "tabBatch"].forEach((id) => { $(id).disabled = value; });
}
function invalidate() {
  current = null;
  issuedReceipt = null;
  $("approval").classList.remove("visible");
  $("issued").classList.remove("visible");
  $("snapshotNote").hidden = false;
  $("snapshotNote").textContent = revisionOf
    ? "Revision mode keeps the tastes, city, category, radius and policy fixed. Enter the agent's changed list."
    : "Inputs changed. Run an audit before confirming another result.";
}
function showView(nextView) {
  if (busy) return;
  const changed = nextView !== view;
  view = nextView;
  if (changed) {
    invalidate();
    $("result").classList.remove("visible");
    $("agentTimeline").hidden = true;
  }
  ["Audit", "Agent", "Batch"].forEach((name) => {
    const selected = nextView === name.toLowerCase();
    $("tab" + name).setAttribute("aria-selected", String(selected));
    $("tab" + name).tabIndex = selected ? 0 : -1;
  });
  $("auditWorkspace").hidden = nextView === "batch";
  $("batchWorkspace").hidden = nextView !== "batch";
  $("loadLiveExample").hidden = !liveConfigured || nextView === "batch";
  $("loadLiveExample").textContent = nextView === "agent" ? "Run live Qloo agent example" : "Run live Denver example";
  $("exampleSource").hidden = true;
  $("auditWorkspace").setAttribute("aria-labelledby", nextView === "agent" ? "tabAgent" : "tabAudit");
  $("candidateField").hidden = nextView === "agent";
  $("demoChoice").hidden = nextView === "agent";
  $("agentField").hidden = nextView !== "agent";
  $("candidates").required = nextView === "audit";
  $("agentGoal").required = nextView === "agent";
  $("auditButton").textContent = nextView === "agent" ? "Run agent loop →" : "Audit recommendations →";
  $("formTitle").textContent = nextView === "agent" ? "Agent revision loop" : "Recommendation audit";
  $("formHint").textContent = nextView === "agent" ? "Propose → critique → revise → re-audit" : "Review every proposed place.";
  if (nextView === "agent") revisionOf = null;
  setBusy(false);
}
["Audit", "Agent", "Batch"].forEach((name, index, names) => {
  $("tab" + name).onclick = () => showView(name.toLowerCase());
  $("tab" + name).onkeydown = (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const next = (index + (event.key === "ArrowRight" ? 1 : -1) + names.length) % names.length;
    $("tab" + names[next]).click();
    $("tab" + names[next]).focus();
  };
});
contextInputs.concat(["candidates", "agentGoal", "agentMode"]).forEach((id) => {
  $(id).addEventListener("input", invalidate);
  $(id).addEventListener("change", invalidate);
});
$("useVenue").addEventListener("change", () => { $("venueFields").hidden = !$("useVenue").checked; });

api("/api/health").then((health) => {
  $("mode").textContent = health.mode;
  liveConfigured = health.qloo === "configured";
  $("heroLiveExample").hidden = !liveConfigured;
  $("loadLiveExample").hidden = !liveConfigured || view === "batch";
  $("agentMode").querySelector('[value="qloo"]').disabled = !health.qloo_agent_enabled;
  if (health.qloo_agent_enabled) $("agentMode").value = "qloo";
  if (health.live_agent_enabled) {
    $("agentMode").querySelector('[value="live"]').disabled = false;
    $("agentMode").querySelector('[value="live"]').textContent = "Live configured model";
  }
  updateAgentSource();
}).catch(() => { $("mode").textContent = "Service unavailable"; });

function updateAgentSource() {
  const mode = $("agentMode").value;
  $("agentGoal").readOnly = mode === "qloo";
  $("agentSourceHelp").textContent = mode === "qloo"
    ? "Starts with the highest-rated places in the comparison pool, without using personal tastes. Receipt checks that draft, and explicit rules revise any misses. Task text is informational; no LLM calls."
    : mode === "scripted" ? "Synthetic places and scores demonstrate the workflow. No model generated these proposals."
    : "A configured model generates and revises proposals. Receipt evaluates them separately; model calls use the server's allowance.";
}
$("agentMode").addEventListener("change", updateAgentSource);

function constraintsPayload() {
  let venue = null;
  if ($("useVenue").checked) {
    venue = {label:$("venueLabel").value.trim(), latitude:Number($("venueLat").value),
      longitude:Number($("venueLon").value), radius_m:Number($("venueRadius").value)};
    if (!venue.label || !Number.isFinite(venue.latitude) || !Number.isFinite(venue.longitude) ||
        !$("venueLat").value || !$("venueLon").value) throw new Error("Provide a venue label and valid coordinates.");
  }
  return {category:$("category").value, venue};
}
function loadSyntheticForm() {
  $("exampleSource").hidden = true;
  revisionOf = null;
  $("anchors").value = "Kendrick Lamar\nEverything Everywhere All at Once\nThe Bear";
  $("candidates").value = "Harbor Street Grill\nCopper Kettle\nNightjar Lounge";
  $("city").value = "Denver, Colorado";
  $("policy").value = "standard";
  $("category").value = "restaurant";
  $("demo").checked = true;
  $("useVenue").checked = true;
  $("venueFields").hidden = false;
  $("venueLabel").value = "Demo Concert Hall";
  $("venueLat").value = "39.74";
  $("venueLon").value = "-104.99";
  $("venueRadius").value = "5000";
  $("agentMode").value = "scripted";
  updateAgentSource();
  invalidate();
  setBusy(false);
}
$("loadSample").onclick = () => { loadSyntheticForm(); $("auditForm").requestSubmit(); };
$("loadLiveExample").onclick = () => {
  if (!liveConfigured || busy) return;
  revisionOf = null;
  const targetView = view === "agent" ? "agent" : "audit";
  showView(targetView);
  $("anchors").value = "Kendrick Lamar\nEverything Everywhere All at Once";
  $("candidates").value = "Work & Class\nTavernetta\nForest Room 5";
  $("city").value = "Denver, Colorado";
  $("policy").value = "personalized";
  $("category").value = "restaurant";
  $("demo").checked = false;
  $("useVenue").checked = true;
  $("venueFields").hidden = false;
  $("venueLabel").value = "The Mission Ballroom";
  $("venueLat").value = "39.776204";
  $("venueLon").value = "-104.969168";
  $("venueRadius").value = "5000";
  $("agentMode").value = "qloo";
  updateAgentSource();
  $("exampleSource").textContent = targetView === "agent"
    ? "Generic ratings agent: real Qloo data and explicit rules. It starts without tastes, then responds to Receipt's critique."
    : "Hand-entered example · real Qloo evidence near Mission Ballroom.";
  $("exampleSource").hidden = false;
  invalidate(); setBusy(false);
  $("auditForm").requestSubmit();
};
$("heroLiveExample").onclick = () => { if (!busy) { showView("audit"); $("loadLiveExample").click(); } };

async function runJob(kind, payload, isBatch) {
  const progressId = isBatch ? "batchProgress" : "runProgress";
  const phaseId = isBatch ? "batchPhase" : "runPhase";
  const elapsedId = isBatch ? "batchElapsed" : "runElapsed";
  $(progressId).hidden = false;
  $(phaseId).textContent = "Preparing…";
  const started = Date.now();
  try {
    let job = await post("/api/jobs/" + kind, payload);
    activeJob = job.job_id;
    while (["queued", "running"].includes(job.status)) {
      $(phaseId).textContent = job.phase;
      $(elapsedId).textContent = Math.floor((Date.now() - started) / 1000) + " seconds · private session · 180-second limit";
      await new Promise((resolve) => setTimeout(resolve, 400));
      job = await api("/api/jobs/" + encodeURIComponent(activeJob));
      if (Date.now() - started > 190000) throw new Error("The run exceeded its browser time limit.");
    }
    if (job.status !== "complete") throw new Error(job.error || "The run stopped without a result.");
    return job.result;
  } catch (error) {
    if (activeJob) post("/api/jobs/" + encodeURIComponent(activeJob) + "/cancel", {}).catch(() => {});
    throw error;
  } finally { activeJob = null; $(progressId).hidden = true; }
}
async function cancelActiveRun() {
  if (activeJob) {
    await post("/api/jobs/" + encodeURIComponent(activeJob) + "/cancel", {});
    $("runPhase").textContent = $("batchPhase").textContent = "Stopping at the next safe boundary…";
  }
}
$("cancelRun").onclick = () => cancelActiveRun().catch((error) => showError(error.message));
$("cancelBatch").onclick = () => cancelActiveRun().catch((error) => showError(error.message, true));

$("auditForm").onsubmit = async (event) => {
  event.preventDefault();
  if (busy) return;
  const anchors = lines("anchors"), candidates = lines("candidates");
  if (anchors.length < 2 || anchors.length > 5 || (view === "audit" && (candidates.length < 1 || candidates.length > 6))) {
    return showError("Use two to five anchors and one to six proposed places.");
  }
  let constraints;
  try { constraints = constraintsPayload(); } catch (error) { return showError(error.message); }
  const isAgent = view === "agent";
  const payload = isAgent
    ? {anchors, city:$("city").value.trim(), goal:$("agentGoal").value.trim(), mode:$("agentMode").value, policy:$("policy").value, constraints, max_rounds:3}
    : {anchors, candidates, city:$("city").value.trim(), policy:$("policy").value, constraints, demo:$("demo").checked, revision_of:revisionOf};
  invalidate(); clearError(); setBusy(true);
  $("auditButton").textContent = isAgent ? "Agent is working…" : "Auditing…";
  $("agentTimeline").hidden = true;
  try {
    const result = await runJob(isAgent ? "agent" : "audit", payload, false);
    if (isAgent) {
      current = result.final_audit;
      $("demo").checked = current.requested_demo;
      $("candidates").value = current.input_candidates.join("\n");
      renderAgent(result);
    } else current = result;
    revisionOf = null;
    renderAudit(current);
    $("snapshotNote").hidden = true;
  } catch (error) { showError(error.message); }
  finally {
    setBusy(false);
    $("auditButton").textContent = revisionOf ? "Audit revised list →" : isAgent ? "Run agent loop →" : "Audit recommendations →";
  }
};

function startRevision(snapshot) {
  const previous = snapshot.audit_id;
  showView("audit");
  revisionOf = previous;
  invalidate(); setBusy(false);
  $("auditButton").textContent = "Audit revised list →";
}
$("beginRevision").onclick = () => {
  if (!current || busy) return;
  startRevision(current);
  $("candidates").focus();
  $("candidates").scrollIntoView({behavior:"smooth", block:"center"});
};
$("applySuggestions").onclick = () => {
  if (!current || busy || !current.repairs.length) return;
  const snapshot = current;
  const kept = snapshot.candidates.filter((row) => row.status === "supported").map((row) => row.name);
  const changed = [...new Set(kept.concat(snapshot.repairs.map((row) => row.name)))].slice(0, snapshot.candidates.length);
  startRevision(snapshot);
  $("candidates").value = changed.join("\n");
  $("auditForm").requestSubmit();
};
$("approve").onclick = async () => {
  if (!current || !current.approval_eligible || busy) return;
  const snapshot = current;
  setBusy(true); clearError();
  try {
    const confirmation = await api("/api/review/" + encodeURIComponent(snapshot.audit_id));
    issuedReceipt = await post("/api/review/approve", confirmation);
    $("issuedText").textContent = "Confirmation recorded for " + issuedReceipt.approved_recommendations.length +
      " recommendation(s) · " + issuedReceipt.source.label + " · " + issuedReceipt.policy.name + ".";
    $("receiptPreview").innerHTML = '<p class="receipt-caption">YOUR REVIEWED PICKS · ' + esc(issuedReceipt.city) + '</p>' +
      issuedReceipt.approved_recommendations.map((item) => '<article class="receipt-pick"><h4>✓ ' + esc(item.name) + '</h4>' + placeDetails(item) +
      '<p>Taste rank ' + percentile(item.personal_percentile) + ' · ' +
      (issuedReceipt.source.mode === 'DEMO' ? 'Synthetic lift ' + lift(item.taste_lift) : 'Panel lift ' + lift(item.panel_lift)) + '</p>' +
      '<p>' + esc(anchorNote(item.anchor_removals)) + '</p></article>').join("");
    $("receiptCode").textContent = JSON.stringify(issuedReceipt, null, 2);
    $("issued").classList.add("visible");
    $("issued").scrollIntoView({behavior:"smooth", block:"nearest"});
  } catch (error) { showError(error.message); }
  finally { setBusy(false); }
};
function download(data, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type:"application/json"}));
  const link = document.createElement("a");
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("downloadReceipt").onclick = () => { if (issuedReceipt) download(issuedReceipt, issuedReceipt.receipt_id + ".json"); };
$("copyEndpoint").onclick = async () => {
  const endpoint = location.origin + "/api/agent/audit";
  try { await navigator.clipboard.writeText(endpoint); $("copyEndpoint").textContent = "Endpoint copied"; }
  catch (_) { $("copyEndpoint").textContent = endpoint; }
};

function renderAudit(data) {
  $("verdictTitle").textContent = data.verdict.title;
  $("verdictDetail").textContent = data.verdict.detail;
  $("verdictIcon").textContent = data.approval_eligible ? "✓" : "!";
  $("resultMode").textContent = $("mode").textContent = data.source.label;
  $("statusDot").classList.toggle("live", data.source.mode === "LIVE");
  $("fingerprint").textContent = "evidence #" + data.fingerprint.slice(0, 8);
  $("universeNote").textContent = data.scoring_coverage.scored + "/" + data.fixed_universe_count + " places compared · " + data.policy.name;
  $("candidateList").innerHTML = data.candidates.map((item) =>
    '<div class="candidate"><span class="status-line ' + esc(item.status) + '"></span>' +
    '<div><h4>' + esc(item.name) + ' · ' + esc(statusLabel(item.status)) + '</h4>' + placeDetails(item) + '<p>' + esc(item.reason) +
    '</p><p>' + esc(anchorNote(item.anchor_removals)) + '</p>' +
    (item.distance_m == null ? "" : '<p>' + esc(item.distance_m) + ' m straight-line from the supplied venue point.</p>') + '</div>' +
    '<div class="score" title="Percentile rank within this comparison set, not a probability of enjoyment">' + percentile(item.personal_percentile) + '<span>Taste rank</span></div>' +
    '<div class="score">' + lift(data.source.mode === "DEMO" ? item.taste_lift : item.panel_lift) + '<span>' +
    (data.source.mode === "DEMO" ? "synthetic lift" : "Panel lift") + '</span></div></div>').join("");
  const panel = data.reference_panel || {};
  $("panelDefinition").textContent = (panel.definition || "Reference panel unavailable for this source.") + " " +
    (panel.profiles || []).map((p) => p.label + ": " + p.anchors.join(" + ")).join("; ") + " " + (panel.reason || "");
  const suggestions = data.repairs || [];
  $("repair").hidden = suggestions.length === 0 || data.approval_eligible;
  $("repairList").innerHTML = suggestions.map((item) => '<div class="repair-item"><strong>' + esc(item.name) +
    '</strong><span>' + esc(item.reason) + '</span><b>Suggested</b></div>').join("");
  $("approval").classList.toggle("visible", data.approval_eligible);
  $("sourceBox").classList.toggle("demo", data.source.mode === "DEMO");
  $("sourceLabel").textContent = data.source.label;
  $("sourceDetail").textContent = data.source.detail;
  $("tags").innerHTML = data.anchors.map((anchor) => '<span class="tag">' + esc(anchor.resolved_name || anchor.name) + ' · ' + esc(anchor.resolution) + '</span>').join("");
  $("trace").innerHTML = data.trace.map((item) => '<li data-state="' + esc(item.state) +
    '"><div><strong>' + esc(item.step) + '</strong><span>' + esc(item.detail) + '</span></div></li>').join("");
  $("limitsList").innerHTML = data.limitations.map((item) => '<li>' + esc(item) + '</li>').join("");
  $("result").classList.add("visible");
  $("result").scrollIntoView({behavior:"smooth", block:"start"});
}
function renderAgent(result) {
  const first = new Map(result.rounds[0].audit.candidates.map((row) => [row.entity_id, row]));
  $("agentTimeline").innerHTML = result.rounds.map((round) => '<article class="round-card"><h3>Round ' + round.round +
    '</h3><span class="badge">' + esc(result.agent.label) + '</span><ul>' +
    round.audit.candidates.map((row) => '<li><strong>' + esc(row.name) + '</strong> · ' + percentile(row.personal_percentile) +
      ' · ' + esc(statusLabel(row.status)) + (round.round > 1 ? (first.has(row.entity_id) ? ' · retained' : ' · replaces an earlier pick') : '') + '</li>').join("") +
    '</ul><p>' + esc(round.audit.verdict.title) + '</p><p>' + esc(round.proposal.note) +
    '</p><strong>' + round.audit.candidates.filter((row) => row.status === 'supported').length + '/' + round.audit.candidates.length +
    ' supported</strong></article>').join("");
  $("agentTimeline").hidden = false;
}

function syntheticBatch() {
  const tastes = [
    ["Kendrick Lamar", "Everything Everywhere All at Once"], ["Taylor Swift", "Little Women"],
    ["Miles Davis", "The Royal Tenenbaums"], ["Beyoncé", "The Bear"], ["Radiohead", "Arrival"],
    ["Bad Bunny", "Spirited Away"], ["Nina Simone", "Beloved"], ["Daft Punk", "Tron"],
    ["Dolly Parton", "Pride and Prejudice"], ["Björk", "Dune"]
  ];
  const picks = [
    ["Harbor Street Grill", "Copper Kettle", "Nightjar Lounge"], ["Juniper House", "Copper Kettle", "Nightjar Lounge"],
    ["Cobalt Noodles", "Juniper House", "Unknown Sample Bistro"]
  ];
  const profiles = [];
  tastes.forEach((anchors, index) => {
    [1, 2].forEach((repeat) => profiles.push({
      profile_id:"synthetic-taste-" + (index + 1) + "-run-" + repeat,
      control_group:"synthetic-taste-" + (index + 1), anchors,
      recommendations:picks[(index + (repeat === 2 && index % 3 === 0 ? 1 : 0)) % picks.length]
    }));
  });
  return {agent_name:"Synthetic fixture captures · no real model", agent_version:"scripted-v1", prompt_version:"synthetic-example-v1",
    captured_at:new Date().toISOString(), city:"Denver, Colorado", profiles, demo:true, policy:"standard",
    constraints:{category:"restaurant", venue:null}};
}
$("loadBatchSample").onclick = () => {
  $("batchJSON").value = JSON.stringify(syntheticBatch(), null, 2);
  $("batchError").classList.remove("visible");
  $("batchReport").hidden = true;
};
$("batchFile").onchange = async () => {
  const file = $("batchFile").files[0];
  if (!file) return;
  if (file.size > 131072) return showError("The JSON file must be smaller than 128 KB.", true);
  try {
    const text = await file.text();
    JSON.parse(text);
    $("batchJSON").value = text;
    $("batchReport").hidden = true;
  } catch (_) { showError("Choose a valid captured-output JSON file.", true); }
};
$("importBatch").onclick = () => $("batchFile").click();
$("batchJSON").addEventListener("input", () => {
  batchResult = null;
  $("batchReport").hidden = true;
});
$("runBatch").onclick = async () => {
  if (busy) return;
  let payload;
  try { payload = JSON.parse($("batchJSON").value); }
  catch (_) { return showError("Load a sample or import a valid captured-output JSON file first.", true); }
  $("batchError").classList.remove("visible");
  $("batchReport").hidden = true;
  setBusy(true);
  try {
    batchResult = await runJob("batch", payload, true);
    renderBatch(batchResult);
  } catch (error) { showError(error.message, true); }
  finally { setBusy(false); }
};
function renderBatch(data) {
  const metric = (label, value, note) => '<article class="metric"><span>' + label + '</span><b>' + rate(value) + '</b><p>' + esc(note) + '</p></article>';
  const m = data.metrics;
  const rows = data.profiles.map((profile) => {
    const count = (status) => profile.candidates.filter((item) => item.status === status).length;
    return '<tr><td><details><summary>' + esc(profile.profile_id) + '</summary>' +
      profile.candidates.map((item) => '<p>' + esc(item.name) + ' · ' + esc(item.status) + '</p>').join("") +
      '</details></td><td>' + count("supported") + '</td><td>' + count("shared_taste") + '</td><td>' + (data.metrics.generic_rate_available ? count("generic") : "—") + '</td><td>' +
      count("mismatch") + '</td><td>' + (count("unverified") + count("ineligible")) + '</td><td>' +
      profile.scoring_coverage.scored + '/' + profile.scoring_coverage.required + '</td></tr>';
  }).join("");
  $("batchReport").innerHTML =
    '<div class="report-source ' + (data.source.mode === "DEMO" ? "demo" : "") + '"><div><h3>' + esc(data.agent.name) +
    '</h3><p>' + esc(data.source.label) + ' · ' + data.profile_count + ' captures · ' + data.unique_taste_profile_count +
    ' taste profiles · ' + m.recommendation_count + ' submitted picks</p></div><button id="downloadBatch" class="button primary" type="button">Download report</button></div>' +
    '<div class="metric-grid">' +
    metric("Output variation (sensitivity)", m.sensitivity, "Independent of Qloo; output diversity does not establish quality.") +
    (data.reference_panel?.available ? metric("Low panel lift", m.low_panel_lift_rate, "Fit is at least P60, but lift is below 10 points versus the declared three-profile panel. Not population popularity.") :
    metric("Generic rate", m.generic_rate, m.generic_rate == null ? "Unavailable: no verified city-only affinity baseline." : "Clears fit but fails the policy's rank-lift bar. Qloo-relative.")) +
    metric("Mismatch rate", m.mismatch_rate, "Below the policy's fit bar in the fixed comparison set.") +
    metric("Unverified rate", m.unverified_rate, "Every unresolved or incompletely scored pick remains in the denominator.") +
    '</div><div class="report-context"><span>Comparison: ' + data.fixed_universe_count + ' places</span><span>Policy: ' +
    esc(data.policy) + '</span><span>Repeat-control variation: ' + rate(m.repeat_control_variation) +
    ' across ' + m.repeat_control_groups + ' groups</span><span>Constraint failures: ' + rate(m.constraint_failure_rate) + '</span></div>' +
    '<div class="profile-bars"><h3>Every submitted pick stays in the report</h3>' + data.profiles.map((profile) => {
      const total = profile.candidates.length;
      const groups = [['supported','Supported'],['shared_taste','Shared with panel'],['generic','Generic'],['mismatch','Mismatch'],['unverified','Unverified'],['ineligible','Outside constraints']];
      return '<div class="profile-bar"><span>' + esc(profile.profile_id) + '</span><div class="bar-track" role="img" aria-label="' +
        esc(groups.map(([s,label]) => label + ': ' + profile.candidates.filter((x) => x.status === s).length).join(', ')) + '">' +
        groups.map(([s,label]) => { const count = profile.candidates.filter((x) => x.status === s).length; return count ? '<span class="bar-' + s + '" style="width:' + (100*count/total) + '%" title="' + esc(label) + ': ' + count + '">' + count + '</span>' : ''; }).join('') + '</div></div>';
    }).join('') + '<p class="micro">Green: supported · Amber: shared/generic · Red: mismatch · Grey: unverified/outside constraints</p></div>' +
    '<div class="report-table"><table><thead><tr><th>Captured profile</th><th>Supported</th><th>Shared with panel</th><th>Generic</th><th>Mismatch</th><th>Unverified / ineligible</th><th>Coverage</th></tr></thead><tbody>' + rows +
    '</tbody></table></div><details class="limits"><summary>Reference panel and definitions</summary><p>' +
    esc(data.reference_panel?.definition || 'Panel unavailable for this source.') + '</p><p>' +
    esc((data.reference_panel?.profiles || []).map((p) => p.label + ': ' + p.anchors.join(' + ')).join('; ')) +
    '</p></details><ul class="report-limits">' + data.limitations.map((note) => '<li>' + esc(note) + '</li>').join("") + '</ul>';
  $("downloadBatch").onclick = () => download(data, data.suite_id + ".json");
  $("batchReport").hidden = false;
  $("batchReport").scrollIntoView({behavior:"smooth", block:"start"});
}
function anchorNote(effects) {
  if (!effects || !effects.length) return "Anchor-removal evidence unavailable.";
  const strongest = effects.reduce((best, effect) => effect.rank_drop > best.rank_drop ? effect : best);
  return strongest.rank_drop > 0
    ? "Removing " + strongest.anchor + " lowered this rank the most (" + Math.round(strongest.rank_drop * 100) + " points)."
    : "No single anchor removal lowered this rank in the tested set.";
}
function statusLabel(value) { return value === 'shared_taste' ? 'shared with panel' : value; }
function placeDetails(item) {
  const place = item.place || {};
  const contribution = (item.qloo_contributions || []).map((x) => x.anchor + ' ' + Math.round(x.score * 100) + '%').join(' · ');
  return (place.image_url ? '<img class="place-image" src="' + esc(place.image_url) + '" alt="' + esc(item.name) + '" loading="lazy" decoding="async" referrerpolicy="no-referrer">' : '') +
    (place.address ? '<p class="place-address">' + esc(place.address) + '</p>' : '') +
    (place.business_rating == null ? '' : '<p class="micro">Qloo venue rating: ' + esc(place.business_rating.toFixed(1)) + '/5' +
      (place.price_level == null ? '' : ' · Price level ' + esc(place.price_level) + '/4') + ' · metadata may change</p>') +
    (place.keywords?.length ? '<p class="micro">Venue keywords: ' + esc(place.keywords.slice(0,4).join(', ')) + '</p>' : '') +
    (contribution ? '<p class="contribution">Qloo contribution: ' + esc(contribution) + '</p>' : '');
}
function percentile(value) { return value == null ? "—" : Math.round(value * 100) + "/100"; }
function lift(value) { return value == null ? "—" : (value >= 0 ? "+" : "") + Math.round(value * 100) + " pts"; }
function rate(value) { return value == null ? "—" : Math.round(value * 100) + "%"; }
function showError(message, batch=false) { $(batch ? "batchError" : "error").textContent = message; $(batch ? "batchError" : "error").classList.add("visible"); }
function clearError() { $("error").textContent = ""; $("error").classList.remove("visible"); }
