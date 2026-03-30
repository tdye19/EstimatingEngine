# Construction Monitor
## Market Intelligence Dashboard for Construction Estimating

Real-time construction market data: BLS employment, FRED economic indicators, Census building permits, with a Market Pressure Index (MPI) scoring engine.

### Stack
- **Edge Functions:** Vercel Serverless (TypeScript)
- **Data Sources:** BLS, FRED, Census Bureau
- **Caching:** Upstash Redis
- **Dashboard:** Static HTML (48KB, zero build step)
- **MPI Engine:** 5 weighted components, 12 MSAs, 0-100 scoring

### Deploy
```bash
npm install
vercel login
vercel          # staging
vercel --prod   # production
```

Add env vars in Vercel dashboard. See `.env.example` for required keys.

### APEX Integration Path
Sprint 19-20: Wire MPI data into APEX estimates for live escalation
adjustments and regional cost index auto-correction.
