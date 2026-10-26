const API_URL = (
  process.env.NEXT_PUBLIC_IMAGE_API_BASE_URL ||
  "https://vasuki-ai.onrender.com"
).replace(/\/$/, "");

export type AccountPlan = {
  plan: "free" | "owner";
  is_owner: boolean;
  puter_access: boolean;
  pro_expires_at?: string | null;
  amount_paise: number;
  plan_days: number;
};

export type PuterImageQuota = {
  allowed: boolean;
  image_count: number;
  daily_limit: number;
  daily_remaining: number;
  persistent: boolean;
};


async function readJson(response: Response) {
  const raw = await response.text();
  let data: Record<string, unknown> = {};
  if (raw) {
    try {
      data = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      data = { detail: raw };
    }
  }
  if (!response.ok) {
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status})`,
    );
  }
  return data;
}

function headers(accessToken: string, json = false) {
  const value: Record<string, string> = {
    Authorization: `Bearer ${accessToken}`,
  };
  if (json) value["Content-Type"] = "application/json";
  return value;
}

export async function fetchAccountPlan(accessToken: string) {
  const response = await fetch(`${API_URL}/api/account/plan`, {
    headers: headers(accessToken),
    cache: "no-store",
  });
  return (await readJson(response)) as unknown as AccountPlan;
}

export async function fetchPuterContext(
  accessToken: string,
  useMemory: boolean,
) {
  const response = await fetch(`${API_URL}/api/puter/context`, {
    method: "POST",
    headers: headers(accessToken, true),
    body: JSON.stringify({ use_memory: useMemory }),
    cache: "no-store",
  });
  return (await readJson(response)) as {
    allowed: boolean;
    plan: string;
    system_prompt: string;
  };
}


export async function consumePuterImageQuota(
  accessToken: string,
) {
  const response = await fetch(
    `${API_URL}/api/puter/image-quota`,
    {
      method: "POST",
      headers: headers(accessToken),
      cache: "no-store",
    },
  );

  return (await readJson(response)) as unknown as PuterImageQuota;
}

export async function releasePuterImageQuota(
  accessToken: string,
) {
  const response = await fetch(
    `${API_URL}/api/puter/image-quota/release`,
    {
      method: "POST",
      headers: headers(accessToken),
      cache: "no-store",
    },
  );

  return (await readJson(response)) as unknown as PuterImageQuota;
}
