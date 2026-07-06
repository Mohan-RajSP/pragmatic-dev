/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Consume the shell's shared token (CSS vars pierce the shadow boundary).
        brand: "var(--brand, #4f46e5)",
      },
    },
  },
  plugins: [],
};

