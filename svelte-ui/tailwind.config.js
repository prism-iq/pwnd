/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  theme: {
    extend: {
      colors: {
        'l-dark': '#0a0a0f',
        'l-darker': '#12121a',
        'l-border': '#2a2a4a',
        'l-accent': '#667eea',
        'l-accent2': '#764ba2',
      }
    },
  },
  plugins: [],
}
