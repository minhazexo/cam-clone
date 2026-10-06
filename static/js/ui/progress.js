/**
 * Processing panel controller: title, animated scan line, page counter,
 * progress bar and the step log.
 *
 * This module is the successor of the duplicated helper blocks that used to
 * live in `app.js` and `scanpdf.js`. Every pipeline (server SSE, on-device,
 * fallback) drives the same panel API, so all three look identical to users:
 *
 *     const panel = createProcessingPanel();
 *     panel.reset();
 *     panel.title("Scanning your document…");
 *     panel.beginStep("Scanning page 1 of 12…");
 *     panel.finishStep("Page 1 scanned");
 *     panel.showTotal(12);
 *     panel.page(1);
 *     panel.progress(1, 12);
 *
 * All DOM lookups are lazy: a stale cached HTML page missing an element
 * degrades to a no-op instead of throwing (the original behaviour).
 */

import { $, setClass, setText, setHidden } from "../core/dom.js";

const IDS = {
  title: "procTitle",
  scanLine: "scanLine",
  counter: "pageCounter",
  current: "pageCurrent",
  total: "pageTotal",
  barWrap: "progressBarWrap",
  bar: "progressBar",
  pct: "progressPct",
  stepLog: "stepLog",
};

const CHECK = "\u2713";
const ARROW = "\u2192";
const DOT = "\u00b7";

/**
 * @typedef {object} ProcessingPanel
 * @property {() => void} reset          clear the log/progress back to defaults
 * @property {(text: string) => void} title        set the headline
 * @property {(active: boolean) => void} scanLine  toggle the scanner animation
 * @property {(text: string) => void} beginStep    add an in-progress step
 * @property {(text?: string) => void} finishStep  complete the current step
 * @property {(text: string) => void} done         add an already-complete step
 * @property {(total: number) => void} showTotal   reveal the page counter
 * @property {(page: number) => void} page         update the current page number
 * @property {(done: number, total: number) => void} progress update the bar
 */

/**
 * Create a controller bound to the current page's processing panel.
 *
 * @returns {ProcessingPanel}
 */
export function createProcessingPanel() {
  let activeStep = null;

  function reset() {
    activeStep = null;
    const log = $(IDS.stepLog);
    if (log) log.innerHTML = "";
    setHidden($(IDS.counter), true);
    setHidden($(IDS.barWrap), true);
    const bar = $(IDS.bar);
    if (bar) {
      bar.style.width = "0%";
      bar.classList.remove("active");
    }
    setText($(IDS.pct), "0%");
    scanLine(false);
    title("Preparing\u2026");
  }

  function title(text) {
    setText($(IDS.title), text);
  }

  function scanLine(active) {
    setClass($(IDS.scanLine), "active", active);
  }

  function page(number) {
    setText($(IDS.current), number);
  }

  function progress(done, total) {
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    const bar = $(IDS.bar);
    if (bar) {
      bar.style.width = `${pct}%`;
      setClass(bar, "active", pct > 0 && pct < 100);
    }
    setText($(IDS.pct), `${pct}%`);
  }

  function showTotal(total) {
    setText($(IDS.current), 0);
    setText($(IDS.total), total);
    setHidden($(IDS.counter), false);
    setHidden($(IDS.barWrap), false);
    progress(0, total);
  }

  function addStep(state, text) {
    const log = $(IDS.stepLog);
    if (!log) return null;

    // Complete the previous active step before adding a new one.
    if (activeStep && activeStep.classList.contains("step-active")) {
      activeStep.classList.remove("step-active");
      activeStep.classList.add("step-done");
      const icon = activeStep.querySelector(".step-icon");
      if (icon) {
        icon.className = "step-icon done";
        icon.textContent = CHECK;
      }
    }

    const li = document.createElement("li");
    li.className =
      state === "active" ? "step-active" : state === "done" ? "step-done" : "";

    const iconEl = document.createElement("span");
    iconEl.className =
      "step-icon " + (state === "active" ? "active" : state === "done" ? "done" : "pending");
    iconEl.textContent = state === "done" ? CHECK : state === "active" ? ARROW : DOT;

    const textEl = document.createElement("span");
    textEl.textContent = text;

    li.appendChild(iconEl);
    li.appendChild(textEl);
    log.appendChild(li);
    li.scrollIntoView({ behavior: "smooth", block: "nearest" });

    if (state === "active") activeStep = li;
    return li;
  }

  function beginStep(text) {
    addStep("active", text);
  }

  function finishStep(newText) {
    if (!activeStep) return;
    activeStep.classList.remove("step-active");
    activeStep.classList.add("step-done");
    const icon = activeStep.querySelector(".step-icon");
    if (icon) {
      icon.className = "step-icon done";
      icon.textContent = CHECK;
    }
    if (newText) {
      const span = activeStep.querySelector("span:last-child");
      if (span) span.textContent = newText;
    }
    activeStep = null;
  }

  function done(text) {
    addStep("done", text);
  }

  return {
    reset,
    title,
    scanLine,
    beginStep,
    finishStep,
    done,
    showTotal,
    page,
    progress,
  };
}
