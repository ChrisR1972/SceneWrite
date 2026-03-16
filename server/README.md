# SceneWrite License API

Cloudflare Worker that handles license key generation, activation, and validation.

## Setup

### 1. Prerequisites
- [Node.js 18+](https://nodejs.org/)
- A [Cloudflare account](https://dash.cloudflare.com/sign-up) (free tier is sufficient)
- A [Stripe account](https://dashboard.stripe.com/register)

### 2. Install dependencies
```bash
cd server
npm install
```

### 3. Authenticate with Cloudflare
```bash
npx wrangler login
```

### 4. Create the KV namespace
```bash
npx wrangler kv:namespace create "LICENSES"
# Copy the id into wrangler.toml

npx wrangler kv:namespace create "LICENSES" --preview
# Copy the preview_id into wrangler.toml
```

### 5. Set the Stripe webhook secret
```bash
npx wrangler secret put STRIPE_WEBHOOK_SECRET
# Paste the whsec_... value from Stripe dashboard
```

### 6. Deploy
```bash
npm run deploy
```

The worker will be available at `https://scenewrite-api.<your-subdomain>.workers.dev`.

### 7. Custom domain (optional)
In the Cloudflare dashboard, add a custom route so the worker responds at
`https://api.scenewrite.app/*`. This requires your domain to be on Cloudflare DNS.

### 8. Configure Stripe webhook
In the [Stripe dashboard](https://dashboard.stripe.com/webhooks):
1. Add endpoint: `https://api.scenewrite.app/api/webhook`
2. Select event: `checkout.session.completed`
3. Copy the signing secret and set it via step 5

## Local Development
```bash
npm run dev
```
This starts a local dev server on `http://localhost:8787`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/webhook` | Stripe webhook — generates license key on payment |
| POST | `/api/activate` | Activate a license key (binds to machine) |
| POST | `/api/validate` | Re-validate an activated license |

## Cost
- Cloudflare Workers free tier: 100,000 requests/day
- Cloudflare KV free tier: 100,000 reads/day, 1,000 writes/day
- Stripe: 2.9% + $0.30 per transaction (no monthly fee)
