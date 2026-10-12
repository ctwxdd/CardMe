import type { TableClient } from "@azure/data-tables";

const websiteEvents = ["page_view", "download_click", "web_coffee_click"] as const;
const counters = ["full_size", "previews", "thumbnails", "review"] as const;
const keys = ["schema_version", "event_id", "event", "app_version", "mode", ...counters, "unrecovered"];
export type CardMeUsage = { schema_version: 1 | 2; event_id: string; event: "app_open" | "rescue_complete" | "coffee_click" | "scan_finished" | (typeof websiteEvents)[number]; app_version: string; mode: "none" | "normal" | "deep"; full_size: number; previews: number; thumbnails: number; review: number; unrecovered: number | null; scan_total?: number; scan_flagged?: number; scan_result?: "completed" | "failed" | "cancelled" };
const count = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0 && v <= 1000000;
export function parseCardMeUsage(input: unknown): CardMeUsage | null {
  if (!input || typeof input !== "object" || Array.isArray(input)) return null;
  const v = input as Record<string, unknown>;
  const scan = v.schema_version === 2;
  const allowedKeys = scan ? [...keys, "scan_total", "scan_flagged", "scan_result"] : keys;
  if (Object.keys(v).length !== allowedKeys.length || !Object.keys(v).every(k => allowedKeys.includes(k)) ||
      (v.schema_version !== 1 && !scan) || typeof v.event_id !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu.test(v.event_id) ||
      typeof v.app_version !== "string" || !/^[0-9A-Za-z][0-9A-Za-z.+-]{0,31}$/u.test(v.app_version) ||
      typeof v.event !== "string" || !["app_open", "rescue_complete", "coffee_click", "scan_finished", ...websiteEvents].includes(v.event) ||
      typeof v.mode !== "string" || !["none", "normal", "deep"].includes(v.mode) || !counters.every(k => count(v[k])) ||
      (v.unrecovered !== null && !count(v.unrecovered))) return null;
  if (scan !== (v.event === "scan_finished")) return null;
  if (scan) {
    if (v.mode !== "normal" || !count(v.scan_total) || !count(v.scan_flagged) || v.scan_flagged > v.scan_total ||
        typeof v.scan_result !== "string" || !["completed", "failed", "cancelled"].includes(v.scan_result) ||
        counters.some(k => v[k] !== 0) || v.unrecovered !== null) return null;
  }
  if (websiteEvents.includes(v.event as (typeof websiteEvents)[number]) && v.app_version !== "web") return null;
  if (v.event === "rescue_complete") {
    if (v.mode === "none" || (v.mode === "deep" ? v.unrecovered !== null : v.unrecovered === null)) return null;
  } else if (!scan && (v.mode !== "none" || counters.some(k => v[k] !== 0) || v.unrecovered !== null)) return null;
  return { ...v, event_id: v.event_id.toLowerCase() } as CardMeUsage;
}

export class CardMeUsageStore {
  private table: TableClient;
  constructor(table: TableClient) { this.table = table; }
  async save(row: CardMeUsage, now: Date) {
    // One random ID per report deduplicates retries without identifying an installation.
    try { await this.table.createEntity({ ...row, unrecovered: row.unrecovered ?? -1, partitionKey: row.event_id[0], rowKey: row.event_id, receivedAt: now.toISOString() }); }
    catch (error) { if ((error as { statusCode?: number }).statusCode !== 409) throw error; }
  }
  async summary(from: string, to: string, version?: string) {
    const result = { appOpens: 0, rescues: 0, coffeeClicks: 0, fullSize: 0, previews: 0, thumbnails: 0, review: 0, unrecovered: 0, unknownUnrecovered: 0, normal: 0, deep: 0, pageViews: 0, downloadClicks: 0, webCoffeeClicks: 0, scanReports: 0, scansCompleted: 0, scansFailed: 0, scansCancelled: 0, totalScanned: 0, scanFlagged: 0, daily: [] as { day: string; scanReports: number; totalScanned: number; scanFlagged: number; scansFailed: number; pageViews: number; downloadClicks: number; appOpens: number; rescues: number; fullSize: number; coffeeClicks: number; webCoffeeClicks: number }[] };
    const days = new Map<string, (typeof result.daily)[number]>();
    let scanned = 0;
    for (const bucket of "0123456789abcdef") {
      const filter = `PartitionKey eq '${bucket}' and receivedAt ge '${from}' and receivedAt lt '${to}'`;
      for await (const row of this.table.listEntities<CardMeUsage>({ queryOptions: { filter } })) {
        if (++scanned > 200000) throw new Error("cardme_summary_limit");
        const website = websiteEvents.includes(row.event as (typeof websiteEvents)[number]);
        if (version && !website && row.app_version !== version) continue;
        const day = String((row as unknown as { receivedAt: string }).receivedAt).slice(0, 10);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) continue;
        let daily = days.get(day);
        if (!daily) { daily = { day, scanReports: 0, totalScanned: 0, scanFlagged: 0, scansFailed: 0, pageViews: 0, downloadClicks: 0, appOpens: 0, rescues: 0, fullSize: 0, coffeeClicks: 0, webCoffeeClicks: 0 }; days.set(day, daily); }
        if (row.event === "scan_finished") {
          daily.scanReports++; result.scanReports++; result.totalScanned += row.scan_total ?? 0; result.scanFlagged += row.scan_flagged ?? 0;
          daily.totalScanned += row.scan_total ?? 0; daily.scanFlagged += row.scan_flagged ?? 0;
          if (row.scan_result === "completed") result.scansCompleted++;
          if (row.scan_result === "cancelled") result.scansCancelled++;
          if (row.scan_result === "failed") { result.scansFailed++; daily.scansFailed++; }
        }
        if (row.event === "page_view") { result.pageViews++; daily.pageViews++; }
        if (row.event === "download_click") { result.downloadClicks++; daily.downloadClicks++; }
        if (row.event === "web_coffee_click") { result.webCoffeeClicks++; daily.webCoffeeClicks++; }
        if (row.event === "app_open") daily.appOpens++;
        if (row.event === "coffee_click") daily.coffeeClicks++;
        if (row.event === "app_open") result.appOpens++;
        if (row.event === "coffee_click") result.coffeeClicks++;
        if (row.event === "rescue_complete") {
          daily.rescues++; daily.fullSize += row.full_size;
          result.rescues++; result[row.mode === "deep" ? "deep" : "normal"]++;
          result.fullSize += row.full_size; result.previews += row.previews; result.thumbnails += row.thumbnails; result.review += row.review;
          if (row.unrecovered === -1) result.unknownUnrecovered++; else result.unrecovered += row.unrecovered ?? 0;
        }
      }
    }
    result.daily = [...days.values()].sort((a, b) => a.day.localeCompare(b.day));
    return result;
  }
  async prune(before: Date, limit = 5000) {
    let removed = 0;
    for (const bucket of "0123456789abcdef") {
      const filter = `PartitionKey eq '${bucket}' and receivedAt lt '${before.toISOString()}'`;
      for await (const row of this.table.listEntities<{partitionKey: string; rowKey: string}>({ queryOptions: { filter } })) {
        await this.table.deleteEntity(row.partitionKey, row.rowKey);
        if (++removed >= limit) return removed;
      }
    }
    return removed;
  }
}
