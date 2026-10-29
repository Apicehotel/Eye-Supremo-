// Recensioni online: porta in TypeScript la pipeline del backend Python
// (review_importers.py: pulizia/identita'; eye_services.py: classificazione, ranking, andamento camere).
// Le recensioni centrali sono poche migliaia: si scaricano una volta per sessione e si calcola nel browser.
import { CATEGORY_KEYWORDS, HOTELS, NEGATIONS, NEGATION_WINDOW, NEGATIVE_WORDS, POSITIVE_WORDS } from "./reviewLexicon.ts";

export type CentralReview = {
  sync_uuid: string; hotel_code: string; review_date: string; source: string | null;
  author: string | null; rating: number | null; room_code: string | null; text: string | null;
};
export type Tag = { category: string; polarity: "positive" | "negative"; confidence: number };
export type ReviewPayload = {
  id: string; hotel: string; hotel_code: string; room: string | null; author: string | null; source: string | null;
  rating: number | null; date: string; text: string; scores: Record<string, number>; tags: Tag[];
  normalized_key: string; valid: boolean; excluded_reason: string | null; raw_review_id: number; origin: string;
};

export const normalizeText = (value: string) =>
  value.normalize("NFKD").replace(/[^\x00-\x7f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().replace(/\s+/g, " ");

// ---- pulizia testo (clean_review_text) ----
const TECHNICAL = new RegExp(
  "^(?:numero di prenotazione\\b|categorie\\s+(?:base|extra)\\b|" +
  "staff|pulizia|posizione|servizi|comfort|rapporto qualità/prezzo|" +
  "letti|vista dalla camera|wifi|parcheggio|cuscini|" +
  "google|tripadvisor|booking(?:\\.com)?|" +
  "(?:vacanza|affari|coppia|famiglia|viaggio)\\s*[✦❘|·].*|" +
  "punti forti dell['’]hotel.*|costo giusto|" +
  "[^\\n]{1,100}\\s+ha scritto una recensione.*|\\d+\\s+contributi.*|" +
  "recensioni hotel.*|numero di prenotazione.*|\\d{1,2}\\s+ago\\s+\\d{4}.*|" +
  "(?:matrimoniale|suite|tripla|quadrupla|doppia|singola|junior|deluxe|superior|standard)[^\\n]{0,100}\\d{3,4}\\s+numero di prenotazione.*|" +
  "[A-ZÀ-Ý][^,\\n]{1,100},\\s*[a-z]{2}\\s+[A-ZÀ-Ý][^\\n]{1,100}|" +
  "(?:camere|servizio|posizione)\\s*\\d+(?:[.,]\\d+)?|" +
  "#[0-9]+|\\d{1,2}/\\d{1,2}/\\d{2,4}\\s*-\\s*\\d{1,2}/\\d{1,2}/\\d{2,4}|" +
  "[^\\n]{2,80}\\s+su google|[^\\n]{2,80}\\s+google|" +
  "rispondi|nuovo!|tradotto .*vedi l'originale|" +
  "nessuna recensione.*|da:|inviato:|a:|oggetto:|" +
  "hotel gio.*|codice identificativo nazionale.*|cin\\s+[A-Z0-9]+|tel\\.?\\s*\\d|" +
  "novità:.*|reception@.*|www\\..*|https?:.*|tel.*|amin|michele|" +
  "\\*?eventuali offerte presenti.*|scopri i nostri suggerimenti.*|" +
  "reception@.*|www\\..*|michele)$", "i");
const GUEST_METADATA = /^[^,\n]{1,100},\s*[a-z]{2}\b.*\b(?:in|out|camera|cam)\b/i;

export function cleanReviewText(text: string): string {
  let cleaned = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  cleaned = cleaned.replace(/<https?:\/\/[^>]+>|<mailto:[^>]+>|https?:\/\/\S+/gi, " ").replace(/<[^>]+>/g, " ");
  const googleMode = /\bgoogle\b/i.test(cleaned);
  cleaned = cleaned.replace(/^\s*_{10,}\s*$/gim, "\n");
  cleaned = cleaned.replace(/^.*?tradotto .*?vedi l['’]originale\s*/is, "");
  const lines: string[] = [];
  for (const line of cleaned.split("\n")) {
    let value = line.replace(/\s+/g, " ").trim();
    if (!value || TECHNICAL.test(value) || GUEST_METADATA.test(value) || /^\d+(?:[.,]\d+)?(?:\s*\/\s*\d+)?$/.test(value)) continue;
    if (googleMode && /^[A-ZÀ-Ý][a-zà-ÿ'’-]{2,}(?:\s+[A-ZÀ-Ý][a-zà-ÿ'’-]{2,}){0,3}(?:\s+DJ)?$/.test(value)) continue;
    if (/^(?:cam(?:era)?|room)\b/i.test(value) && /\b\d{1,4}[A-Z]?\b/i.test(value)) continue;
    value = value.replace(/^(?:Camere|Attività nelle vicinanze|Sicurezza|Percorribilità a piedi|Mangiare e bere|Dettagli importanti)\s*/i, "");
    lines.push(value);
  }
  return lines.join("\n").trim();
}

// ---- fonte, voto, identita' ----
const SCALES: Record<string, number> = { Booking: 10, Google: 5, TripAdvisor: 5 };
export function normalizedSource(source: string | null | undefined): string | null {
  const value = (source || "").trim();
  if (!value) return null;
  const aliases: Record<string, string> = { "booking.com": "Booking", "google maps": "Google", "trip advisor": "TripAdvisor" };
  return aliases[value.toLowerCase()] || value;
}
export function normalizedRating(value: unknown, source: string | null | undefined): number | null {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const n = Number(String(value).trim().replace(",", "."));
  const scale = SCALES[normalizedSource(source) || ""] ?? 10;
  return Number.isFinite(n) && n >= 0 && n <= scale ? n : null;
}
const validRoom = (code: string | null | undefined) => {
  const v = (code || "").trim();
  return /^\d{1,4}[A-Za-z]?$/.test(v) ? v : null;
};

// ---- voti per categoria nei digest (extract_category_scores) ----
const DATE_LIKE = /\b(?:in|out)\s*:?\s*\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b/gi;
const CATEGORY_LABELS: [string, string][] = [
  ["rapporto\\s+qualit[àa]\\s*/\\s*prezzo|qualit[àa]\\s*/\\s*prezzo", "Qualità/prezzo"], ["vista\\s+dalla\\s+camera", "Vista dalla camera"],
  ["ristorante\\s+sul\\s+posto", "Ristorante"], ["staff", "Staff"], ["pulizia", "Pulizia"], ["comfort", "Comfort"], ["posizione", "Posizione"],
  ["servizi|servizio", "Servizi"], ["letti", "Letti"], ["colazione", "Colazione"], ["wi-?fi", "Wi-Fi"], ["camere", "Camere"],
];
const CATEGORY_SCORE = CATEGORY_LABELS.map(([label, name]) => ({
  name,
  re: new RegExp("(?<![A-Za-zÀ-ÿ])(?:" + label + ")(?![A-Za-zÀ-ÿ])[ \\t\\r\\n]*[:\\-]?[ \\t\\r\\n]*(\\d{1,2}(?:[.,]\\d)?)(?![\\d,./-]|[ \\t]*(?:min|minuti|km|metri|persone|notti|stelle|%))", "gi"),
}));
export function extractCategoryScores(text: string, source?: string | null): Record<string, number> {
  const scale = ["booking", "booking.com", "email", ""].includes((source || "Booking").trim().toLowerCase()) ? 10 : 5;
  const cleaned = text.replace(DATE_LIKE, " ");
  const scores: Record<string, number> = {};
  for (const { name, re } of CATEGORY_SCORE) {
    if (name in scores) continue;
    re.lastIndex = 0;
    for (const m of cleaned.matchAll(re)) {
      const v = Number(m[1].replace(",", "."));
      if (v >= 0 && v <= scale) { scores[name] = v; break; }
    }
  }
  return scores;
}

// ---- classificazione (classify_review_text) ----
const KEYWORDS_NORM = Object.entries(CATEGORY_KEYWORDS).map(([cat, kws]) => [cat, kws.map(normalizeText)] as [string, string[]]);
const CLAUSE_SPLIT = /\s*(?:[,;]|\bma\b|\bperò\b|\bnonostante\b|\btuttavia\b|\bunico\s+neo\b|(?=\bcomunque\b))\s*/i;
export function classifyText(text: string): Tag[] {
  const found: Tag[] = [];
  const sentences = text.split(/(?<=[.!?])\s+|\n+/).map((s) => s.trim()).filter(Boolean);
  if (!sentences.length) sentences.push(text);
  let emoji: "positive" | "negative" | null = null;
  for (const raw of sentences) {
    const clauses = raw.split(CLAUSE_SPLIT).map((s) => (s || "").trim()).filter(Boolean);
    if (!clauses.length) clauses.push(raw);
    const active = new Set<string>();
    for (const clause of clauses) {
      if (/^comunque\b/i.test(clause)) emoji = null;
      const sentence = normalizeText(clause);
      const tokens = sentence.match(/[a-zà-ÿ]+/g) || [];
      let positive = 0, negative = 0;
      tokens.forEach((token, i) => {
        const inverted = tokens.slice(Math.max(0, i - NEGATION_WINDOW), i).some((t) => NEGATIONS.has(t));
        if (POSITIVE_WORDS.has(token)) { if (inverted) negative++; else positive++; }
        else if (NEGATIVE_WORDS.has(token)) { if (inverted) positive++; else negative++; }
      });
      if (/\bpochi\s+passi\b/.test(sentence)) { negative = Math.max(0, negative - 1); positive++; }
      if (/\bnon\b[^.!?\n]{0,60}\b(?:molti|molte|molto|molta|aveva|avevano|c['’]era|c['’]erano)\b/.test(sentence)) negative++;
      if (/\b(?:al|sotto)\s+di\s+sotto\b|\bsotto\s+le\s+aspettative\b/.test(sentence)) negative++;
      if (/[😊🙂😃]/u.test(clause)) { emoji = "positive"; positive++; }
      if (/[☹🙁😞😡]/u.test(clause)) { emoji = "negative"; negative++; }
      if (emoji === "positive" && !positive && !negative) positive++;
      else if (emoji === "negative" && !positive && !negative) negative++;
      const polarity = negative > positive ? "negative" : positive > negative ? "positive" : "neutral";
      if (polarity === "neutral") continue;
      for (const [category, kws] of KEYWORDS_NORM) {
        let hits = kws.filter((k) => sentence.includes(k)).length;
        if (hits) active.add(category);
        else if (active.has(category)) hits = 1;
        if (hits) found.push({ category, polarity, confidence: Math.min(1, 0.65 + 0.08 * hits) });
      }
    }
  }
  const unique = new Map<string, Tag>();
  for (const t of found) {
    const key = `${t.category}|${t.polarity}`;
    const prev = unique.get(key);
    if (!prev || t.confidence > prev.confidence) unique.set(key, t);
  }
  return [...unique.values()];
}

// ---- payload per ogni recensione centrale ----
const hotelName = (code: string) => HOTELS.find((h) => h.code === code)?.name || code;
export function toPayload(r: CentralReview): ReviewPayload {
  const source = normalizedSource(r.source);
  const rating = normalizedRating(r.rating, source);
  const text = cleanReviewText(r.text || "");
  const room = validRoom(r.room_code);
  const date = String(r.review_date || "").slice(0, 10);
  const key = [r.hotel_code.toLowerCase(), date, (room || "").toLowerCase(), (source || "").toLowerCase(), rating === null ? "" : rating.toFixed(4), normalizeText(text)].join("|");
  let valid = Boolean(text) && source !== null;
  let reason: string | null = valid ? null : "testo o fonte non riconosciuti";
  if (r.rating != null && rating === null) { valid = false; reason = "voto fuori scala o non leggibile"; }
  return {
    id: `cache:${r.sync_uuid}`, hotel: hotelName(r.hotel_code), hotel_code: r.hotel_code, room, author: r.author, source, rating, date, text,
    scores: extractCategoryScores(r.text || "", source), tags: text ? classifyText(text) : [], normalized_key: key, valid, excluded_reason: reason,
    raw_review_id: 0, origin: "supabase",
  };
}

export type Processed = { all: ReviewPayload[]; valid: ReviewPayload[]; stats: Record<string, number> };
export function process(raw: CentralReview[]): Processed {
  const all = raw.map(toPayload).sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  const seen = new Set<string>();
  const valid: ReviewPayload[] = [];
  let excluded = 0, duplicates = 0, withoutRoom = 0, withoutRating = 0, votes = 0;
  for (const p of all) {
    if (!p.valid) { excluded++; continue; }
    if (seen.has(p.normalized_key)) { duplicates++; continue; }
    seen.add(p.normalized_key);
    valid.push(p);
    if (p.rating !== null) votes++; else withoutRating++;
    if (!p.room) withoutRoom++;
  }
  return {
    all, valid,
    stats: { raw: raw.length, expanded: all.length, normalized: valid.length, valid: valid.length, excluded, duplicates, valid_votes: votes, without_room: withoutRoom, without_rating: withoutRating },
  };
}

export const forHotel = (items: ReviewPayload[], hotelCode?: string | null) => (hotelCode ? items.filter((r) => r.hotel_code === hotelCode) : items);

// ---- ranking (review_rankings) ----
export function rankings(items: ReviewPayload[], limit = 5) {
  const rooms = new Map<string, { room: string; hotel: string; n: number; sum: number; rated: number }>();
  for (const r of items) {
    if (!r.room) continue;
    const key = `${r.hotel_code}|${r.room}`;
    const it = rooms.get(key) || { room: r.room, hotel: r.hotel, n: 0, sum: 0, rated: 0 };
    it.n++;
    if (r.rating !== null) { it.sum += r.rating; it.rated++; }
    rooms.set(key, it);
  }
  const scoredRooms = [...rooms.values()].map((x) => {
    const rating = x.rated ? x.sum / x.rated : 0;
    const confidence = Math.min(1, x.n / 10);
    return { room: x.room, hotel: x.hotel, reviews: x.n, rating: Math.round(rating * 100) / 100, score: Math.round(rating * (0.6 + 0.4 * confidence) * 1000) / 1000 };
  }).sort((a, b) => b.score - a.score);
  const counts = new Map<string, { positive: number; negative: number }>();
  for (const r of items) for (const t of r.tags) {
    const c = counts.get(t.category) || { positive: 0, negative: 0 };
    c[t.polarity]++;
    counts.set(t.category, c);
  }
  const services = [...counts.entries()].map(([service, c]) => {
    const total = c.positive + c.negative;
    return { service, ...c, mentions: total, score: total ? Math.round(((c.positive - c.negative) / total) * 1000) / 1000 : 0 };
  }).sort((a, b) => b.score - a.score);
  return {
    best_rooms: scoredRooms.slice(0, limit), worst_rooms: scoredRooms.slice(-limit).reverse(),
    best_services: services.slice(0, limit), worst_services: services.slice(-limit).reverse(),
  };
}

// ---- andamento camere (room_rating_timeline) ----
const ROOM_CATEGORIES = new Set(["Camere / Arredi", "Letti", "Pulizia"]);
function roomScore(r: ReviewPayload): [number | null, number, number] {
  const tags = r.tags.filter((t) => ROOM_CATEGORIES.has(t.category));
  const positive = tags.filter((t) => t.polarity !== "negative").length;
  const negative = tags.length - positive;
  const scale = ["google", "tripadvisor"].includes((r.source || "").trim().toLowerCase()) ? 2 : 1;
  let score: number | null = r.rating !== null ? r.rating * scale : null;
  if (positive || negative) {
    const tagScore = (positive / (positive + negative)) * 10;
    score = score === null ? tagScore : (score * 2 + tagScore) / 3;
  }
  return [score === null ? null : Math.round(score * 100) / 100, positive, negative];
}
const dayBefore = (iso: string) => new Date(Date.parse(iso) - 86400000).toISOString().slice(0, 10);
export function roomTimeline(items: ReviewPayload[]) {
  const groups = new Map<string, ReviewPayload[]>();
  for (const r of items) if (r.room) { const k = `${r.hotel_code}|${r.room}`; (groups.get(k) || groups.set(k, []).get(k)!).push(r); }
  const result: any[] = [];
  for (const reviews of groups.values()) {
    reviews.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    const periods: any[] = [];
    let window: number[] = [];
    for (const r of reviews) {
      const [score, positive, negative] = roomScore(r);
      if (score === null) continue;
      window = [...window, score].slice(-3);
      const weights = window.map((_, i) => i + 1);
      const dynamic = Math.round((window.reduce((s, v, i) => s + v * weights[i], 0) / weights.reduce((a, b) => a + b, 0)) * 100) / 100;
      const status = dynamic < 6 ? "attenzione" : dynamic < 7.5 ? "monitorare" : "ok";
      const causes = [...new Set(r.tags.filter((t) => t.polarity === "negative" && ROOM_CATEGORIES.has(t.category)).map((t) => t.category))].sort();
      const prev = periods[periods.length - 1];
      if (!prev || prev.status !== status || Math.abs(dynamic - prev.score) >= 1) {
        if (prev) prev.to = dayBefore(r.date);
        periods.push({ from: r.date, to: null, score: dynamic, status, reviews: 1, positive, negative, causes });
      } else {
        prev.reviews++; prev.positive += positive; prev.negative += negative;
        prev.causes = [...new Set([...prev.causes, ...causes])].sort();
      }
    }
    if (periods.length) {
      const last = periods[periods.length - 1];
      result.push({ hotel: reviews[0].hotel, hotel_code: reviews[0].hotel_code, room: reviews[0].room, current_score: last.score, current_status: last.status, periods });
    }
  }
  return result.sort((a, b) => a.current_score - b.current_score || a.hotel.localeCompare(b.hotel) || String(a.room).localeCompare(String(b.room)));
}
