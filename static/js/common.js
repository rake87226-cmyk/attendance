// Shared helpers: face-api models, webcam, Web Serial RFID reader.
const MODEL_URL = "https://cdn.jsdelivr.net/npm/@vladmandic/face-api@1.7.12/model/";
// For offline use: download the models into static/models and use "/static/models/" instead.

async function loadModels() {
  await Promise.all([
    faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
    faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
    faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL),
  ]);
}

async function startCamera(video) {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { width: 640, height: 480, facingMode: "user" }, audio: false,
  });
  video.srcObject = stream;
  video.classList.add("on");
  await video.play();
}

function stopCamera(video) {
  if (video.srcObject) video.srcObject.getTracks().forEach(t => t.stop());
  video.srcObject = null;
  video.classList.remove("on");
}

const detectorOptions = () => new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 });

async function detectFace(video) {
  return faceapi.detectSingleFace(video, detectorOptions()).withFaceLandmarks().withFaceDescriptor();
}

function dist(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }
function eyeEAR(eye) {  // eye aspect ratio; drops sharply when the eye closes
  return (dist(eye[1], eye[5]) + dist(eye[2], eye[4])) / (2 * dist(eye[0], eye[3]));
}

// ---- Web Serial RFID reader (Chrome / Edge only) ----
async function readPort(port, onUid, onState) {
  await port.open({ baudRate: 9600 });
  onState("Reader connected");
  const decoder = new TextDecoderStream();
  port.readable.pipeTo(decoder.writable).catch(() => {});
  const reader = decoder.readable.getReader();
  let buf = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += value;
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).trim();
        buf = buf.slice(i + 1);
        if (/^[0-9A-F]{8,20}$/.test(line)) onUid(line);
      }
    }
  } catch (e) { /* unplugged */ }
  onState("Reader disconnected");
}

async function connectReader(onUid, onState) {
  if (!("serial" in navigator)) { alert("Web Serial needs Chrome or Edge."); return; }
  const port = await navigator.serial.requestPort();
  readPort(port, onUid, onState).catch(e => onState("Could not open port: " + e.message));
}

async function autoConnectReader(onUid, onState) {  // reuse an already-permitted port
  if (!("serial" in navigator)) return;
  const ports = await navigator.serial.getPorts();
  if (ports.length) readPort(ports[0], onUid, onState).catch(() => onState("Not connected"));
}

async function api(url, opts) {
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({}));
  if (r.status === 401) window.location.assign("/admin/login");
  return { ok: r.ok, status: r.status, data: j };
}
const postJSON = (url, body) => api(url, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});
