# Tallyable landing site

Next.js 15 + Tailwind 4 + Framer Motion, exported as plain static files.

```
cd site
npm install
npm run dev      # http://localhost:3000
npm run build    # static site in site/out
```

Buttons point at the live app, https://tallyable.streamlit.app (`components/links.ts`).

## Online

Live at https://bokchoi-kc0420.github.io/Tallyable/. `.github/workflows/pages.yml` rebuilds and
publishes it on every merge to main that touches `site/`. Image and font paths are relative
(`art/...`, not `/art/...`) so they work under the `/Tallyable/` sub-path.

Art in `public/art/` is cropped from the Figma AI drafts. `logo.png` is the final logo, unedited.

## The built copy in `landing/`

`start.bat` opens the landing page from `landing/` (a static build of this folder), so it
works without Node. After changing the site, rebuild that copy from the repo root:

```
cd site && npm run build && cd .. && rm -rf landing && cp -r site/out landing
```
