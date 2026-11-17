"use strict";

// ---- tab switching -------------------------------------------------------

function switchTab(which) {
  const tabs   = document.querySelectorAll(".tab");
  const panels = document.querySelectorAll(".tab-panel");

  tabs.forEach(t => {
    const active = t.id === `tab-${which}`;
    t.classList.toggle("active", active);
    t.setAttribute("aria-selected", String(active));
  });
  panels.forEach(p => {
    p.classList.toggle("hidden", p.id !== `panel-${which}`);
  });

  // Reset status when switching tabs
  hideStatus();
}

// ---- status display ------------------------------------------------------

const statusArea     = document.getElementById("status-area");
const statusIndicator = document.getElementById("status-indicator");
const statusText     = document.getElementById("status-text");
const downloadLink   = document.getElementById("download-link");

function showStatus(text, state = "working") {
  statusArea.hidden = false;
  statusIndicator.className = `status-indicator ${state}`;
  statusText.textContent    = text;
  statusText.className      = state === "error" ? "status-text error" : "status-text";
  downloadLink.hidden       = true;
}

function showDownload(jobId, text) {
  statusArea.hidden         = false;
  statusIndicator.className = "status-indicator done";
  statusText.textContent    = text;
  statusText.className      = "status-text";
  downloadLink.href         = `/api/jobs/${jobId}/download`;
  downloadLink.hidden       = false;
}

function hideStatus() {
  statusArea.hidden   = true;
  downloadLink.hidden = true;
}

// ---- polling -------------------------------------------------------------

const MAX_POLLS = 90; // 90 × 1.2 s = ~108 s max wait

async function poll(jobId, attempt = 0) {
  if (attempt >= MAX_POLLS) {
    showStatus(
      "Timed out waiting for a response. The server may still be processing — " +
      "refresh the page and try again.",
      "error"
    );
    setSubmitting(false);
    return;
  }
  try {
    const r = await fetch(`/api/jobs/${jobId}`);
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || "Request failed.");

    if (j.status === "done") {
      showDownload(jobId, j.message || "Your PDF is ready.");
      setSubmitting(false);
    } else if (j.status === "error") {
      showStatus(j.error || "Something went wrong.", "error");
      setSubmitting(false);
    } else {
      showStatus(j.message || "Working…", "working");
      setTimeout(() => poll(jobId, attempt + 1), 1200);
    }
  } catch (e) {
    showStatus(e.message, "error");
    setSubmitting(false);
  }
}

// ---- shared submit state -------------------------------------------------

let _activeBtn = null;

function setSubmitting(on) {
  if (_activeBtn) _activeBtn.disabled = on;
}

// ---- URL form ------------------------------------------------------------

const formUrl = document.getElementById("form-url");
const btnUrl  = document.getElementById("btn-url");
const urlInput = document.getElementById("url-input");

formUrl.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) {
    showStatus("Please paste a ChatGPT share link first.", "error");
    return;
  }
  _activeBtn = btnUrl;
  setSubmitting(true);
  showStatus("Starting…", "working");

  try {
    const r = await fetch("/api/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || "Request failed.");
    poll(j.job_id);
  } catch (err) {
    showStatus(err.message, "error");
    setSubmitting(false);
  }
});

// ---- file form -----------------------------------------------------------

const formFile  = document.getElementById("form-file");
const btnFile   = document.getElementById("btn-file");
const fileInput = document.getElementById("file-input");
const dropArea  = document.getElementById("drop-area");
const dropLabel = document.getElementById("drop-label");

fileInput.addEventListener("change", () => {
  const f = fileInput.files[0];
  if (f) {
    dropLabel.textContent = f.name;
    btnFile.disabled = false;
  } else {
    dropLabel.innerHTML =
      '<span>Drop file here or <span class="file-browse">browse</span></span>';
    btnFile.disabled = true;
  }
});

// Drag-and-drop styling
["dragenter", "dragover"].forEach(ev =>
  dropArea.addEventListener(ev, e => {
    e.preventDefault();
    dropArea.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach(ev =>
  dropArea.addEventListener(ev, e => {
    e.preventDefault();
    dropArea.classList.remove("dragover");
  })
);
dropArea.addEventListener("drop", e => {
  const f = e.dataTransfer.files[0];
  if (f && f.name.toLowerCase().endsWith(".html")) {
    // Transfer to the file input via DataTransfer
    const dt = new DataTransfer();
    dt.items.add(f);
    fileInput.files = dt.files;
    fileInput.dispatchEvent(new Event("change"));
  } else {
    showStatus("Please drop an HTML file (.html).", "error");
  }
});

formFile.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = fileInput.files[0];
  if (!f) {
    showStatus("Please select an HTML file first.", "error");
    return;
  }
  _activeBtn = btnFile;
  setSubmitting(true);
  showStatus("Uploading file…", "working");

  const fd = new FormData();
  fd.append("file", f);

  try {
    const r = await fetch("/api/convert-file", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || "Request failed.");
    poll(j.job_id);
  } catch (err) {
    showStatus(err.message, "error");
    setSubmitting(false);
  }
});
