/* Light fallback image-enhancement worker (the v1 worker).
 *
 * Used only when the full engine (`scan-worker-v2.js` + OpenCV.js WASM) cannot
 * load (see `static/js/workers/engine-loader.js`). It performs a cheap
 * per-pixel paper/ink blend instead of the real pipeline, so output quality is
 * intentionally lower — the `/scan-pdf` page waits for the full engine
 * instead.
 *
 * Worker protocol: same message shape as the v2 worker, minus `stats` and the
 * `ping` warmup probe:
 *   request   { width, height, pixels: ArrayBuffer }   RGBA, transferable
 *   response  { width, height, pixels: ArrayBuffer }   RGBA, transferable
 *
 * Local-only: no file or network access is used.
 */
"use strict";

self.onmessage = ({ data }) => {
  const { width, height, pixels } = data;
  const image = new Uint8ClampedArray(pixels);
  const output = new Uint8ClampedArray(image.length);
  const stride = width * 4;

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const i = y * stride + x * 4;
      const r = image[i];
      const g = image[i + 1];
      const b = image[i + 2];
      const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
      const paper = Math.max(0, Math.min(255, (luminance - 35) * 1.18 + 255));
      const ink = Math.max(0, Math.min(255, luminance * 1.12 - 18));
      const amount = Math.max(0, Math.min(1, (220 - luminance) / 150));
      output[i] = Math.round(r * (1 - amount) + Math.min(255, paper * 0.9 + ink * 0.1) * amount);
      output[i + 1] = Math.round(g * (1 - amount) + Math.min(255, paper * 0.9 + ink * 0.1) * amount);
      output[i + 2] = Math.round(b * (1 - amount) + Math.min(255, paper * 0.9 + ink * 0.1) * amount);
      output[i + 3] = image[i + 3];
    }
  }

  self.postMessage({ width, height, pixels: output.buffer }, [output.buffer]);
};
