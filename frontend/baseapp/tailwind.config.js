/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,html,ejs}"],
  theme: {
    extend: {
      colors: {
        // Shared brand tokens (MFEs reference these via CSS variables).
        brand: {
          DEFAULT: "#4f46e5",
          dark: "#4338ca",
        },
      },
    },
  },
  plugins: [],
};

