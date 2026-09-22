/* ── RScan Web — Frontend Logic (with live SSE PDF scan progress) ──────── */
document.addEventListener("DOMContentLoaded", function () {
(function () {
  "use strict";

  // ── DOM refs ────────────────────────────────────────────────────────────
  const uploadZone        = document.getElementById("uploadZone");
  const fileInput         = document.getElementById("fileInput");
  const btnImages         = document.getElementById("btnImages");
  const btnPdf            = document.getElementById("btnPdf");
  const uploadSection     = document.getElementById("uploadSection");
  const processingSection = document.getElementById("processingSection");
  const resultsSection    = document.getElementById("resultsSection");
  const resultsGrid       = document.getElementById("resultsGrid");
  const btnDownloadAll    = document.getElementById("btnDownloadAll");
  const btnScanMore       = document.getElementById("btnScanMore");

  // Page-limit modal
  const pageLimitBackdrop = document.getElementById("pageLimitBackdrop");
  const pageLimitOptions  = document.getElementById("pageLimitOptions");
  const pageLimitCancel   = document.getElementById("pageLimitCancel");

  // Processing panel elements — resolved lazily so a browser-cached old HTML never crashes
  function $procTitle()       { return document.getElementById("procTitle"); }
  function $scanLine()        { return document.getElementById("scanLine"); }
  function $pageCounter()     { return document.getElementById("pageCounter"); }
  function $pageCurrent()     { return document.getElementById("pageCurrent"); }
  function $pageTotal()       { return document.getElementById("pageTotal"); }
  function $progressBarWrap() { return document.getElementById("progressBarWrap"); }
  function $progressBar()     { return document.getElementById("progressBar"); }
  function $progressPct()     { return document.getElementById("progressPct"); }
  function $stepLog()         { return document.getElementById("stepLog"); }

  // ── State ────────────────────────────────────────────────────────────────
  let scannedPages          = [];
  let scannedPdfName        = null;
  let localPdfUrl           = null;
  let lastSelectionSig      = "";
  let activeEventSource     = null;
  let _activeStepLi         = null;

  const MAX_LOCAL_PDF_BYTES = 50 * 1024 * 1024;
  const MAX_LOCAL_PDF_PAGES = 50;
  const DEFAULT_PAGE_LIMIT  = null;

  if (window.pdfjsLib) {
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = "/static/vendor/pdf.worker.js";
  }

  // ── Drag & Drop ──────────────────────────────────────────────────────────
  if (uploadZone) {
    uploadZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      uploadZone.classList.add("dragover");
    });
    uploadZone.addEventListener("dragleave", () => uploadZone.classList.remove("dragover"));
    uploadZone.addEventListener("drop", (e) => {
      e.preventDefault();
      uploadZone.classList.remove("dragover");
      handleFiles(e.dataTransfer.files);
    });
    uploadZone.addEventListener("click", (e) => {
      if (e.target.closest(".btn")) return;
      if (fileInput) fileInput.click();
    });
  }

  if (fileInput) {
    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) handleFiles(fileInput.files);
    });
  }

  // ── Buttons ──────────────────────────────────────────────────────────────
  if (btnImages) {
    btnImages.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!fileInput) return;
      fileInput.accept = ".jpg,.jpeg,.png,.bmp,.tif,.tiff,.webp";
      fileInput.multiple = true;
      fileInput.click();
    });
  }

  if (btnPdf) {
    btnPdf.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!fileInput) return;
      fileInput.accept = ".pdf";
      fileInput.multiple = false;
      fileInput.click();
    });
  }

  if (btnScanMore) {
    btnScanMore.addEventListener("click", () => {
      clearLocalPdf();
      closeEventSource();
      if (resultsSection)    resultsSection.classList.add("hidden");
      if (uploadSection)     uploadSection.classList.remove("hidden");
      if (resultsGrid)       resultsGrid.innerHTML = "";
      scannedPages = [];
      scannedPdfName = null;
      lastSelectionSig = "";
      resetProcessingUI();
    });
  }

  if (btnDownloadAll) btnDownloadAll.addEventListener("click", downloadAll);

  // ── Handle Files ──────────────────────────────────────────────────────────
  async function handleFiles(files) {
    if (!files || !files.length) return;

    const fileArray = Array.from(files);
    const sig = fileArray.map((f) => f.name + ":" + f.size + ":" + f.lastModified).sort().join("|");
    if (sig === lastSelectionSig) return;
    lastSelectionSig = sig;

    showProcessing();

    const firstFile = files[0];
    const isPdf = firstFile.type === "application/pdf" || /\.pdf$/i.test(firstFile.name);

    if (isPdf) {
      if (files.length !== 1) {
        alert("Please select one PDF at a time.");
        showUpload();
        return;
      }

      // Ask the user how many pages to scan
      let chosenLimit;
      try {
        chosenLimit = await askPageLimit();
      } catch (_) {
        // User cancelled the modal
        showUpload();
        return;
      }

      try {
        await scanPdfWithLiveProgress(firstFile, chosenLimit);
      } catch (err) {
        console.error("SSE PDF scan failed, trying local fallback:", err);
        try {
          await scanPdfLocally(firstFile, DEFAULT_PAGE_LIMIT);
        } catch (fallbackErr) {
          alert("Scan failed: " + fallbackErr.message);
          showUpload();
        }
      }
      return;
    }

    // ── Image mode ───────────────────────────────────────────────────────
    addStep("active", "Scanning " + fileArray.length + " image(s)…");
    updateProcTitle("Scanning images…");

    const formData = new FormData();
    fileArray.forEach((f) => formData.append("files", f));

    try {
      const res  = await fetch("/api/scan", { method: "POST", body: formData });
      const data = await res.json();
      if (data.error) { alert("Error: " + data.error); showUpload(); return; }
      scannedPages = data.pages || [];
      if (!scannedPages.length) { alert("No pages were scanned."); showUpload(); return; }
      markStepDone();
      showImageResults();
    } catch (err) {
      alert("Scan failed: " + err.message);
      showUpload();
    }
  }

  // ── SSE PDF scan (two-phase: upload → stream progress) ───────────────────
  async function scanPdfWithLiveProgress(file, pageLimit) {
    resetProcessingUI();
    updateProcTitle("Uploading your PDF…");
    setScanLine(true);

    // Phase 1 — upload and get job_id
    addStep("active", "Uploading \"" + file.name + "\" (" + formatBytes(file.size) + ")…");
    const body = new FormData();
    body.append("file", file, file.name);
    if (Number.isInteger(pageLimit) && pageLimit >= 1) {
      body.append("page_limit", String(pageLimit));
    }

    let jobId;
    try {
      const resp = await fetch("/api/scan-pdf-start", { method: "POST", body });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || data.error) throw new Error(data.error || "Upload failed (HTTP " + resp.status + ")");
      jobId = data.job_id;
    } catch (err) {
      setScanLine(false);
      throw err;
    }

    markStepDone("PDF uploaded successfully");
    updateProcTitle("Scanning your document…");

    // Phase 2 — connect to SSE progress stream
    return new Promise((resolve, reject) => {
      closeEventSource();
      const es = new EventSource("/api/scan-pdf-progress/" + jobId);
      activeEventSource = es;

      es.onmessage = (ev) => {
        let event;
        try { event = JSON.parse(ev.data); } catch { return; }

        switch (event.type) {

          case "loading":
            updateProcTitle("Loading PDF pages…");
            addStep("active", "Detecting pages in the PDF…");
            break;

          case "detected": {
            const total = event.total;
            markStepDone("Found " + total + " page" + (total !== 1 ? "s" : "") + " in the PDF");
            updateProcTitle("Scanning " + total + " page" + (total !== 1 ? "s" : "") + "…");
            showPageCounter(0, total);
            showProgressBar(0, total);
            break;
          }

          case "scanning": {
            const { page, total } = event;
            updateProcTitle("Scanning page " + page + " of " + total + "…");
            setPageCurrent(page);
            addStep("active", "Scanning page " + page + " of " + total + "…");
            updateProgressBar(page - 1, total);
            break;
          }

          case "page_done": {
            const { page, total } = event;
            markStepDone("Page " + page + " scanned");
            setPageCurrent(page);
            updateProgressBar(page, total);
            break;
          }

          case "assembling":
            updateProcTitle("Assembling scanned PDF…");
            addStep("active", "Assembling all pages into final PDF…");
            setScanLine(false);
            break;

          case "done": {
            const elapsed = event.elapsed;
            markStepDone("Done! " + elapsed + "s — PDF is ready");
            updateProcTitle("Scan complete!");
            updateProgressBar(1, 1);
            scannedPdfName = event.pdf;
            es.close();
            activeEventSource = null;
            setTimeout(() => {
              const pdfUrl = "/api/pdf/" + encodeURIComponent(event.pdf);
              showServerPdfResult(file.name, pdfUrl, elapsed);
              resolve();
            }, 600);
            break;
          }

          case "error":
            es.close();
            activeEventSource = null;
            setScanLine(false);
            reject(new Error(event.message || "Scan failed"));
            break;

          case "_eof":
            es.close();
            activeEventSource = null;
            break;
        }
      };

      es.onerror = () => {
        es.close();
        activeEventSource = null;
        setScanLine(false);
        reject(new Error("Connection to scan server was lost. Please try again."));
      };
    });
  }

  // ── Local PDF fallback (PDF.js + scan-worker) ─────────────────────────────
  async function scanPdfLocally(file, pageLimit) {
    if (!window.pdfjsLib || !window.PDFLib) {
      throw new Error("Local PDF engine is still loading. Please try again.");
    }
    if (file.size > MAX_LOCAL_PDF_BYTES) {
      throw new Error("This PDF is larger than the 50 MB local-processing limit.");
    }

    resetProcessingUI();
    updateProcTitle("Scanning locally…");
    setScanLine(true);

    addStep("active", "Loading PDF in browser…");
    const bytes = new Uint8Array(await file.arrayBuffer());
    let source;
    try {
      source = await window.pdfjsLib.getDocument({ data: bytes }).promise;
    } catch (err) {
      throw err;
    }
    markStepDone("Found " + source.numPages + " page(s)");

    if (source.numPages > MAX_LOCAL_PDF_PAGES) {
      throw new Error("This PDF has " + source.numPages + " pages. Local scanning supports up to " + MAX_LOCAL_PDF_PAGES + " pages.");
    }

    const pagesToScan = pageLimit != null ? Math.min(source.numPages, pageLimit) : source.numPages;
    showPageCounter(0, pagesToScan);
    showProgressBar(0, pagesToScan);
    updateProcTitle("Scanning " + pagesToScan + " pages…");

    const output = await window.PDFLib.PDFDocument.create();
    const worker = new Worker("/static/js/scan-worker.js");
    const pageImages = [];

    try {
      for (let pageNumber = 1; pageNumber <= pagesToScan; pageNumber++) {
        addStep("active", "Scanning page " + pageNumber + " of " + pagesToScan + "…");
        setPageCurrent(pageNumber);
        updateProgressBar(pageNumber - 1, pagesToScan);

        const page = await source.getPage(pageNumber);
        const pageSize = page.getViewport({ scale: 1 });
        const scale = Math.min(2.0, 1500 / pageSize.width);
        const viewport = page.getViewport({ scale });
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(viewport.width);
        canvas.height = Math.round(viewport.height);
        await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
        const processed = await enhanceCanvas(canvas, worker);
        const dataUrl = processed.toDataURL("image/jpeg", 0.94);
        const jpgBytes = dataUrlToBytes(dataUrl);
        const embedded = await output.embedJpg(jpgBytes);
        const pdfPage = output.addPage([pageSize.width, pageSize.height]);
        const fit = Math.min(pageSize.width / processed.width, pageSize.height / processed.height);
        pdfPage.drawImage(embedded, {
          x: (pageSize.width - processed.width * fit) / 2,
          y: (pageSize.height - processed.height * fit) / 2,
          width: processed.width * fit,
          height: processed.height * fit,
        });
        if (pageImages.length < 12) {
          pageImages.push({ dataUrl, width: processed.width, height: processed.height });
        }
        markStepDone("Page " + pageNumber + " scanned");
        updateProgressBar(pageNumber, pagesToScan);
      }
    } finally {
      worker.terminate();
      setScanLine(false);
    }

    addStep("active", "Building PDF…");
    updateProcTitle("Assembling PDF…");
    const resultBytes = await output.save();
    if (localPdfUrl) URL.revokeObjectURL(localPdfUrl);
    localPdfUrl = URL.createObjectURL(new Blob([resultBytes], { type: "application/pdf" }));
    markStepDone("Done! PDF ready");
    setTimeout(() => showLocalPdfResult(file.name, pageImages, localPdfUrl), 500);
  }

  function enhanceCanvas(canvas, worker) {
    return new Promise((resolve, reject) => {
      const context = canvas.getContext("2d", { willReadFrequently: true });
      const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
      worker.onmessage = ({ data }) => {
        if (!data || !data.pixels) { reject(new Error("Worker returned invalid data.")); return; }
        context.putImageData(new ImageData(new Uint8ClampedArray(data.pixels), data.width, data.height), 0, 0);
        resolve(canvas);
      };
      worker.onerror = () => reject(new Error("Scan worker stopped unexpectedly."));
      worker.postMessage({ width: canvas.width, height: canvas.height, pixels: imageData.data.buffer }, [imageData.data.buffer]);
    });
  }

  function dataUrlToBytes(dataUrl) {
    const binary = atob(dataUrl.split(",")[1]);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }

  // ── UI helpers — safe element wrappers ───────────────────────────────────

  function setScanLine(active) {
    const el = $scanLine();
    if (el) el.classList.toggle("active", active);
  }

  function setPageCurrent(num) {
    const el = $pageCurrent();
    if (el) el.textContent = num;
  }

  function updateProcTitle(text) {
    const el = $procTitle();
    if (el) el.textContent = text;
  }

  // ── Page-limit modal ──────────────────────────────────────────────────────
  function askPageLimit() {
    return new Promise((resolve, reject) => {
      if (!pageLimitBackdrop || !pageLimitOptions) {
        // No modal in DOM — just scan all pages
        resolve(null);
        return;
      }

      // Clear any previous selection highlight
      pageLimitOptions.querySelectorAll(".page-opt-btn").forEach(function (b) {
        b.classList.remove("selected");
      });

      // Show the modal
      pageLimitBackdrop.classList.remove("hidden");

      function cleanup() {
        pageLimitBackdrop.classList.add("hidden");
        pageLimitOptions.removeEventListener("click", onOption);
        if (pageLimitCancel) pageLimitCancel.removeEventListener("click", onCancel);
        pageLimitBackdrop.removeEventListener("click", onBackdrop);
      }

      function onOption(e) {
        const btn = e.target.closest(".page-opt-btn");
        if (!btn) return;
        // Highlight selection
        pageLimitOptions.querySelectorAll(".page-opt-btn").forEach(function (b) {
          b.classList.remove("selected");
        });
        btn.classList.add("selected");
        const raw = btn.dataset.limit;
        const limit = (raw === "all" || !raw) ? null : parseInt(raw, 10);
        // Brief pause so user sees the highlight, then close & resolve
        setTimeout(function () { cleanup(); resolve(limit); }, 220);
      }

      function onCancel() { cleanup(); reject(new Error("cancelled")); }
      function onBackdrop(e) { if (e.target === pageLimitBackdrop) onCancel(); }

      pageLimitOptions.addEventListener("click", onOption);
      if (pageLimitCancel) pageLimitCancel.addEventListener("click", onCancel);
      pageLimitBackdrop.addEventListener("click", onBackdrop);
    });
  }

  function showPageCounter(current, total) {
    const pc = $pageCurrent();  if (pc) pc.textContent = current;
    const pt = $pageTotal();    if (pt) pt.textContent = total;
    const counter = $pageCounter(); if (counter) counter.classList.remove("hidden");
  }

  function showProgressBar(done, total) {
    const wrap = $progressBarWrap(); if (wrap) wrap.classList.remove("hidden");
    updateProgressBar(done, total);
  }

  function updateProgressBar(done, total) {
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    const pb  = $progressBar();
    if (pb) {
      pb.style.width = pct + "%";
      if (pct > 0 && pct < 100) pb.classList.add("active");
      else pb.classList.remove("active");
    }
    const pp = $progressPct();
    if (pp) pp.textContent = pct + "%";
  }

  // ── Processing UI — step log ──────────────────────────────────────────────

  function resetProcessingUI() {
    _activeStepLi = null;
    const sl = $stepLog();
    if (sl) sl.innerHTML = "";
    const pc = $pageCounter();
    if (pc) pc.classList.add("hidden");
    const pbw = $progressBarWrap();
    if (pbw) pbw.classList.add("hidden");
    const pb = $progressBar();
    if (pb) { pb.style.width = "0%"; pb.classList.remove("active"); }
    const pp = $progressPct();
    if (pp) pp.textContent = "0%";
    setScanLine(false);
    updateProcTitle("Preparing…");
  }

  function addStep(state, text) {
    const log = $stepLog();
    if (!log) return null;

    // close previous active step
    if (_activeStepLi && _activeStepLi.classList.contains("step-active")) {
      _activeStepLi.classList.remove("step-active");
      _activeStepLi.classList.add("step-done");
      const icon = _activeStepLi.querySelector(".step-icon");
      if (icon) { icon.className = "step-icon done"; icon.textContent = "\u2713"; }
    }

    const li = document.createElement("li");
    li.className = state === "active" ? "step-active" : state === "done" ? "step-done" : "";

    const iconEl = document.createElement("span");
    iconEl.className = "step-icon " + (state === "active" ? "active" : state === "done" ? "done" : "pending");
    iconEl.textContent = state === "done" ? "\u2713" : state === "active" ? "\u2192" : "\u00b7";

    const textEl = document.createElement("span");
    textEl.textContent = text;

    li.appendChild(iconEl);
    li.appendChild(textEl);
    log.appendChild(li);
    li.scrollIntoView({ behavior: "smooth", block: "nearest" });

    if (state === "active") _activeStepLi = li;
    return li;
  }

  function markStepDone(newText) {
    if (!_activeStepLi) return;
    _activeStepLi.classList.remove("step-active");
    _activeStepLi.classList.add("step-done");
    const icon = _activeStepLi.querySelector(".step-icon");
    if (icon) { icon.className = "step-icon done"; icon.textContent = "\u2713"; }
    if (newText) {
      const span = _activeStepLi.querySelector("span:last-child");
      if (span) span.textContent = newText;
    }
    _activeStepLi = null;
  }

  // ── UI helpers — Show sections ────────────────────────────────────────────

  function showUpload() {
    if (processingSection) processingSection.classList.add("hidden");
    if (resultsSection)    resultsSection.classList.add("hidden");
    if (uploadSection)     uploadSection.classList.remove("hidden");
    resetProcessingUI();
  }

  function showProcessing() {
    if (uploadSection)     uploadSection.classList.add("hidden");
    if (resultsSection)    resultsSection.classList.add("hidden");
    if (processingSection) processingSection.classList.remove("hidden");
    resetProcessingUI();
  }

  function showImageResults() {
    if (processingSection) processingSection.classList.add("hidden");
    if (resultsSection)    resultsSection.classList.remove("hidden");
    if (!resultsGrid) return;

    scannedPages.forEach((page) => {
      if (page.error) {
        const card = document.createElement("div");
        card.className = "result-card";
        card.innerHTML =
          "<div class=\"result-card-body\">" +
          "<div class=\"result-card-name\">" + esc(page.name) + "</div>" +
          "<div class=\"result-card-meta\" style=\"color:#f87171\">Error: " + esc(page.error) + "</div>" +
          "</div>";
        resultsGrid.appendChild(card);
        return;
      }

      const card = document.createElement("div");
      card.className = "result-card";
      card.innerHTML =
        "<img class=\"result-card-img\" src=\"/api/image/" + page.id + "\" alt=\"" + esc(page.name) + "\" loading=\"lazy\">" +
        "<div class=\"result-card-body\">" +
        "<div class=\"result-card-name\">" + esc(page.name) + "</div>" +
        "<div class=\"result-card-meta\">" + page.width + " \u00d7 " + page.height + "px</div>" +
        "<div class=\"result-card-actions\">" +
        "<a class=\"btn btn-primary btn-sm\" href=\"/api/image/" + page.id + "\" download=\"" + safeFilename(page.name, "scanned_page") + "\">" +
        "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4\"/><polyline points=\"7 10 12 15 17 10\"/><line x1=\"12\" y1=\"15\" x2=\"12\" y2=\"3\"/></svg>" +
        "Download</a></div></div>";
      resultsGrid.appendChild(card);
    });
  }

  function showServerPdfResult(originalName, pdfUrl, elapsed) {
    if (processingSection) processingSection.classList.add("hidden");
    if (resultsSection)    resultsSection.classList.remove("hidden");
    if (!resultsGrid) return;

    const card = document.createElement("div");
    card.className = "result-card";
    card.innerHTML =
      "<div class=\"result-card-pdf\">" +
      "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.5\">" +
      "<path d=\"M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z\"/>" +
      "<polyline points=\"14 2 14 8 20 8\"/>" +
      "<line x1=\"9\" y1=\"13\" x2=\"15\" y2=\"13\"/><line x1=\"9\" y1=\"17\" x2=\"15\" y2=\"17\"/>" +
      "</svg><p>Scanned PDF</p></div>" +
      "<div class=\"result-card-body\">" +
      "<div class=\"result-card-name\">" + esc(originalName) + "</div>" +
      "<div class=\"result-card-meta\">Server scan complete" + (elapsed ? " \u00b7 " + elapsed + "s" : "") + "</div>" +
      "<div class=\"result-card-actions\">" +
      "<a class=\"btn btn-success btn-sm\" href=\"" + pdfUrl + "\" download=\"" + safeFilename(originalName, "scanned_document") + "\">" +
      "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4\"/><polyline points=\"7 10 12 15 17 10\"/><line x1=\"12\" y1=\"15\" x2=\"12\" y2=\"3\"/></svg>" +
      "Download PDF</a></div></div>";
    resultsGrid.appendChild(card);
  }

  function showLocalPdfResult(originalName, pageImages, pdfUrl) {
    if (processingSection) processingSection.classList.add("hidden");
    if (resultsSection)    resultsSection.classList.remove("hidden");
    if (!resultsGrid || !pageImages.length) return;

    const preview = pageImages[0];
    const card = document.createElement("div");
    card.className = "result-card";
    card.innerHTML =
      "<img class=\"result-card-img\" src=\"" + preview.dataUrl + "\" alt=\"Local scan preview\">" +
      "<div class=\"result-card-body\">" +
      "<div class=\"result-card-name\">" + esc(originalName) + "</div>" +
      "<div class=\"result-card-meta\">" + pageImages.length + " page(s) scanned locally</div>" +
      "<div class=\"result-card-actions\">" +
      "<a class=\"btn btn-success btn-sm\" href=\"" + pdfUrl + "\" download=\"" + safeFilename(originalName, "scanned_document") + "\">" +
      "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4\"/><polyline points=\"7 10 12 15 17 10\"/><line x1=\"12\" y1=\"15\" x2=\"12\" y2=\"3\"/></svg>" +
      "Download PDF</a></div></div>";
    resultsGrid.appendChild(card);
  }

  // ── Download all ──────────────────────────────────────────────────────────
  function downloadAll() {
    scannedPages.forEach((page) => {
      if (page.id) {
        const a = document.createElement("a");
        a.href = "/api/image/" + page.id;
        a.download = safeFilename(page.name, "scanned_page");
        a.click();
      }
    });
    if (scannedPdfName) {
      const a = document.createElement("a");
      a.href = "/api/pdf/" + scannedPdfName;
      a.download = scannedPdfName;
      a.click();
    }
    if (localPdfUrl) {
      const a = document.createElement("a");
      a.href = localPdfUrl;
      a.download = "scanned_document.pdf";
      a.click();
    }
  }

  // ── Misc helpers ──────────────────────────────────────────────────────────
  function clearLocalPdf() {
    if (localPdfUrl) URL.revokeObjectURL(localPdfUrl);
    localPdfUrl = null;
  }

  function closeEventSource() {
    if (activeEventSource) { activeEventSource.close(); activeEventSource = null; }
  }

  function formatBytes(n) {
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
    return (n / 1048576).toFixed(1) + " MB";
  }

  function safeFilename(name, fallback) {
    const cleaned = String(name || "").replace(/[^a-z0-9._-]+/gi, "_").replace(/^\.+/, "");
    return cleaned || fallback;
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

})();
}); // DOMContentLoaded
