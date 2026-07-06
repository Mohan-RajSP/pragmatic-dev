const path = require("path");

module.exports = (_env, argv) => {
  const isProduction = argv && argv.mode === "production";

  return {
    entry: path.resolve(__dirname, "src/pragmatic-dev-tipsapp.tsx"),
    mode: isProduction ? "production" : "development",
    output: {
      filename: "pragmatic-dev-tipsapp.js",
      libraryTarget: "system",
      path: path.resolve(__dirname, "dist"),
      publicPath: "/",
      clean: true,
    },
    resolve: {
      extensions: [".ts", ".tsx", ".js"],
    },
    module: {
      rules: [
        { test: /\.tsx?$/, exclude: /node_modules/, use: "ts-loader" },
        {
          // Compile Tailwind CSS to a *constructable* CSSStyleSheet so we can
          // inject it INSIDE the Shadow DOM via adoptedStyleSheets.
          test: /\.css$/,
          use: [
            { loader: "css-loader", options: { exportType: "css-style-sheet" } },
            "postcss-loader",
          ],
        },
      ],
    },
    // Shared singletons provided by the shell's import-map — never bundle them.
    externals: ["react", "react-dom", "single-spa"],
    devServer: {
      port: 9001,
      host: "0.0.0.0",
      // The shell (:9000) loads this bundle cross-origin, so allow it.
      headers: { "Access-Control-Allow-Origin": "*" },
      allowedHosts: "all",
      hot: false,
      liveReload: false,
    },
  };
};

