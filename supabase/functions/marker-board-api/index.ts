import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
};

const STATE_ID = "default";
const TOKEN_TTL_SECONDS = 60 * 60 * 24;
const BOARD_PASSWORD = Deno.env.get("BOARD_PASSWORD") || "revu1234";
const SESSION_SECRET = Deno.env.get("SESSION_SECRET") || "marker-board-session-secret-2026-04-22";

const supabase = createClient(
  Deno.env.get("SUPABASE_URL") || "",
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "",
);

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}

function base64UrlEncode(bytes: Uint8Array) {
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function base64UrlDecode(value: string) {
  const padded = value + "=".repeat((4 - (value.length % 4)) % 4);
  const binary = atob(padded.replaceAll("-", "+").replaceAll("_", "/"));
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

async function hmac(payload: string) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(SESSION_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  return new Uint8Array(signature);
}

async function createSessionToken() {
  const now = Math.floor(Date.now() / 1000);
  const payload = base64UrlEncode(new TextEncoder().encode(JSON.stringify({
    iat: now,
    exp: now + TOKEN_TTL_SECONDS,
  })));
  const signature = base64UrlEncode(await hmac(payload));
  return `${payload}.${signature}`;
}

async function verifySessionToken(token: string) {
  const [payload, signature] = token.split(".");
  if (!payload || !signature) return false;

  const expected = base64UrlEncode(await hmac(payload));
  if (signature !== expected) return false;

  try {
    const decoded = JSON.parse(new TextDecoder().decode(base64UrlDecode(payload)));
    return Number(decoded.exp || 0) >= Math.floor(Date.now() / 1000);
  } catch (_error) {
    return false;
  }
}

async function requireAuth(req: Request) {
  const authHeader = req.headers.get("Authorization") || "";
  const token = authHeader.startsWith("Bearer ") ? authHeader.slice(7).trim() : "";
  return verifySessionToken(token);
}

async function loadState() {
  const { data, error } = await supabase.rpc("get_marker_board_state", {
    workspace_id_input: STATE_ID,
  });

  if (error) {
    throw error;
  }

  return data || null;
}

async function saveState(payload: Record<string, unknown>) {
  const { error } = await supabase.rpc("save_marker_board_state", {
    workspace_id_input: STATE_ID,
    state_input: payload,
  });

  if (error) {
    throw error;
  }
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  const url = new URL(req.url);
  const path = url.pathname;

  if (req.method === "POST" && path.endsWith("/auth")) {
    const payload = await req.json().catch(() => ({}));
    if (String(payload.password || "") !== BOARD_PASSWORD) {
      return jsonResponse({ ok: false, message: "비밀번호가 올바르지 않습니다." }, 401);
    }
    return jsonResponse({ ok: true, token: await createSessionToken() });
  }

  if (path.endsWith("/state")) {
    if (!(await requireAuth(req))) {
      return jsonResponse({ ok: false, message: "Unauthorized" }, 401);
    }

    if (req.method === "GET") {
      try {
        return jsonResponse({ ok: true, state: await loadState() });
      } catch (error) {
        return jsonResponse({ ok: false, message: error instanceof Error ? error.message : "Unknown error" }, 500);
      }
    }

    if (req.method === "PUT") {
      const payload = await req.json().catch(() => null);
      if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        return jsonResponse({ ok: false, message: "Payload must be an object" }, 400);
      }

      try {
        await saveState(payload as Record<string, unknown>);
        return jsonResponse({ ok: true });
      } catch (error) {
        return jsonResponse({ ok: false, message: error instanceof Error ? error.message : "Unknown error" }, 500);
      }
    }
  }

  return jsonResponse({ ok: false, message: "Not found" }, 404);
});
