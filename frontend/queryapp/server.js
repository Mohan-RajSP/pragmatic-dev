/**
 * Express server for the queryapp MFE.
 *
 * Serves the webpack-built SystemJS bundle from ./dist. The shell loads this
 * bundle cross-origin via its import-map, so we send permissive CORS headers.
 * There's no HTML page here — it's just the JS module.
 */
const path = require("path");
const express = require("express");

const app = express();
const PORT = process.env.PORT || 9002;
const DIST_DIR = path.join(__dirname, "dist");

app.use(
  express.static(DIST_DIR, {
    setHeaders(res) {
      res.setHeader("Access-Control-Allow-Origin", "*");
    },
  })
);

app.listen(PORT, "0.0.0.0", () => {
  // eslint-disable-next-line no-console
  console.log(`[queryapp] serving ./dist on http://0.0.0.0:${PORT}`);
});

