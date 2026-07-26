import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SkuMultiSelect } from "@/components/SkuMultiSelect";
import type { ProductItem } from "@/lib/types";

const PRODUCTS: ProductItem[] = [
  { sku: "MUG-001", product_name: "Ceramic Mug", category: "kitchenware", sales_days: 120, last_sale_date: "2026-07-20", has_forecast: true },
  { sku: "TSH-022", product_name: "Logo Tee", category: "apparel", sales_days: 90, last_sale_date: "2026-07-19", has_forecast: false },
  { sku: "CAB-104", product_name: "USB-C Cable", category: "electronics", sales_days: 200, last_sale_date: "2026-07-21", has_forecast: true },
];

describe("SkuMultiSelect", () => {
  it("renders selected SKUs as chips and removes them", async () => {
    const onChange = vi.fn();
    render(
      <SkuMultiSelect products={PRODUCTS} selected={["MUG-001"]} onChange={onChange} />,
    );
    expect(screen.getByText("MUG-001")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove MUG-001" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("filters options by search query and adds on click", async () => {
    const onChange = vi.fn();
    render(<SkuMultiSelect products={PRODUCTS} selected={[]} onChange={onChange} />);
    const input = screen.getByRole("combobox");
    await userEvent.type(input, "logo");
    expect(screen.getByText("Logo Tee")).toBeInTheDocument();
    expect(screen.queryByText("Ceramic Mug")).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Logo Tee"));
    expect(onChange).toHaveBeenCalledWith(["TSH-022"]);
  });

  it("excludes already-selected SKUs from options", async () => {
    render(
      <SkuMultiSelect products={PRODUCTS} selected={["MUG-001"]} onChange={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("combobox"));
    expect(screen.queryByRole("option", { name: /Ceramic Mug/ })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Logo Tee/ })).toBeInTheDocument();
  });

  it("enforces the 10-SKU cap", () => {
    const onChange = vi.fn();
    const ten = Array.from({ length: 10 }, (_, i) => `SKU-${i}`);
    render(<SkuMultiSelect products={PRODUCTS} selected={ten} onChange={onChange} />);
    expect(screen.getByText("10/10")).toBeInTheDocument();
  });
});
