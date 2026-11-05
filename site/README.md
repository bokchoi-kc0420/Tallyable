# Tallyable landing site

Next.js 15 + Tailwind 4 + Framer Motion, exported as plain static files.

```
cd site
npm install
npm run dev      # http://localhost:3000
npm run build    # static site in site/out
```

"Get Started" points at `NEXT_PUBLIC_APP_URL` (default `http://localhost:8501`, the local Streamlit app).

## Putting it online (free, when you're ready)

1. Sign in at vercel.com with GitHub and import this repo.
2. Set **Root Directory** to `site`. Framework preset: Next.js.
3. Add env var `NEXT_PUBLIC_APP_URL` = your Streamlit app's URL (see `docs/deploy_streamlit_cloud.md`).
4. Deploy. Every push to main redeploys.

Art in `public/art/` is cropped from the Figma AI drafts. `logo.png` is the final logo, unedited.
