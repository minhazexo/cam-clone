/* RScan /scan-pdf — local full-quality scan flow (Step 4 of docs/09-LOCAL-FULL-QUALITY-PLAN.md).
 *
 * Classic script, no modules/bundler. Mirrors the proven scanPdfLocally /
 * enhanceCanvas pattern from static/js/app.js, but at 200-DPI parity with the
 * server pipeline, with A4 output pages and a black frame drawn on canvas.
 *
 * Flow: file picker → pdf.js render (scale 200/72, width capped at 2500px,
 * 1800px on small screens) → scan worker ({width,height,pixels} protocol) →
 * putImageData → canvas black frame → JPEG q0.80 → pdf-lib embedJpg →
 * A4 page matched to image aspect → blob download + thumbnail grid.
 */
(function () {
  "use strict";

  /* ── Guards — same names/values as static/js/app.js ── */
  var MAX_LOCAL_PDF_BYTES = 50 * 1024 * 1024;
  var MAX_LOCAL_PDF_PAGES = 50;

  var PDF_WORKER_SRC = "/static/vendor/pdf.worker.js";
  var JPEG_QUALITY = 0.80;
  var MAX_THUMBNAILS = 12;
  var A4_PORTRAIT = [595, 842];
  var A4_LANDSCAPE = [842, 595];

  var _activeStepLi = null;
  var _blobUrl = null;
  var _engineReady = false;
  var _engineWorker = null; // persistent warm worker from the loader (never per-scan)
  var _scanning = false;

  function $(id) { return document.getElementById(id); }

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    if (window.pdfjsLib && window.pdfjsLib.GlobalWorkerOptions) {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDF_WORKER_SRC;
    }

    var btnPdf = $("btnPdf");
    var fileInput = $("fileInput");
    var uploadZone = $("uploadZone");
    var btnScanMore = $("btnScanMore");

    /* Engine gating: btnPdf stays disabled until the warm worker arrives. */
    if (btnPdf) btnPdf.disabled = true;
    if (window.RScanEngine && typeof window.RScanEngine.ready === "function") {
      window.RScanEngine.ready(
        function (info) {
          _engineReady = true;
          _engineWorker = info && info.worker ? info.worker : null;
          var st = $("engineStatus");
          if (st) st.textContent = "\u25CF Scan engine ready (" + info.source + ")";
          if (btnPdf && !_scanning) btnPdf.disabled = false;
        },
        function (err) {
          var st = $("engineStatus");
          if (st) st.textContent = "\u25CF Engine failed to load: " + (err && err.message ? err.message : String(err));
        }
      );
    } else {
      var st = $("engineStatus");
      if (st) st.textContent = "\u25CF Engine loader missing (opencv-loader.js not loaded)";
    }

    if (btnPdf && fileInput) {
      btnPdf.addEventListener("click", function (e) {
        e.stopPropagation();
        fileInput.accept = ".pdf";
        fileInput.multiple = false;
        fileInput.click();
      });
    }

    if (fileInput) {
      fileInput.addEventListener("change", function () {
        if (fileInput.files && fileInput.files.length) {
          var f = fileInput.files[0];
          fileInput.value = "";
          handleFile(f);
        }
      });
    }

    if (uploadZone && fileInput) {
      uploadZone.addEventListener("dragover", function (e) {
        e.preventDefault();
        uploadZone.classList.add("dragover");
      });
      uploadZone.addEventListener("dragleave", function () {
        uploadZone.classList.remove("dragover");
      });
      uploadZone.addEventListener("drop", function (e) {
        e.preventDefault();
        uploadZone.classList.remove("dragover");
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
          handleFile(e.dataTransfer.files[0]);
        }
      });
      uploadZone.addEventListener("click", function (e) {
        if (e.target && e.target.closest && e.target.closest(".btn")) return;
        fileInput.click();
      });
    }

    if (btnScanMore) {
      btnScanMore.addEventListener("click", resetToUpload);
    }

    window.addEventListener("pagehide", function () {
      if (_engineWorker) { try { _engineWorker.terminate(); } catch (e) { /* ignore */ } }
      _engineWorker = null;
    });
  }

  function handleFile(file) {
    if (!file || _scanning) return;
    runScan(file).catch(function (err) {
      addStep("active", "Scan failed");
      markStepDone("Error: " + (err && err.message ? err.message : String(err)));
      updateProcTitle("Scan failed \u2014 try again");
      setBusy(false);
      _scanning = false;
    });
  }

  function setBusy(busy) {
    _scanning = busy;
    var btnPdf = $("btnPdf");
    if (btnPdf) btnPdf.disabled = busy || !_engineReady;
  }

  function runScan(file) {
    if (!window.pdfjsLib || !window.PDFLib) {
      return Promise.reject(new Error("Local PDF engine is still loading. Please try again."));
    }
    if (!_engineWorker) {
      return Promise.reject(new Error("Scan engine is still warming up. Please wait for 'ready' and try again."));
    }
    if (file.size > MAX_LOCAL_PDF_BYTES) {
      return Promise.reject(new Error("This PDF is larger than the 50 MB local-processing limit."));
    }

    showProcessing();
    resetProcessingUI();
    setBusy(true);
    updateProcTitle("Scanning locally\u2026");

    var source = null;
    var output = null;
    var worker = _engineWorker; // persistent warm worker — never terminated per scan
    var pageImages = [];

    return loadPdfBytes(file)
      .then(function (bytes) {
        addStep("active", "Loading PDF in browser\u2026");
        return window.pdfjsLib.getDocument({ data: bytes }).promise;
      })
      .then(function (src) {
        source = src;
        markStepDone("Found " + source.numPages + " page(s)");
        if (source.numPages > MAX_LOCAL_PDF_PAGES) {
          throw new Error("This PDF has " + source.numPages + " pages. Local scanning supports up to " + MAX_LOCAL_PDF_PAGES + " pages.");
        }
        var pagesToScan = source.numPages;
        showPageCounter(0, pagesToScan);
        showProgressBar(0, pagesToScan);
        updateProcTitle("Scanning " + pagesToScan + " pages\u2026");
        return window.PDFLib.PDFDocument.create();
      })
      .then(function (doc) {
        output = doc;
        addStep("done", "Engine worker ready");
        return processPages(source, source.numPages, worker, output, pageImages);
      })
      .then(function () {
        addStep("active", "Building PDF\u2026");
        updateProcTitle("Assembling PDF\u2026");
        return output.save();
      })
      .then(function (resultBytes) {
        if (_blobUrl) { try { URL.revokeObjectURL(_blobUrl); } catch (e) { /* ignore */ } }
        var blob = new Blob([resultBytes], { type: "application/pdf" });
        _blobUrl = URL.createObjectURL(blob);
        markStepDone("Done! PDF ready");
        updateProcTitle("Scan complete");
        showResults(file.name, pageImages, _blobUrl);
      })
      .then(function () {
        /* Persistent worker stays alive for the next scan. */
        setBusy(false);
      })
      .catch(function (err) {
        throw err;
      });
  }

  function loadPdfBytes(file) {
    return file.arrayBuffer().then(function (buf) { return new Uint8Array(buf); });
  }

  function processPages(source, pagesToScan, worker, output, pageImages) {
    var smallScreen = (window.innerWidth && window.innerWidth < 768) ||
      (window.screen && window.screen.width && window.screen.width < 768);
    var capWidth = smallScreen ? 1800 : 2500;

    var chain = Promise.resolve();
    for (var pageNumber = 1; pageNumber <= pagesToScan; pageNumber++) {
      (function (n) {
        chain = chain.then(function () {
          return processOnePage(source, n, pagesToScan, capWidth, worker, output, pageImages);
        });
      })(pageNumber);
    }
    return chain;
  }

  function processOnePage(source, pageNumber, pagesToScan, capWidth, worker, output, pageImages) {
    addStep("active", "Scanning page " + pageNumber + " of " + pagesToScan + "\u2026");
    setPageCurrent(pageNumber);
    updateProgressBar(pageNumber - 1, pagesToScan);

    var canvas = null;
    return source.getPage(pageNumber).then(function (page) {
      var pageSize = page.getViewport({ scale: 1 });
      /* 200-DPI parity with the server (200/72), capped for memory. */
      var scale = Math.min(200 / 72, capWidth / pageSize.width);
      var viewport = page.getViewport({ scale: scale });
      canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(viewport.width));
      canvas.height = Math.max(1, Math.round(viewport.height));
      return page.render({ canvasContext: canvas.getContext("2d"), viewport: viewport }).promise;
    }).then(function () {
      return enhanceCanvas(canvas, worker);
    }).then(function () {
      drawPageBorder(canvas);
      var dataUrl = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
      var jpgBytes = dataUrlToBytes(dataUrl);
      return output.embedJpg(jpgBytes).then(function (embedded) {
        var landscape = canvas.width >= canvas.height;
        var dims = landscape ? A4_LANDSCAPE : A4_PORTRAIT;
        var pdfPage = output.addPage(dims);
        var fit = Math.min(dims[0] / canvas.width, dims[1] / canvas.height);
        pdfPage.drawImage(embedded, {
          x: (dims[0] - canvas.width * fit) / 2,
          y: (dims[1] - canvas.height * fit) / 2,
          width: canvas.width * fit,
          height: canvas.height * fit
        });
        if (pageImages.length < MAX_THUMBNAILS) {
          pageImages.push({ dataUrl: dataUrl, width: canvas.width, height: canvas.height });
        }
        markStepDone("Page " + pageNumber + " scanned");
        updateProgressBar(pageNumber, pagesToScan);
      });
    });
  }

  /* SAME protocol as scan-worker.js: posts {width,height,pixels}, gets it back. */
  function enhanceCanvas(canvas, worker) {
    return new Promise(function (resolve, reject) {
      var context = canvas.getContext("2d", { willReadFrequently: true });
      var imageData;
      try {
        imageData = context.getImageData(0, 0, canvas.width, canvas.height);
      } catch (err) {
        reject(err);
        return;
      }
      worker.onmessage = function (e) {
        var data = e && e.data;
        if (!data || !data.pixels) {
          reject(new Error("Worker returned invalid data."));
          return;
        }
        try {
          context.putImageData(new ImageData(new Uint8ClampedArray(data.pixels), data.width, data.height), 0, 0);
        } catch (err) {
          reject(err);
          return;
        }
        resolve(canvas);
      };
      worker.onerror = function () {
        reject(new Error("Scan worker stopped unexpectedly."));
      };
      try {
        worker.postMessage(
          { width: canvas.width, height: canvas.height, pixels: imageData.data.buffer },
          [imageData.data.buffer]
        );
      } catch (err) {
        reject(err);
      }
    });
  }

  function drawPageBorder(canvas) {
    var ctx = canvas.getContext("2d");
    if (!ctx) return;
    var lw = Math.max(2, Math.round(Math.min(canvas.width, canvas.height) * 0.003));
    ctx.save();
    ctx.strokeStyle = "#000000";
    ctx.lineWidth = lw;
    ctx.strokeRect(lw, lw, canvas.width - lw * 2, canvas.height - lw * 2);
    ctx.restore();
  }

  function dataUrlToBytes(dataUrl) {
    var binary = atob(dataUrl.split(",")[1]);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }

  function showResults(originalName, pageImages, pdfUrl) {
    var processingSection = $("processingSection");
    var resultsSection = $("resultsSection");
    var resultsGrid = $("resultsGrid");
    var btnDownloadAll = $("btnDownloadAll");
    if (processingSection) processingSection.classList.add("hidden");
    if (resultsSection) resultsSection.classList.remove("hidden");

    var dlName = safeFilename(String(originalName || "").replace(/\.pdf$/i, ""), "scanned_document") + ".pdf";
    if (btnDownloadAll) {
      btnDownloadAll.onclick = function () {
        var a = document.createElement("a");
        a.href = pdfUrl;
        a.download = dlName;
        document.body.appendChild(a);
        a.click();
        a.remove();
      };
    }

    if (!resultsGrid) return;
    resultsGrid.innerHTML = "";
    pageImages.forEach(function (img, i) {
      var card = document.createElement("div");
      card.className = "result-card";
      card.innerHTML =
        "<img class=\"result-card-img\" src=\"" + img.dataUrl + "\" alt=\"Scanned page " + (i + 1) + "\" loading=\"lazy\">" +
        "<div class=\"result-card-body\">" +
        "<div class=\"result-card-name\">" + esc(originalName) + " \u2014 page " + (i + 1) + "</div>" +
        "<div class=\"result-card-meta\">" + img.width + " \u00d7 " + img.height + "px</div>" +
        "</div>";
      resultsGrid.appendChild(card);
    });
  }

  function resetToUpload() {
    if (_scanning) return;
    if (_blobUrl) { try { URL.revokeObjectURL(_blobUrl); } catch (e) { /* ignore */ } _blobUrl = null; }
    var resultsGrid = $("resultsGrid");
    if (resultsGrid) resultsGrid.innerHTML = "";
    var btnDownloadAll = $("btnDownloadAll");
    if (btnDownloadAll) btnDownloadAll.onclick = null;
    var resultsSection = $("resultsSection");
    if (resultsSection) resultsSection.classList.add("hidden");
    var processingSection = $("processingSection");
    if (processingSection) processingSection.classList.add("hidden");
    var uploadSection = $("uploadSection");
    if (uploadSection) uploadSection.classList.remove("hidden");
    resetProcessingUI();
  }

  /* ── Minimal UI helpers (mirroring static/js/app.js; that file is untouched) ── */

  function showProcessing() {
    var uploadSection = $("uploadSection");
    if (uploadSection) uploadSection.classList.add("hidden");
    var resultsSection = $("resultsSection");
    if (resultsSection) resultsSection.classList.add("hidden");
    var resultsGrid = $("resultsGrid");
    if (resultsGrid) resultsGrid.innerHTML = "";
    var processingSection = $("processingSection");
    if (processingSection) processingSection.classList.remove("hidden");
    resetProcessingUI();
  }

  function resetProcessingUI() {
    _activeStepLi = null;
    var sl = $("stepLog");
    if (sl) sl.innerHTML = "";
    var pc = $("pageCounter");
    if (pc) pc.classList.add("hidden");
    var pbw = $("progressBarWrap");
    if (pbw) pbw.classList.add("hidden");
    var pb = $("progressBar");
    if (pb) { pb.style.width = "0%"; pb.classList.remove("active"); }
    var pp = $("progressPct");
    if (pp) pp.textContent = "0%";
    updateProcTitle("Preparing\u2026");
  }

  function updateProcTitle(text) {
    var el = $("procTitle");
    if (el) el.textContent = text;
  }

  function showPageCounter(current, total) {
    var pc = $("pageCurrent");
    if (pc) pc.textContent = current;
    var pt = $("pageTotal");
    if (pt) pt.textContent = total;
    var counter = $("pageCounter");
    if (counter) counter.classList.remove("hidden");
  }

  function setPageCurrent(num) {
    var el = $("pageCurrent");
    if (el) el.textContent = num;
  }

  function showProgressBar(done, total) {
    var wrap = $("progressBarWrap");
    if (wrap) wrap.classList.remove("hidden");
    updateProgressBar(done, total);
  }

  function updateProgressBar(done, total) {
    var pct = total > 0 ? Math.round((done / total) * 100) : 0;
    var pb = $("progressBar");
    if (pb) {
      pb.style.width = pct + "%";
      if (pct > 0 && pct < 100) pb.classList.add("active");
      else pb.classList.remove("active");
    }
    var pp = $("progressPct");
    if (pp) pp.textContent = pct + "%";
  }

  function addStep(state, text) {
    var log = $("stepLog");
    if (!log) return null;
    if (_activeStepLi && _activeStepLi.classList.contains("step-active")) {
      _activeStepLi.classList.remove("step-active");
      _activeStepLi.classList.add("step-done");
      var prevIcon = _activeStepLi.querySelector(".step-icon");
      if (prevIcon) { prevIcon.className = "step-icon done"; prevIcon.textContent = "\u2713"; }
    }
    var li = document.createElement("li");
    li.className = state === "active" ? "step-active" : state === "done" ? "step-done" : "";
    var iconEl = document.createElement("span");
    iconEl.className = "step-icon " + (state === "active" ? "active" : state === "done" ? "done" : "pending");
    iconEl.textContent = state === "done" ? "\u2713" : state === "active" ? "\u2192" : "\u00b7";
    var textEl = document.createElement("span");
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
    var icon = _activeStepLi.querySelector(".step-icon");
    if (icon) { icon.className = "step-icon done"; icon.textContent = "\u2713"; }
    if (newText) {
      var span = _activeStepLi.querySelector("span:last-child");
      if (span) span.textContent = newText;
    }
    _activeStepLi = null;
  }

  function safeFilename(name, fallback) {
    var cleaned = String(name || "").replace(/[^a-z0-9._-]+/gi, "_").replace(/^\.+/, "");
    return cleaned || fallback;
  }

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

})();
