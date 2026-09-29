/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: '#201a13',
          soft: '#4c4438',
          muted: '#857a68',
        },
        paper: '#f7f2e7',
        card: '#fffdf8',
        line: {
          DEFAULT: '#e8dfc9',
          strong: '#d9cdaf',
        },
        gold: {
          DEFAULT: '#cba868',
          deep: '#9a7536',
          soft: '#f4ead4',
          wash: '#faf4e6',
        },
        green: {
          DEFAULT: '#1e7b43',
          soft: '#e6f3ea',
          line: '#b9dcc6',
        },
        warn: {
          DEFAULT: '#9b5b00',
          bg: '#faf0da',
          line: '#ecd3a2',
        },
        bad: {
          DEFAULT: '#b42318',
          bg: '#fbeeec',
          line: '#f0c1ba',
        },
        side: {
          DEFAULT: '#1b1610',
          soft: '#2a2318',
          text: '#d8cdb8',
        },
      },
      fontFamily: {
        serif: ['Cormorant Garamond', 'Georgia', 'serif'],
        sans: ['Lexend', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
