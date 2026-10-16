# Smart Attendance System (RFID + Face Recognition)

Arduino Uno + RC522 reads the card UID over USB. The website (Flask) receives it
through Chrome's Web Serial API, opens the laptop webcam, and matches the face
with face-api.js. Attendance is saved in SQLite.

## 1. Arduino
Wiring (RC522 -> Uno): SDA-10, SCK-13, MOSI-11, MISO-12, RST-9, GND-GND, 3.3V-3.3V (NOT 5V).
Install the **MFRC522** library, open `arduino/rfid_reader/rfid_reader.ino`, upload.
Check Serial Monitor (9600): tapping a card prints its UID. Close Serial Monitor afterwards
(it blocks the browser from using the port).

## 2. Backend
```
python -m venv venv
venv\Scripts\activate        (Windows)   |   source venv/bin/activate   (Mac/Linux)
pip install -r requirements.txt
python app.py
```
Open http://localhost:5000 in **Chrome or Edge** (localhost allows camera + serial).
Set `ADMIN_PASSWORD` before starting the server to enable admin access. If it is
unset, admin access is disabled. For deployments that need sessions to survive a
restart, also set a stable, random `SECRET_KEY` environment variable.

## 3. Use
1. **Attendance**: Connect reader (one-time permission) -> tap a card -> camera opens -> blink -> marked. Each student has three separate check-ins per day: 9:00-9:15 AM, 1:15-1:30 PM, and one flexible check-in from 2:00-5:00 PM. Scans outside the two fixed windows cannot fill the flexible slot before 2:00 PM. The first two windows close at 9:15 AM and 1:30 PM; the flexible check-in opens at 2:00 PM and closes at 5:00 PM.
2. **Admin**: Sign in with `ADMIN_PASSWORD` to enroll students, delete enrollments, filter reports, and export all attendance records.

## Notes
- Internet is needed on first load: face-api.js and its models come from jsDelivr.
  For offline use, download the `model` folder of `@vladmandic/face-api` into `static/models`,
  and set `MODEL_URL = "/static/models/"` in `static/js/common.js`.
- Tune `MATCH_THRESHOLD` in `static/js/attendance.js` (0.45 stricter, 0.55 looser).
- Keep the attendance page open and focused; use good, front-facing light.
- The database file `attendance.db` is created on first run. Delete it to reset everything.
- Face data (descriptors) is personal data. Get consent and protect the laptop.
