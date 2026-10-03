"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, Empty, ErrorNote, Input, Label, PageTitle, Pill } from "@/components/ui";
import { createCustomer, createProduct, listCustomers, listProducts, unwrap } from "@/lib/api";
import { money } from "@/lib/format";
import { canEdit, useMe } from "@/lib/hooks";

const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function CatalogPage() {
  const qc = useQueryClient();
  const me = useMe();
  const editable = canEdit(me.data?.role);
  const cur = me.data?.currency ?? "USD";
  const products = useQuery({ queryKey: ["products"], queryFn: () => unwrap(listProducts()) });
  const customers = useQuery({ queryKey: ["customers"], queryFn: () => unwrap(listCustomers()) });
  const [p, setP] = useState({ sku: "", name: "", unit: "tub", unit_price: "", aliases: "" });
  const [c, setC] = useState({ name: "", aliases: "", email: "", payment_terms_days: "30" });

  const addProduct = useMutation({
    mutationFn: () => unwrap(createProduct({ body: { sku: p.sku, name: p.name, unit: p.unit, unit_price: p.unit_price, aliases: split(p.aliases), active: true } })),
    onSuccess: () => { setP({ sku: "", name: "", unit: "tub", unit_price: "", aliases: "" }); qc.invalidateQueries({ queryKey: ["products"] }); },
  });
  const addCustomer = useMutation({
    mutationFn: () => unwrap(createCustomer({ body: { name: c.name, aliases: split(c.aliases), email: c.email || null, payment_terms_days: Number(c.payment_terms_days) } })),
    onSuccess: () => { setC({ name: "", aliases: "", email: "", payment_terms_days: "30" }); qc.invalidateQueries({ queryKey: ["customers"] }); },
  });

  return (
    <>
      <PageTitle title="Catalog" sub="Keel matches what's written on paper to these. Aliases are the shorthand people actually write." />
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3">
          <h2 className="text-sm font-medium uppercase tracking-wide text-muted">Products</h2>
          {products.data?.length === 0 && <Empty title="No products yet" />}
          <Card className="divide-y divide-line">
            {products.data?.map((pr) => (
              <div key={pr.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="font-medium">{pr.name} <span className="num text-xs text-muted">{pr.sku}</span></p>
                  {!!pr.aliases?.length && <p className="truncate text-xs text-muted">written as {pr.aliases.join(", ")}</p>}
                </div>
                <span className="num shrink-0">{money(pr.unit_price, cur)} / {pr.unit}</span>
              </div>
            ))}
          </Card>
          {editable && (
            <form className="grid grid-cols-2 gap-2 rounded-xl border border-dashed border-line p-4" onSubmit={(e) => { e.preventDefault(); addProduct.mutate(); }}>
              <label><Label>SKU</Label><Input id="p_sku" required value={p.sku} onChange={(e) => setP({ ...p, sku: e.target.value })} /></label>
              <label><Label>Name</Label><Input id="p_name" required value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} /></label>
              <label><Label>Unit</Label><Input id="p_unit" value={p.unit} onChange={(e) => setP({ ...p, unit: e.target.value })} /></label>
              <label><Label>Price</Label><Input id="p_price" required inputMode="decimal" value={p.unit_price} onChange={(e) => setP({ ...p, unit_price: e.target.value })} /></label>
              <label className="col-span-2"><Label hint="comma separated">Also written as</Label><Input id="p_aliases" value={p.aliases} onChange={(e) => setP({ ...p, aliases: e.target.value })} /></label>
              <div className="col-span-2"><ErrorNote error={addProduct.error} /></div>
              <Button className="col-span-2" disabled={addProduct.isPending}>Add product</Button>
            </form>
          )}
        </section>
        <section className="space-y-3">
          <h2 className="text-sm font-medium uppercase tracking-wide text-muted">Customers</h2>
          {customers.data?.length === 0 && <Empty title="No customers yet" />}
          <Card className="divide-y divide-line">
            {customers.data?.map((cu) => (
              <div key={cu.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="font-medium">{cu.name}</p>
                  {!!cu.aliases?.length && <p className="truncate text-xs text-muted">written as {cu.aliases.join(", ")}</p>}
                </div>
                <Pill>net {cu.payment_terms_days}</Pill>
              </div>
            ))}
          </Card>
          {editable && (
            <form className="grid grid-cols-2 gap-2 rounded-xl border border-dashed border-line p-4" onSubmit={(e) => { e.preventDefault(); addCustomer.mutate(); }}>
              <label className="col-span-2"><Label>Name</Label><Input id="c_name" required value={c.name} onChange={(e) => setC({ ...c, name: e.target.value })} /></label>
              <label><Label>Email</Label><Input id="c_email" type="email" value={c.email} onChange={(e) => setC({ ...c, email: e.target.value })} /></label>
              <label><Label>Terms (days)</Label><Input id="c_terms" inputMode="numeric" value={c.payment_terms_days} onChange={(e) => setC({ ...c, payment_terms_days: e.target.value })} /></label>
              <label className="col-span-2"><Label hint="comma separated">Also written as</Label><Input id="c_aliases" value={c.aliases} onChange={(e) => setC({ ...c, aliases: e.target.value })} /></label>
              <div className="col-span-2"><ErrorNote error={addCustomer.error} /></div>
              <Button className="col-span-2" disabled={addCustomer.isPending}>Add customer</Button>
            </form>
          )}
        </section>
      </div>
    </>
  );
}
