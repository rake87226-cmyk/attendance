const $ = id => document.getElementById(id);
const video = $("video"), statusEl = $("status"), logEl = $("log"), idle = $("idle");

const MATCH_THRESHOLD = 0.5;   // lower = stricter
const SCAN_TIMEOUT_MS = 15000;
const BLINK_CLOSED_RATIO = 0.72;

let modelsReady = false, busy = false;

function setStatus(text, cls = "info") { statusEl.textContent = text; statusEl.className = "status big " + cls; }
function addLog(text, cls) {
  const li = document.createElement("li");
  li.textContent = new Date().toLocaleTimeString() + " - " + text;
  li.className = cls === "ok" ? "ok-t" : cls === "bad" ? "bad-t" : "";
  logEl.prepend(li);
  while (logEl.children.length > 15) logEl.lastChild.remove();
}
const resetSoon = () => setTimeout(() => { if (!busy) setStatus("Ready. Tap a card.", "info"); }, 4000);

async function handleCard(uid) {
  if (!modelsReady || busy) return;
  busy = true;
  try {
    setStatus("Card " + uid + " read...", "info");
    const s = await api("/api/student/" + uid);
    if (!s.ok) { setStatus("Card not registered", "bad"); addLog("Unknown card " + uid, "bad"); return; }
    const st = s.data;
    if (st.already_marked) { setStatus(st.name + " completed all three check-ins today.", "info"); addLog(st.name + " completed all check-ins", ""); return; }
    if (!st.can_scan) {
      setStatus(st.scan_error || "No check-in is available right now.", "bad");
      addLog(st.name + " could not check in: " + (st.scan_error || "no open check-in"), "bad");
      return;
    }

    setStatus("Hi " + st.name + ". Look at the camera" + ($("liveness").checked ? ", keep your eyes open briefly, then blink once." : "."), "info");
    idle.style.display = "none";
    await startCamera(video);

    const result = await verifyFace(st.descriptors, $("liveness").checked);
    stopCamera(video);
    idle.style.display = "flex";

    if (result.ok) {
      const saved = await postJSON("/api/attendance", { student_id: st.id, status: "PRESENT", distance: result.distance });
      if (!saved.ok) {
        const message = saved.data.error || "Could not save attendance.";
        setStatus(message, "bad");
        addLog(st.name + ": " + message, "bad");
        return;
      }
      setStatus("Welcome, " + st.name + "! " + saved.data.slot_label + " check-in marked.", "ok");
      addLog(st.name + " marked PRESENT - " + saved.data.slot_label, "ok");
    } else {
      const saved = await postJSON("/api/attendance", { student_id: st.id, status: "FLAGGED", distance: result.distance, note: result.reason });
      if (!saved.ok) throw new Error(saved.data.error || "Could not save the failed scan.");
      setStatus("Not verified: " + result.reason, "bad");
      addLog(st.name + " FLAGGED (" + result.reason + ")", "bad");
    }
  } catch (e) {
    stopCamera(video); idle.style.display = "flex";
    setStatus("Error: " + e.message, "bad");
  } finally {
    busy = false; resetSoon();
  }
}

async function verifyFace(stored, needBlink) {
  const t0 = Date.now();
  let best = Infinity, seenFace = false, maxEyeOpen = 0, wasOpen = false, blinked = !needBlink;

  while (Date.now() - t0 < SCAN_TIMEOUT_MS) {
    const det = await detectFace(video);
    if (det) {
      seenFace = true;
      const d = Math.min(...stored.map(s => faceapi.euclideanDistance(det.descriptor, s)));
      best = Math.min(best, d);

      const ear = (eyeEAR(det.landmarks.getLeftEye()) + eyeEAR(det.landmarks.getRightEye())) / 2;
      if (needBlink) {
        maxEyeOpen = Math.max(maxEyeOpen, ear);
        if (ear >= maxEyeOpen * 0.85) wasOpen = true;
        if (wasOpen && ear < maxEyeOpen * BLINK_CLOSED_RATIO) blinked = true;
      }

      if (best < MATCH_THRESHOLD && blinked) return { ok: true, distance: best };
    }
  }
  if (!seenFace) return { ok: false, distance: null, reason: "no face detected" };
  if (best >= MATCH_THRESHOLD) return { ok: false, distance: best, reason: "face mismatch" };
  return { ok: false, distance: best, reason: "liveness (blink) not detected" };
}

$("btnReader").onclick = () => connectReader(handleCard, s => $("readerState").textContent = s);
autoConnectReader(handleCard, s => $("readerState").textContent = s);

loadModels().then(() => { modelsReady = true; setStatus("Ready. Connect the reader and tap a card.", "info"); })
  .catch(() => setStatus("Could not load face models (check internet).", "bad"));
