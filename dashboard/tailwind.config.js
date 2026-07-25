/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0b0f19",
        card: "#131b2e",
        border: "#1f2d4d",
        brandSpace: "#00E5FF",
        brandHistory: "#FFBF00",
        brandTech: "#00FF66"
      }
    },
  },
  plugins: [],
}
