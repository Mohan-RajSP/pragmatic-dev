// css-loader (exportType: "css-style-sheet") returns a constructable stylesheet.
declare module "*.css" {
  const sheet: CSSStyleSheet;
  export default sheet;
}

