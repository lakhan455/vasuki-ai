const API_URL = (
  process.env.NEXT_PUBLIC_IMAGE_API_BASE_URL ||
  "https://vasuki-ai.onrender.com"
).replace(/\/$/, "");

export type AccountPlan = {
  plan: "free" | "pro" | "owner";
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

type RazorpayOrder = {
  key_id: string;
  order_id: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
};

type RazorpayResult = {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
};

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => {
      open: () => void;
      on: (
        event: string,
        handler: (response: { error?: { description?: string } }) => void,
      ) => void;
    };
  }
}

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

async function createOrder(accessToken: string) {
  const response = await fetch(`${API_URL}/api/billing/create-order`, {
    method: "POST",
    headers: headers(accessToken),
    cache: "no-store",
  });
  return (await readJson(response)) as unknown as RazorpayOrder;
}

async function verifyPayment(
  accessToken: string,
  result: RazorpayResult,
) {
  const response = await fetch(`${API_URL}/api/billing/verify`, {
    method: "POST",
    headers: headers(accessToken, true),
    body: JSON.stringify(result),
    cache: "no-store",
  });
  return readJson(response);
}

function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve();

  return new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      'script[src="https://checkout.razorpay.com/v1/checkout.js"]',
    );
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error("Razorpay checkout load nahi hua.")),
        { once: true },
      );
      return;
    }

    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () =>
      reject(new Error("Razorpay checkout load nahi hua."));
    document.head.appendChild(script);
  });
}

export async function buyVasukiPro(
  accessToken: string,
  user: { name?: string; email?: string },
) {
  const order = await createOrder(accessToken);
  await loadRazorpay();

  if (!window.Razorpay) {
    throw new Error("Razorpay checkout unavailable.");
  }

  return new Promise<Record<string, unknown>>((resolve, reject) => {
    const RazorpayCtor = window.Razorpay;
    if (!RazorpayCtor) {
      reject(new Error("Razorpay checkout unavailable."));
      return;
    }

    const checkout = new RazorpayCtor({
      key: order.key_id,
      amount: order.amount,
      currency: order.currency,
      name: order.name,
      description: order.description,
      order_id: order.order_id,
      prefill: {
        name: user.name || "",
        email: user.email || "",
      },
      theme: { color: "#4f86f7" },
      handler: async (result: RazorpayResult) => {
        try {
          resolve(await verifyPayment(accessToken, result));
        } catch (error) {
          reject(error);
        }
      },
      modal: {
        ondismiss: () =>
          reject(new Error("Payment window close kar diya gaya.")),
      },
    });

    checkout.on("payment.failed", (response) => {
      reject(
        new Error(
          response.error?.description ||
            "Payment failed. Dobara try karein.",
        ),
      );
    });
    checkout.open();
  });
}
