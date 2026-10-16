const reportBody = document.querySelector("#reportTable tbody");

async function loadReport() {
  const from = document.getElementById("from").value;
  const to = document.getElementById("to").value;
  const query = new URLSearchParams({ from, to }).toString();
  document.getElementById("btnCsv").href = "/api/export.csv?" + query;

  const result = await api("/api/report?" + query);
  if (!result.ok) {
    reportBody.textContent = "";
    return;
  }
  reportBody.textContent = "";
  if (result.data.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.textContent = "No attendance records found for the selected dates.";
    tr.appendChild(td);
    reportBody.appendChild(tr);
    return;
  }

  const days = new Map();
  result.data.forEach(row => {
    if (!days.has(row.report_date)) days.set(row.report_date, new Map());
    const students = days.get(row.report_date);
    if (!students.has(row.student_id)) {
      students.set(row.student_id, {
        name: row.name,
        rollNo: row.roll_no,
        slots: {},
      });
    }
    students.get(row.student_id).slots[row.slot] = row;
  });

  [...days.keys()].sort().reverse().forEach(day => {
    const students = [...days.get(day).values()].sort((a, b) => a.name.localeCompare(b.name));
    const [year, month, date] = day.split("-").map(Number);
    const label = new Date(year, month - 1, date).toLocaleDateString(undefined, {
      weekday: "long", year: "numeric", month: "long", day: "numeric",
    });
    const group = document.createElement("tr");
    group.className = "report-day";
    const heading = document.createElement("th");
    heading.colSpan = 5;
    heading.scope = "rowgroup";
    heading.textContent = label;
    group.appendChild(heading);
    reportBody.appendChild(group);

    students.forEach(student => {
      const tr = document.createElement("tr");
      for (const value of [student.name, student.rollNo]) {
        const td = document.createElement("td");
        td.textContent = value;
        tr.appendChild(td);
      }

      const legacy = student.slots.legacy;
      if (legacy) {
        const td = document.createElement("td");
        td.colSpan = 3;
        td.textContent = `Legacy daily attendance: ${legacy.status}`;
        td.className = legacy.status === "PRESENT" ? "ok-t" : "absent-t";
        tr.appendChild(td);
      } else {
        ["morning", "afternoon", "flexible"].forEach(slot => {
          const td = document.createElement("td");
          const row = student.slots[slot];
          const status = row ? row.status : "—";
          td.textContent = status;
          td.className = status === "PRESENT" ? "ok-t" : status === "ABSENT" ? "absent-t" : status === "PENDING" ? "pending-t" : "";
          tr.appendChild(td);
        });
      }
      reportBody.appendChild(tr);
    });
  });
}

document.getElementById("btnFilter").addEventListener("click", loadReport);
loadReport();
