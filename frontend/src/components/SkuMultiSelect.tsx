"use client";

import { useMemo, useRef, useState } from "react";
import type { ProductItem } from "@/lib/types";

const MAX_SELECTED = 10;

interface Props {
  products: ProductItem[];
  selected: string[];
  onChange: (skus: string[]) => void;
  loading?: boolean;
}

/** Searchable multi-select combobox for 1–10 SKUs, with chips. */
export function SkuMultiSelect({ products, selected, onChange, loading }: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const options = useMemo(() => {
    const q = query.trim().toLowerCase();
    return products
      .filter(
        (p) =>
          !selected.includes(p.sku) &&
          (!q ||
            p.sku.toLowerCase().includes(q) ||
            p.product_name.toLowerCase().includes(q)),
      )
      .slice(0, 20);
  }, [products, selected, query]);

  const add = (sku: string) => {
    if (selected.length >= MAX_SELECTED || selected.includes(sku)) return;
    onChange([...selected, sku]);
    setQuery("");
    setActive(0);
    inputRef.current?.focus();
  };

  const remove = (sku: string) => onChange(selected.filter((s) => s !== sku));

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, options.length - 1));
      setOpen(true);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && open && options[active]) {
      e.preventDefault();
      add(options[active].sku);
    } else if (e.key === "Escape") {
      setOpen(false);
    } else if (e.key === "Backspace" && !query && selected.length) {
      remove(selected[selected.length - 1]);
    }
  };

  return (
    <div className="relative">
      <div
        className="flex flex-wrap items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-2 py-1.5 focus-within:border-[var(--c-series-1)]"
        onClick={() => inputRef.current?.focus()}
      >
        {selected.map((sku) => (
          <span
            key={sku}
            className="flex items-center gap-1 rounded bg-blue-50 px-2 py-0.5 text-sm text-blue-900"
          >
            {sku}
            <button
              type="button"
              aria-label={`Remove ${sku}`}
              onClick={(e) => {
                e.stopPropagation();
                remove(sku);
              }}
              className="text-blue-400 hover:text-blue-700"
            >
              ×
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded={open}
          aria-label="Search and select products"
          className="min-w-40 flex-1 bg-transparent px-1 py-0.5 text-sm outline-none"
          placeholder={
            selected.length === 0 ? "Select products to forecast…" : "Add another…"
          }
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            setActive(0);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={onKeyDown}
        />
        <span className="text-xs text-gray-400">
          {selected.length}/{MAX_SELECTED}
        </span>
      </div>

      {open && (
        <ul
          role="listbox"
          className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-gray-200 bg-white shadow-lg"
        >
          {loading && <li className="px-3 py-2 text-sm text-gray-400">Loading…</li>}
          {!loading && options.length === 0 && (
            <li className="px-3 py-2 text-sm text-gray-400">No matching products</li>
          )}
          {options.map((p, i) => (
            <li
              key={p.sku}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                add(p.sku);
              }}
              onMouseEnter={() => setActive(i)}
              className={`flex cursor-pointer items-center justify-between px-3 py-2 text-sm ${
                i === active ? "bg-blue-50" : ""
              }`}
            >
              <span>
                <span className="font-medium">{p.sku}</span>{" "}
                <span className="text-gray-500">{p.product_name}</span>
              </span>
              {p.has_forecast && (
                <span className="text-xs text-green-600">forecast ready</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
