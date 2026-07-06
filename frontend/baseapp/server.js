/**
 * Express server for the baseapp shell.
 *
 * Serves the webpack-built static assets from ./dist. Because this is a
 * single-spa root-config (client-side routing), any non-file request falls
 * back to index.html. Bundles are served with permissive CORS so the browser
 * can also load them cross-origin if referenced that way.
 */
const path = require("path");
const express = require("express");

const app = express();
const PORT = process.env.PORT || 9000;
const DIST_DIR = path.join(__dirname, "dist");

app.use(
  express.static(DIST_DIR, {
    setHeaders(res) {
      res.setHeader("Access-Control-Allow-Origin", "*");
    },
  })
);

// SPA fallback — serve the shell HTML for any client-side route.
app.get("*", (_req, res) => {
  res.sendFile(path.join(DIST_DIR, "index.html"));
});

app.listen(PORT, "0.0.0.0", () => {
  // eslint-disable-next-line no-console
  console.log(`[baseapp] serving ./dist on http://0.0.0.0:${PORT}`);
});

