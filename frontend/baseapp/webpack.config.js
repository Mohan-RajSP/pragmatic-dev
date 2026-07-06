const path = require("path");
const HtmlWebpackPlugin = require("html-webpack-plugin");

module.exports = (_env, argv) => {
  const isProduction = argv && argv.mode === "production";

  return {
    entry: path.resolve(__dirname, "src/pragmatic-dev-root-config.ts"),
    mode: isProduction ? "production" : "development",
    output: {
      filename: "pragmatic-dev-root-config.js",
      // SystemJS module format — the shell is loaded via the import-map.
      libraryTarget: "system",
      path: path.resolve(__dirname, "dist"),
      publicPath: "/",
      clean: true,
    },
    resolve: {
      extensions: [".ts", ".js"],
    },
    module: {
      rules: [
        { test: /\.ts$/, exclude: /node_modules/, use: "ts-loader" },
        {
          // The single-spa-layout template imported as a raw string.
          test: /\.html$/,
          exclude: /index\.ejs$/,
          type: "asset/source",
        },
        {
          test: /\.css$/,
          use: ["style-loader", "css-loader", "postcss-loader"],
        },
      ],
    },
    // Provided at runtime via the SystemJS import-map, so don't bundle them.
    externals: ["single-spa", /^@pragmatic-dev\//],
    devServer: {
      port: 9000,
      host: "0.0.0.0",
      historyApiFallback: true,
      // Allow the MFEs (other origins/ports) to load shell assets in dev.
      headers: { "Access-Control-Allow-Origin": "*" },
      allowedHosts: "all",
    },
    plugins: [
      new HtmlWebpackPlugin({
        template: path.resolve(__dirname, "src/index.ejs"),
        templateParameters: { isLocal: !isProduction },
      }),
    ],
  };
};

