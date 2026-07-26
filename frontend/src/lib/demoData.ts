/** Browser-side synthetic sales generator.
 *
 * Produces a realistic multi-SKU daily sales CSV (seasonality, weekly pattern,
 * trend, noise, promo spikes) and uploads it through the normal CSV path —
 * so demo users exercise the exact same pipeline as real users.
 */
const DEMO_PRODUCTS: { sku: string; name: string; base: number }[] = [
  { sku: "MUG-001", name: "Ceramic Mug", base: 30 },
  { sku: "TSH-022", name: "Logo Tee", base: 18 },
  { sku: "CAB-104", name: "USB-C Cable 2m", base: 45 },
  { sku: "NOT-310", name: "A5 Notebook", base: 22 },
  { sku: "BOT-007", name: "Steel Water Bottle", base: 14 },
];

function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function generateDemoCsv(days = 400): File {
  const rand = mulberry32(42);
  const today = new Date();
  const lines: string[] = ["date,sku,product_name,quantity,revenue,price,promo_flag"];

  for (const p of DEMO_PRODUCTS) {
    const price = 9 + rand() * 30;
    for (let d = days; d >= 1; d--) {
      const date = new Date(today);
      date.setDate(date.getDate() - d);
      const dayOfYear = Math.floor(
        (date.getTime() - new Date(date.getFullYear(), 0, 0).getTime()) / 86400000,
      );
      const seasonal = 1 + 0.35 * Math.sin((dayOfYear / 365) * 2 * Math.PI);
      const weekly = date.getDay() === 0 || date.getDay() === 6 ? 1.25 : 1.0;
      const trend = 1 + (days - d) / (days * 4);
      const promo = rand() < 0.06;
      const noise = 0.7 + rand() * 0.6;
      const qty = Math.max(
        0,
        Math.round(p.base * seasonal * weekly * trend * noise * (promo ? 1.8 : 1)),
      );
      const revenue = (qty * price * (promo ? 0.85 : 1)).toFixed(2);
      lines.push(
        `${date.toISOString().slice(0, 10)},${p.sku},${p.name},${qty},${revenue},${price.toFixed(2)},${promo}`,
      );
    }
  }
  return new File([lines.join("\n")], "demo-sales.csv", { type: "text/csv" });
}
