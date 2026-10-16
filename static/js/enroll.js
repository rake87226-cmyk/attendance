const $ = id => document.getElementById(id);
const video = $("video"), msg = $("msg");
let samples = [], camOn = false;

function say(t, cls = "info") { msg.textContent = t; msg.className = "status " + cls; }
function refreshButtons() {
  $("btnCapture").disabled = !camOn || samples.length >= 3;
  $("btnSave").disabled = samples.length < 3;
  $("btnCapture").textContent = `Capture face (${samples.length}/3)`;
}

$("btnReader").onclick = () => connectReader(uid => { $("uid").value = uid; say("Card read: " + uid, "ok"); },
  s => $("readerState").textContent = s);
autoConnectReader(uid => { $("uid").value = uid; }, s => $("readerState").textContent = s);

$("btnCam").onclick = async () => {
  try { await startCamera(video); camOn = true; refreshButtons(); say("Camera on."); }
  catch (e) { say("Camera error: " + e.message, "bad"); }
};

$("btnCapture").onclick = async () => {
  const det = await detectFace(video);
  if (!det) return say("No face found. Look at the camera and try again.", "bad");
  samples.push(Array.from(det.descriptor));
  refreshButtons();
  say(`Sample ${samples.length}/3 captured.`, "ok");
};

$("btnSave").onclick = async () => {
  const body = { name: $("name").value, roll_no: $("roll").value, card_uid: $("uid").value, descriptors: samples };
  const r = await postJSON("/api/enroll", body);
  if (!r.ok) return say(r.data.error || "Save failed", "bad");
  say("Student saved.", "ok");
  samples = [];
  ["name", "roll", "uid"].forEach(i => $(i).value = "");
  stopCamera(video); camOn = false; refreshButtons();
  loadStudents();
};

async function loadStudents() {
  const r = await api("/api/students");
  const tb = document.querySelector("#studentsTable tbody");
  if (!r.ok) return;
  tb.innerHTML = "";
  r.data.forEach(s => {
    const tr = document.createElement("tr");
    [s.name, s.roll_no, s.card_uid].forEach(v => { const td = document.createElement("td"); td.textContent = v; tr.appendChild(td); });
    const td = document.createElement("td");
    const b = document.createElement("button");
    b.className = "btn"; b.textContent = "Delete";
    b.onclick = async () => { if (confirm("Delete " + s.name + " and their attendance?")) { await api("/api/students/" + s.id, { method: "DELETE" }); loadStudents(); } };
    td.appendChild(b); tr.appendChild(td); tb.appendChild(tr);
  });
}

loadModels().then(() => say("Models ready. Connect the reader, tap a card, start the camera.", "ok"))
  .catch(() => say("Could not load face models (check internet).", "bad"));
loadStudents();
refreshButtons();
