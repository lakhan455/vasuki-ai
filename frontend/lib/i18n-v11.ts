
export type V11Locale = "en" | "hi" | "es" | "fr" | "de" | "ja";

const messages: Record<V11Locale, Record<string, string>> = {
  en: { title: "Reliability + Agent Control Center", overview: "Overview", voice: "Voice", sandbox: "Sandbox", research: "Research", code: "Coding Agent", video: "Video", multimodal: "Multimodal", privacy: "Privacy" },
  hi: { title: "Reliability + Agent Control Center", overview: "Overview", voice: "Voice", sandbox: "Sandbox", research: "Research", code: "Coding Agent", video: "Video", multimodal: "Multimodal", privacy: "Privacy" },
  es: { title: "Centro de fiabilidad y agentes", overview: "Resumen", voice: "Voz", sandbox: "Entorno aislado", research: "Investigación", code: "Agente de código", video: "Video", multimodal: "Multimodal", privacy: "Privacidad" },
  fr: { title: "Centre de fiabilité et d’agents", overview: "Aperçu", voice: "Voix", sandbox: "Bac à sable", research: "Recherche", code: "Agent de code", video: "Vidéo", multimodal: "Multimodal", privacy: "Confidentialité" },
  de: { title: "Zuverlässigkeits- und Agentenzentrale", overview: "Übersicht", voice: "Sprache", sandbox: "Sandbox", research: "Recherche", code: "Coding-Agent", video: "Video", multimodal: "Multimodal", privacy: "Datenschutz" },
  ja: { title: "信頼性・エージェント管理センター", overview: "概要", voice: "音声", sandbox: "サンドボックス", research: "リサーチ", code: "コーディングエージェント", video: "動画", multimodal: "マルチモーダル", privacy: "プライバシー" },
};

export function v11Locale(value?: string): V11Locale {
  const code = (value || "").toLowerCase().split("-")[0];
  return (["en","hi","es","fr","de","ja"].includes(code) ? code : "en") as V11Locale;
}

export function v11t(locale: V11Locale, key: string) {
  return messages[locale]?.[key] || messages.en[key] || key;
}
