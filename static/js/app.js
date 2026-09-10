/* ── RScan Web — Frontend Logic ─────────────────────────────────────── */
(function () {
  "use strict";

  // DOM refs
  const uploadZone = document.getElementById("uploadZone");
  const fileInput = document.getElementById("fileInput");
  const btnImages = document.getElementById("btnImages");
  const btnPdf = document.getElementById("btnPdf");
  const uploadSection = document.getElementById("uploadSection");
  const processingSection = document.getElementById("processingSection");
  const processingStatus = document.getElementById("processingStatus");
  const resultsSection = document.getElementById("resultsSection");
  const resultsGrid = document.getElementById("resultsGrid");
  const btnDownloadAll = document.getElementById("btnDownloadAll");
  const btnScanMore = document.getElementById("btnScanMore");

  let scannedPages = []; // { id, name, width, height }
  let scannedPdfName = null;
  let isPdfMode = false;

  // ── Drag & Drop ──────────────────────────────────────────────────
  uploadZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadZone.classList.add("dragover");
  });
  uploadZone.addEventListener("dragleave", () => {
    uploadZone.classList.remove("dragover");
  });
  uploadZone.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadZone.classList.remove("dragover");
    handleFiles(e.dataTransfer.files);
  });
  uploadZone.addEventListener("click", (e) => {
    if (e.target === btnImages || e.target === btnPdf || e.target.closest(".btn")) return;
    fileInput.click();
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) handleFiles(fileInput.files);
  });

  // ── Buttons ──────────────────────────────────────────────────────
  btnImages.addEventListener("click", (e) => {
    e.stopPropagation();
    isPdfMode = false;
    fileInput.accept = ".jpg,.jpeg,.png,.bmp,.tif,.tiff,.webp";
    fileInput.multiple = true;
    fileInput.click();
  });
  btnPdf.addEventListener("click", (e) => {
    e.stopPropagation();
    isPdfMode = true;
    fileInput.accept = ".pdf";
    fileInput.multiple = false;
    fileInput.click();
  });

  btnScanMore.addEventListener("click", () => {
    resultsSection.classList.add("hidden");
    uploadSection.classList.remove("hidden");
    resultsGrid.innerHTML = "";
    scannedPages = [];
    scannedPdfName = null;
  });

  btnDownloadAll.addEventListener("click", downloadAll);

  // ── Handle Files ─────────────────────────────────────────────────
  async function handleFiles(files) {
    if (!files || !files.length) return;

    uploadSection.classList.add("hidden");
    processingSection.classList.remove("hidden");
    resultsSection.classList.add("hidden");
    resultsGrid.innerHTML = "";

    // PDF mode
    if (isPdfMode) {
      const file = files[0];
      processingStatus.textContent = `Scanning PDF: ${file.name} ...`;
      const formData = new FormData();
      formData.append("file", file);
      try {
        const res = await fetch("/api/scan-pdf", { method: "POST", body: formData });
        const data = await res.json();
        if (data.error) {
          alert("Error: " + data.error);
          showUpload();
          return;
        }
        scannedPdfName = data.pdf;
        showPdfResult(file.name);
      } catch (err) {
        alert("Scan failed: " + err.message);
        showUpload();
      }
      return;
    }

    // Image mode
    const fileList = Array.from(files);
    const formData = new FormData();
    fileList.forEach((f) => formData.append("files", f));

    processingStatus.textContent = `Scanning ${fileList.length} image(s)...`;

    try {
      const res = await fetch("/api/scan", { method: "POST", body: formData });
      const data = await res.json();
      if (data.error) {
        alert("Error: " + data.error);
        showUpload();
        return;
      }
      scannedPages = data.pages || [];
      if (scannedPages.length === 0) {
        alert("No pages were scanned successfully.");
        showUpload();
        return;
      }
      showImageResults();
    } catch (err) {
      alert("Scan failed: " + err.message);
      showUpload();
    }
  }

  // ── Show Results ─────────────────────────────────────────────────
  function showUpload() {
    processingSection.classList.add("hidden");
    uploadSection.classList.remove("hidden");
  }

  function showImageResults() {
    processingSection.classList.add("hidden");
    resultsSection.classList.remove("hidden");

    scannedPages.forEach((page) => {
      if (page.error) {
        const card = document.createElement("div");
        card.className = "result-card";
        card.innerHTML = `
          <div class="result-card-body">
            <div class="result-card-name">${esc(page.name)}</div>
            <div class="result-card-meta" style="color:#e53935">Error: ${esc(page.error)}</div>
          </div>`;
        resultsGrid.appendChild(card);
        return;
      }

      const card = document.createElement("div");
      card.className = "result-card";
      card.innerHTML = `
        <img class="result-card-img" src="/api/image/${page.id}" alt="${esc(page.name)}" loading="lazy">
        <div class="result-card-body">
          <div class="result-card-name">${esc(page.name)}</div>
          <div class="result-card-meta">${page.width} &times; ${page.height}px</div>
          <div class="result-card-actions">
            <a class="btn btn-primary btn-sm" href="/api/image/${page.id}" download="scanned_${esc(page.name)}">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              Download
            </a>
          </div>
        </div>`;
      resultsGrid.appendChild(card);
    });
  }

  function showPdfResult(originalName) {
    processingSection.classList.add("hidden");
    resultsSection.classList.remove("hidden");

    const card = document.createElement("div");
    card.className = "result-card";
    card.innerHTML = `
      <div class="result-card-pdf">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        <span style="font-weight:600;color:#333">Scanned PDF</span>
      </div>
      <div class="result-card-body">
        <div class="result-card-name">${esc(originalName)}</div>
        <div class="result-card-meta">PDF — All pages scanned</div>
        <div class="result-card-actions">
          <a class="btn btn-primary btn-sm" href="/api/pdf/${scannedPdfName}" download="scanned_${esc(originalName)}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Download PDF
          </a>
        </div>
      </div>`;
    resultsGrid.appendChild(card);
  }

  function downloadAll() {
    // For images: trigger individual downloads
    if (scannedPages.length) {
      scannedPages.forEach((page) => {
        if (page.id) {
          const a = document.createElement("a");
          a.href = `/api/image/${page.id}`;
          a.download = `scanned_${page.name}`;
          a.click();
        }
      });
    }
    // For PDF
    if (scannedPdfName) {
      const a = document.createElement("a");
      a.href = `/api/pdf/${scannedPdfName}`;
      a.download = `scanned_${scannedPdfName}`;
      a.click();
    }
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }
})();
