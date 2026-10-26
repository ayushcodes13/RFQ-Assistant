"use client";

import React, { useEffect, useState } from "react";
import { CatalogItem } from "@/types";
import { importCatalogCSV, listCatalog } from "@/services/api";

export function CatalogView() {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [uploading, setUploading] = useState(false);
  const [importSummary, setImportSummary] = useState<any>(null);

  const loadItems = async () => {
    setLoading(true);
    try {
      const data = await listCatalog();
      setItems(data);
    } catch (e: any) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadItems();
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || !e.target.files[0]) return;
    setUploading(true);
    try {
      const res = await importCatalogCSV(e.target.files[0]);
      setImportSummary(res.summary);
      loadItems();
    } catch (err: any) {
      alert(`Import failed: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const filtered = items.filter(
    (i) =>
      i.internal_sku.toLowerCase().includes(searchTerm.toLowerCase()) ||
      i.manufacturer.toLowerCase().includes(searchTerm.toLowerCase()) ||
      i.manufacturer_part_number.toLowerCase().includes(searchTerm.toLowerCase()) ||
      i.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // Group by MPN to detect catalog collisions
  const mpnCounts: { [mpn: string]: string[] } = {};
  items.forEach((i) => {
    const k = i.manufacturer_part_number.toUpperCase();
    if (!mpnCounts[k]) mpnCounts[k] = [];
    if (!mpnCounts[k].includes(i.manufacturer)) mpnCounts[k].push(i.manufacturer);
  });
  const collisions = Object.entries(mpnCounts).filter(([_, oems]) => oems.length > 1);

  return (
    <div className="catalog-container">
      <div className="catalog-header">
        <div>
          <h1 className="page-title">Authorized Item Master Catalog</h1>
          <p className="page-subtitle">
            Ground-truth catalog containing authorized distributor SKUs and exact manufacturer part numbers.
          </p>
        </div>

        <div className="header-actions">
          <label className="import-btn">
            {uploading ? "Importing CSV..." : "📁 Import Catalog CSV"}
            <input
              type="file"
              accept=".csv"
              className="hidden-file-input"
              disabled={uploading}
              onChange={handleFileUpload}
            />
          </label>
        </div>
      </div>

      {importSummary && (
        <div className="summary-alert">
          ✓ Imported {importSummary.imported} items. Found {importSummary.duplicates} duplicates,{" "}
          {importSummary.collisions} cross-brand collisions. Total catalog items:{" "}
          {importSummary.total_catalog_size}.
        </div>
      )}

      {collisions.length > 0 && (
        <div className="collision-banner">
          <div className="banner-title font-bold">
            ⚠ Cross-Brand Part Number Collisions Detected ({collisions.length}):
          </div>
          <div className="collision-list">
            {collisions.map(([mpn, oems]) => (
              <span key={mpn} className="collision-tag font-mono">
                {mpn} → {oems.join(" vs ")}
              </span>
            ))}
          </div>
          <div className="banner-note">
            When customer RFQs omit the manufacturer name for these parts, the system flags them for
            mandatory human brand selection instead of guessing.
          </div>
        </div>
      )}

      <div className="search-bar">
        <input
          type="text"
          className="search-input"
          placeholder="Filter catalog by SKU, OEM, part number, or description..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
        <div className="item-count font-mono">{filtered.length} items loaded</div>
      </div>

      <div className="table-card">
        {loading ? (
          <div className="loading">Loading catalog items...</div>
        ) : filtered.length === 0 ? (
          <div className="empty">No catalog items found.</div>
        ) : (
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Internal SKU</th>
                <th>Manufacturer</th>
                <th>Manufacturer Part Number</th>
                <th>Description</th>
                <th className="align-right">List Price</th>
                <th className="align-center">Stock</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={item.internal_sku}>
                  <td className="font-mono font-bold text-accent">{item.internal_sku}</td>
                  <td className="font-bold">{item.manufacturer}</td>
                  <td className="font-mono">{item.manufacturer_part_number}</td>
                  <td className="desc-cell">{item.description}</td>
                  <td className="align-right font-mono">
                    {item.list_price !== null && item.list_price !== undefined
                      ? `$${item.list_price.toFixed(2)}`
                      : "—"}
                  </td>
                  <td className="align-center font-mono">
                    {item.stock_qty !== null && item.stock_qty !== undefined
                      ? item.stock_qty
                      : "—"}
                  </td>
                  <td className="font-muted font-mono">{item.catalog_version || "v1"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <style jsx>{`
        .catalog-container {
          padding: 1.5rem;
          max-width: 1440px;
          margin: 0 auto;
        }
        .catalog-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          margin-bottom: 1.25rem;
        }
        .page-title {
          font-size: 1.3rem;
          font-weight: 700;
          color: var(--text-primary);
        }
        .page-subtitle {
          font-size: 0.85rem;
          color: var(--text-muted);
          margin-top: 0.2rem;
        }
        .import-btn {
          background: var(--accent-primary);
          color: #ffffff;
          padding: 0.5rem 1rem;
          border-radius: 6px;
          font-size: 0.85rem;
          font-weight: 600;
          cursor: pointer;
          display: inline-block;
        }
        .hidden-file-input { display: none; }
        .summary-alert {
          background: #ECFDF5;
          border: 1px solid #A7F3D0;
          color: #065F46;
          padding: 0.65rem 1rem;
          border-radius: 6px;
          font-size: 0.85rem;
          margin-bottom: 1rem;
        }
        .collision-banner {
          background: #FFFBEB;
          border: 1px solid #FDE68A;
          color: #92400E;
          padding: 0.85rem 1rem;
          border-radius: 6px;
          margin-bottom: 1rem;
          font-size: 0.82rem;
        }
        .banner-title {
          margin-bottom: 0.35rem;
        }
        .collision-list {
          display: flex;
          gap: 0.5rem;
          flex-wrap: wrap;
          margin-bottom: 0.35rem;
        }
        .collision-tag {
          background: #FEF3C7;
          border: 1px solid #FCD34D;
          padding: 0.15rem 0.45rem;
          border-radius: 4px;
          font-size: 0.76rem;
        }
        .banner-note {
          color: #B45309;
          font-size: 0.75rem;
        }
        .search-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 1rem;
        }
        .search-input {
          width: 420px;
          padding: 0.5rem 0.85rem;
          border: 1px solid var(--border-medium);
          border-radius: 6px;
          font-size: 0.88rem;
          background: #ffffff;
        }
        .item-count {
          font-size: 0.8rem;
          color: var(--text-muted);
        }
        .table-card {
          background: #ffffff;
          border: 1px solid var(--border-light);
          border-radius: 8px;
          box-shadow: var(--shadow-sm);
          overflow: hidden;
        }
        .catalog-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.85rem;
          text-align: left;
        }
        .catalog-table th {
          background: var(--bg-subtle);
          padding: 0.75rem 1rem;
          font-weight: 600;
          color: var(--text-secondary);
          border-bottom: 1px solid var(--border-light);
        }
        .catalog-table td {
          padding: 0.75rem 1rem;
          border-bottom: 1px solid var(--border-light);
        }
        .desc-cell {
          max-width: 400px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .align-right { text-align: right; }
        .align-center { text-align: center; }
        .font-mono { font-family: var(--font-mono); }
        .font-bold { font-weight: 700; }
        .font-muted { color: var(--text-muted); }
        .text-accent { color: var(--accent-primary); }
        .loading, .empty {
          padding: 3rem;
          text-align: center;
          color: var(--text-muted);
        }
      `}</style>
    </div>
  );
}
