/* Write Vite's entry pages. They are generated rather than committed: the
   repository keeps HTML out of every tree but the product frontends (AGENTS.md
   section 7), and this island lives under experimental/.

   Both pages set Chinese in a Song face: the Latin face comes first and Chinese
   falls back to Noto Serif SC, loaded here, then the systems' own Song faces.
   index.html is the run viewer; studio.html is the RSI Studio, which wears
   ui-web's stylesheet and replaces only its --sans stack (studio.css). */
import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')

const page = ({ lang, title, head, entry }) => `<!doctype html>
<html lang="${lang}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${title}</title>${head}
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="${entry}"></script>
  </body>
</html>
`

writeFileSync(
  join(root, 'index.html'),
  page({
    lang: 'en',
    title: 'RSI Runs',
    head: `
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;500;600;700&display=swap" />`,
    entry: '/src/main.tsx',
  }),
)

writeFileSync(
  join(root, 'studio.html'),
  page({
    lang: 'en',
    title: 'RSI Studio',
    head: `
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Serif+SC:wght@400;500;600;700&display=swap" />`,
    entry: '/src/studio/main.tsx',
  }),
)
