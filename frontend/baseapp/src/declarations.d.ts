// Allow importing the single-spa-layout template as a raw string.
declare module "*.html" {
  const content: string;
  export default content;
}

