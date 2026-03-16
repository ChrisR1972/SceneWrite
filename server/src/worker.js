/**
 * SceneWrite License API — Cloudflare Worker
 *
 * Routes:
 *   POST /api/webhook    — Stripe webhook (generates license on payment)
 *   POST /api/activate   — App sends key + machine_id to activate
 *   POST /api/validate   — App re-validates a previously activated license
 *
 * KV schema (key = license_key):
 *   {
 *     license_key, email, created_at, machine_id,
 *     activated, plan, stripe_payment_id
 *   }
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    try {
      if (request.method === "POST" && path === "/api/webhook") {
        return await handleWebhook(request, env);
      }
      if (request.method === "POST" && path === "/api/activate") {
        return await handleActivate(request, env);
      }
      if (request.method === "POST" && path === "/api/validate") {
        return await handleValidate(request, env);
      }
      if (request.method === "POST" && path === "/api/lookup-session") {
        return await handleLookupSession(request, env);
      }
      return jsonResponse({ error: "Not found" }, 404);
    } catch (err) {
      return jsonResponse({ error: "Internal server error" }, 500);
    }
  },
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Stripe-Signature",
  };
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders() },
  });
}

function generateKey() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const group = () =>
    Array.from({ length: 4 }, () =>
      chars[Math.floor(Math.random() * chars.length)]
    ).join("");
  return `SW-${group()}-${group()}-${group()}-${group()}`;
}

// ── Stripe Webhook ──────────────────────────────────────────────────────────

async function handleWebhook(request, env) {
  const body = await request.text();

  // --- Signature verification ---
  // In production, verify the Stripe-Signature header against
  // env.STRIPE_WEBHOOK_SECRET using Stripe's algorithm.
  // For now, a simplified check:
  const sig = request.headers.get("Stripe-Signature") || "";
  if (!sig && env.STRIPE_WEBHOOK_SECRET) {
    return jsonResponse({ error: "Missing signature" }, 401);
  }

  let event;
  try {
    event = JSON.parse(body);
  } catch {
    return jsonResponse({ error: "Invalid JSON" }, 400);
  }

  if (event.type !== "checkout.session.completed") {
    return jsonResponse({ received: true });
  }

  const session = event.data?.object;
  if (!session) return jsonResponse({ error: "No session data" }, 400);

  const email = session.customer_details?.email || session.customer_email || "";
  const paymentId = session.payment_intent || session.id;

  const key = generateKey();
  const record = {
    license_key: key,
    email,
    created_at: new Date().toISOString(),
    machine_id: null,
    activated: false,
    plan: "lifetime",
    stripe_payment_id: paymentId,
  };

  await env.LICENSES.put(key, JSON.stringify(record));

  // Index by email so you can look up keys for support
  const emailIndex = (await getJSON(env.LICENSES, `email:${email}`)) || [];
  emailIndex.push(key);
  await env.LICENSES.put(`email:${email}`, JSON.stringify(emailIndex));

  // Index by Stripe session ID so the success page can show the key
  await env.LICENSES.put(`session:${session.id}`, key);
  if (paymentId && paymentId !== session.id) {
    await env.LICENSES.put(`session:${paymentId}`, key);
  }

  return jsonResponse({ success: true, license_key: key });
}

// ── Activate ────────────────────────────────────────────────────────────────

async function handleActivate(request, env) {
  const { license_key, machine_id } = await request.json();
  if (!license_key || !machine_id) {
    return jsonResponse({ valid: false, error: "Missing license_key or machine_id" }, 400);
  }

  const record = await getJSON(env.LICENSES, license_key);
  if (!record) {
    return jsonResponse({ valid: false, error: "Invalid license key." });
  }

  // If already activated on a different machine, reject
  if (record.activated && record.machine_id && record.machine_id !== machine_id) {
    return jsonResponse({
      valid: false,
      error: "This license is already activated on another machine. Contact support to transfer.",
    });
  }

  // Activate (or re-confirm on same machine)
  record.activated = true;
  record.machine_id = machine_id;
  record.activated_at = new Date().toISOString();
  await env.LICENSES.put(license_key, JSON.stringify(record));

  return jsonResponse({
    valid: true,
    email: record.email,
    plan: record.plan,
  });
}

// ── Validate ────────────────────────────────────────────────────────────────

async function handleValidate(request, env) {
  const { license_key, machine_id } = await request.json();
  if (!license_key) {
    return jsonResponse({ valid: false, error: "Missing license_key" }, 400);
  }

  const record = await getJSON(env.LICENSES, license_key);
  if (!record) {
    return jsonResponse({ valid: false, error: "License not found." });
  }

  if (machine_id && record.machine_id && record.machine_id !== machine_id) {
    return jsonResponse({
      valid: false,
      error: "License is activated on a different machine.",
    });
  }

  return jsonResponse({
    valid: true,
    email: record.email,
    plan: record.plan,
  });
}

// ── Lookup by Stripe session (for the success page) ─────────────────────────

async function handleLookupSession(request, env) {
  const { session_id } = await request.json();
  if (!session_id) {
    return jsonResponse({ error: "Missing session_id" }, 400);
  }

  // Look up the key we stored under the session/payment ID
  const key = await env.LICENSES.get(`session:${session_id}`);
  if (!key) {
    return jsonResponse({ license_key: null });
  }
  return jsonResponse({ license_key: key });
}

// ── KV Utility ──────────────────────────────────────────────────────────────

async function getJSON(kv, key) {
  const raw = await kv.get(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
