import * as pdfjsLib from "pdfjs-dist/legacy/build/pdf.js";
import { PDFDocument } from "pdf-lib";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/static/vendor/pdf.worker.js";

(window as unknown as {
  pdfjsLib: typeof pdfjsLib;
  PDFLib: { PDFDocument: typeof PDFDocument };
}).pdfjsLib = pdfjsLib;
(window as unknown as {
  PDFLib: { PDFDocument: typeof PDFDocument };
}).PDFLib = { PDFDocument };
