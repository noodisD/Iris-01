/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          dark: '#1a1a2e',
          darker: '#16213e',
          gold: '#FFD700',
          goldLight: '#FFC107',
        },
        text: {
          primary: '#ecf0f1',
          secondary: '#bdc3c7',
        }
      },
      fontFamily: {
        sans: ['Segoe UI', 'Tahoma', 'Geneva', 'Verdana', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
