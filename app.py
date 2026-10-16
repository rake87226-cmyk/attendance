"""Smart Attendance System - Flask backend (SQLite)."""
import csv
import hmac
import io
import json
import os
import secrets
import sqlite3
from datetime import date, datetime, time, timedelta

from functools import wraps

from flask import Flask, Response, g, jsonify, redirect, render_template, request, session, url_for

DB_PATH = "attendance.db"
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD")

ATTENDANCE_SLOTS = (
    ("morning", "9:00 - 9:15 AM", time(9, 0), time(9, 15)),
    ("afternoon", "1:15 - 1:30 PM", time(13, 15), time(13, 30)),
    ("flexible", "Flexible (2:00 - 5:00 PM)", time(14, 0), time(17, 0)),
)


# ---------- database helpers ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_no TEXT NOT NULL UNIQUE,
            card_uid TEXT NOT NULL UNIQUE,
            face_descriptors TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,          -- PRESENT or FLAGGED
            distance REAL,
            note TEXT,
            FOREIGN KEY (student_id) REFERENCES students(id)
        );
        """
    )
    attendance_columns = {
        row[1] for row in db.execute("PRAGMA table_info(attendance)")
    }
    if "slot" not in attendance_columns:
        db.execute("ALTER TABLE attendance ADD COLUMN slot TEXT")
        today = date.today().isoformat()
        for key, _label, start, end in ATTENDANCE_SLOTS[:2]:
            db.execute(
                "UPDATE attendance SET slot = ? WHERE status = 'PRESENT' "
                "AND slot IS NULL AND date(timestamp) = ? "
                "AND time(timestamp) >= ? AND time(timestamp) < ?",
                (key, today, start.strftime("%H:%M:%S"), end.strftime("%H:%M:%S")),
            )
        db.execute(
            "UPDATE attendance SET slot = 'flexible' WHERE status = 'PRESENT' "
            "AND slot IS NULL AND date(timestamp) = ? AND time(timestamp) < '17:00:00'",
            (today,),
        )
    db.execute(
        "CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    db.execute(
        "INSERT OR IGNORE INTO app_settings (key, value) "
        "VALUES ('attendance_slots_start_date', date('now', 'localtime'))"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS attendance_one_present_per_slot "
        "ON attendance (student_id, date(timestamp), slot) "
        "WHERE status = 'PRESENT' AND slot IS NOT NULL"
    )
    db.commit()
    db.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def choose_attendance_slot(scan_time, completed_slots):
    if scan_time >= time(17, 0):
        return None, "Today's check-in window has closed at 5:00 PM."

    for key, label, start, end in ATTENDANCE_SLOTS[:2]:
        if start <= scan_time < end and key not in completed_slots:
            return (key, label), None

    flexible_start = ATTENDANCE_SLOTS[2][2]
    if scan_time < flexible_start:
        return None, "The flexible check-in is available from 2:00 PM to 5:00 PM."

    if "flexible" not in completed_slots:
        return ATTENDANCE_SLOTS[2][:2], None
    return None, "The flexible check-in is already recorded; fixed check-ins must be made during their 15-minute windows."


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return jsonify(error="Admin login required"), 401
        return view(*args, **kwargs)
    return wrapped


# ---------- pages ----------
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/enroll")
def enroll_page():
    return redirect(url_for("admin_enroll_page"))


@app.get("/attendance")
def attendance_page():
    return render_template("attendance.html")


@app.get("/report")
def report_page():
    return redirect(url_for("admin_reports_page"))


@app.get("/admin/login")
def admin_login_page():
    if session.get("is_admin"):
        return redirect(url_for("admin_page"))
    return render_template("admin_login.html", configured=bool(app.config["ADMIN_PASSWORD"]))


@app.post("/admin/login")
def admin_login():
    expected = app.config["ADMIN_PASSWORD"]
    supplied = request.form.get("password", "")
    if expected and hmac.compare_digest(supplied, expected):
        session.clear()
        session["is_admin"] = True
        return redirect(url_for("admin_page"))
    return render_template("admin_login.html", configured=bool(expected), error="Incorrect admin password."), 401


@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.get("/admin")
def admin_page():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login_page"))
    return render_template("admin.html")


@app.get("/admin/enroll")
def admin_enroll_page():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login_page"))
    return render_template("admin_enroll.html")


@app.get("/admin/reports")
def admin_reports_page():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login_page"))
    return render_template("admin_reports.html")


# ---------- API ----------
@app.get("/api/student/<uid>")
def api_student(uid):
    db = get_db()
    row = db.execute("SELECT * FROM students WHERE card_uid = ?", (uid.upper(),)).fetchone()
    if not row:
        return jsonify(error="Card not registered"), 404
    completed_slots = {
        result["slot"]
        for result in db.execute(
            "SELECT slot FROM attendance WHERE student_id = ? AND status = 'PRESENT' "
            "AND date(timestamp) = ? AND slot IS NOT NULL",
            (row["id"], date.today().isoformat()),
        ).fetchall()
    }
    _, availability_error = choose_attendance_slot(datetime.now().time(), completed_slots)
    return jsonify(
        id=row["id"],
        name=row["name"],
        roll_no=row["roll_no"],
        descriptors=json.loads(row["face_descriptors"]),
        completed_slots=sorted(completed_slots),
        already_marked=len(completed_slots) == len(ATTENDANCE_SLOTS),
        can_scan=availability_error is None,
        scan_error=availability_error,
    )


@app.get("/api/students")
@admin_required
def api_students():
    rows = get_db().execute(
        "SELECT id, name, roll_no, card_uid, created_at FROM students ORDER BY id DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/enroll")
@admin_required
def api_enroll():
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip()
    roll = (d.get("roll_no") or "").strip()
    uid = (d.get("card_uid") or "").strip().upper()
    descriptors = d.get("descriptors") or []
    if not (name and roll and uid and descriptors):
        return jsonify(error="Name, roll no, card and face are all required"), 400
    try:
        db = get_db()
        db.execute(
            "INSERT INTO students (name, roll_no, card_uid, face_descriptors, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, roll, uid, json.dumps(descriptors), now()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="Roll number or card is already registered"), 409
    return jsonify(ok=True)


@app.delete("/api/students/<int:sid>")
@admin_required
def api_delete_student(sid):
    db = get_db()
    db.execute("DELETE FROM attendance WHERE student_id = ?", (sid,))
    db.execute("DELETE FROM students WHERE id = ?", (sid,))
    db.commit()
    return jsonify(ok=True)


@app.post("/api/attendance")
def api_attendance():
    d = request.get_json(force=True)
    sid = d.get("student_id")
    status = "PRESENT" if d.get("status") == "PRESENT" else "FLAGGED"
    db = get_db()
    if status == "PRESENT":
        scan_datetime = datetime.now()
        db.execute("BEGIN IMMEDIATE")
        student = db.execute("SELECT id FROM students WHERE id = ?", (sid,)).fetchone()
        if not student:
            db.rollback()
            return jsonify(error="Student not found"), 404
        completed_slots = {
            result["slot"]
            for result in db.execute(
                "SELECT slot FROM attendance WHERE student_id = ? AND status = 'PRESENT' "
                "AND date(timestamp) = ? AND slot IS NOT NULL",
                (sid, scan_datetime.date().isoformat()),
            ).fetchall()
        }
        selected_slot, error = choose_attendance_slot(scan_datetime.time(), completed_slots)
        if error:
            db.rollback()
            return jsonify(error=error), 409
        slot, slot_label = selected_slot
        try:
            db.execute(
                "INSERT INTO attendance (student_id, timestamp, status, distance, note, slot) "
                "VALUES (?, ?, 'PRESENT', ?, ?, ?)",
                (sid, scan_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                 d.get("distance"), d.get("note"), slot),
            )
        except sqlite3.IntegrityError:
            db.rollback()
            return jsonify(error="This check-in was already recorded. Please try again."), 409
        db.commit()
        return jsonify(ok=True, slot=slot, slot_label=slot_label)

    db.execute(
        "INSERT INTO attendance (student_id, timestamp, status, distance, note) "
        "VALUES (?, ?, ?, ?, ?)",
        (sid, now(), status, d.get("distance"), d.get("note")),
    )
    db.commit()
    return jsonify(ok=True)


def query_report(start, end):
    db = get_db()
    settings = db.execute(
        "SELECT value FROM app_settings WHERE key = 'attendance_slots_start_date'"
    ).fetchone()
    slots_start = date.fromisoformat(settings["value"])
    today = date.today()
    current_time = datetime.now().time()
    first_day = date.fromisoformat(start) if start else None
    last_day = date.fromisoformat(end) if end else today
    if last_day > today:
        last_day = today

    students = db.execute(
        "SELECT id, name, roll_no, card_uid, created_at FROM students"
    ).fetchall()
    present_rows = db.execute(
        "SELECT a.id, a.student_id, s.name, s.roll_no, s.card_uid, a.timestamp, "
        "date(a.timestamp) AS report_date, a.status, a.distance, a.slot "
        "FROM attendance a JOIN students s ON s.id = a.student_id "
        "WHERE a.status = 'PRESENT' AND date(a.timestamp) <= ? "
        "AND (? IS NULL OR date(a.timestamp) >= ?) "
        "ORDER BY a.timestamp, a.id",
        (last_day.isoformat(), first_day.isoformat() if first_day else None,
         first_day.isoformat() if first_day else None),
    ).fetchall()
    legacy_present = {}
    scheduled_present = {}
    for row in present_rows:
        key = (row["student_id"], row["report_date"])
        if date.fromisoformat(row["report_date"]) < slots_start:
            legacy_present.setdefault(key, row)
        elif row["slot"]:
            scheduled_present[(row["student_id"], row["report_date"], row["slot"])] = row

    rows = []
    for student in students:
        enrolled = date.fromisoformat(student["created_at"][:10])
        day = max(enrolled, first_day) if first_day else enrolled
        while day <= last_day:
            day_text = day.isoformat()
            if day < slots_start:
                existing = legacy_present.get((student["id"], day_text))
                rows.append({
                    "id": existing["id"] if existing else None,
                    "student_id": student["id"],
                    "name": student["name"],
                    "roll_no": student["roll_no"],
                    "card_uid": student["card_uid"],
                    "timestamp": existing["timestamp"] if existing else "",
                    "report_date": day_text,
                    "slot": "legacy",
                    "slot_label": "Daily (before check-in schedule)",
                    "status": "PRESENT" if existing else "ABSENT",
                    "distance": existing["distance"] if existing else None,
                })
            else:
                for key, label, _start, deadline in ATTENDANCE_SLOTS:
                    existing = scheduled_present.get((student["id"], day_text, key))
                    due = day < today or current_time >= deadline
                    rows.append({
                        "id": existing["id"] if existing else None,
                        "student_id": student["id"],
                        "name": student["name"],
                        "roll_no": student["roll_no"],
                        "card_uid": student["card_uid"],
                        "timestamp": existing["timestamp"] if existing else "",
                        "report_date": day_text,
                        "slot": key,
                        "slot_label": label,
                        "status": (
                            "PRESENT" if existing else "ABSENT" if due else "PENDING"
                        ),
                        "distance": existing["distance"] if existing else None,
                    })
            day += timedelta(days=1)

    slot_order = {key: index for index, (key, *_rest) in enumerate(ATTENDANCE_SLOTS)}
    rows.sort(
        key=lambda row: (
            -date.fromisoformat(row["report_date"]).toordinal(),
            row["name"].casefold(),
            slot_order.get(row["slot"], -1),
        )
    )
    return rows


@app.get("/api/report")
@admin_required
def api_report():
    rows = query_report(request.args.get("from"), request.args.get("to"))
    return jsonify([dict(r) for r in rows])


@app.get("/api/export.csv")
@admin_required
def api_export():
    rows = query_report(request.args.get("from"), request.args.get("to"))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([
        "Name", "Roll No", "Date", "Morning", "Afternoon", "Evening",
    ])
    grouped = {}
    for r in rows:
        key = (r["report_date"], r["student_id"])
        grouped.setdefault(key, {
            "name": r["name"],
            "roll_no": r["roll_no"],
            "slots": {},
        })["slots"][r["slot"]] = r["status"]
    for (report_date, _student_id), student in sorted(grouped.items(), reverse=True):
        slots = student["slots"]
        if "legacy" in slots:
            morning = f"Legacy daily: {slots['legacy']}"
            afternoon = ""
            flexible = ""
        else:
            morning = slots.get("morning", "")
            afternoon = slots.get("afternoon", "")
            flexible = slots.get("flexible", "")
        w.writerow([
            student["name"], student["roll_no"], report_date,
            morning, afternoon, flexible,
        ])
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=attendance.csv"},
    )


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
