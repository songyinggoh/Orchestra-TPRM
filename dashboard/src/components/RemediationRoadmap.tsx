import React, { useState } from "react";

export interface RemediationItem {
  finding_id: string;
  action: string;
  owner: "vendor" | "buyer" | "both";
  priority: "P0" | "P1" | "P2";
  leverage: string;
  est_effort_days: number | null;
}

export interface RemediationPlan {
  items: RemediationItem[];
  horizon_days: number;
  summary: string;
}

const PRIORITY_BG: Record<RemediationItem["priority"], string> = {
  P0: "#2a1717",
  P1: "#2a2317",
  P2: "#171f2a",
};

const PRIORITY_FG: Record<RemediationItem["priority"], string> = {
  P0: "#f87171",
  P1: "#fbbf24",
  P2: "#93c5fd",
};

export const RemediationRoadmap: React.FC<{ plan: RemediationPlan | null }> = ({ plan }) => {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (!plan) return null;

  const groupedItems = (["P0", "P1", "P2"] as const).map((p) => ({
    priority: p,
    items: plan.items.filter((i) => i.priority === p),
  }));

  const isEmpty = plan.items.length === 0;

  return (
    <section
      style={{
        padding: "24px",
        background: "#0f1115",
        border: "1px solid #1f2329",
        borderRadius: "8px",
        marginBottom: "16px",
        fontFamily: "'Roboto Mono', monospace",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "12px" }}>
        <h2 style={{ margin: 0, color: "#e6e9ef", fontSize: "18px", fontWeight: 600 }}>
          Remediation Roadmap
        </h2>
        {!isEmpty && (
          <span style={{ color: "#7a8390", fontSize: "12px" }}>
            Horizon: {plan.horizon_days}d
          </span>
        )}
      </div>
      <p style={{ color: "#c4cad4", marginTop: 0, fontStyle: "italic" }}>{plan.summary}</p>

      {!isEmpty && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px", marginTop: "16px" }}>
          {groupedItems.map((group) => (
            <div key={group.priority}>
              <div
                style={{
                  background: PRIORITY_BG[group.priority],
                  color: PRIORITY_FG[group.priority],
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 600,
                  letterSpacing: "0.05em",
                  marginBottom: "8px",
                  display: "inline-block",
                }}
              >
                {group.priority}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {group.items.length === 0 ? (
                  <div style={{ color: "#7a8390", fontSize: "12px", fontStyle: "italic" }}>—</div>
                ) : (
                  group.items.map((item) => (
                    <div
                      key={item.finding_id}
                      onClick={() => setExpanded(expanded === item.finding_id ? null : item.finding_id)}
                      style={{
                        padding: "12px",
                        background: "#15181e",
                        border: "1px solid #1f2329",
                        borderRadius: "4px",
                        cursor: "pointer",
                        fontSize: "13px",
                        color: "#e6e9ef",
                      }}
                    >
                      <div style={{ fontWeight: 500 }}>{item.action}</div>
                      <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
                        <span
                          style={{
                            padding: "2px 6px",
                            background: "#1f2329",
                            borderRadius: "2px",
                            fontSize: "10px",
                            color: "#c4cad4",
                          }}
                        >
                          {item.owner}
                        </span>
                        {item.est_effort_days != null && (
                          <span style={{ fontSize: "10px", color: "#7a8390" }}>
                            ~{item.est_effort_days}d
                          </span>
                        )}
                      </div>
                      {expanded === item.finding_id && (
                        <div style={{ marginTop: "8px", fontSize: "11px", color: "#c4cad4" }}>
                          <span style={{ color: "#7a8390" }}>Leverage:</span> {item.leverage}
                          <br />
                          <span style={{ color: "#7a8390" }}>Finding ID:</span> {item.finding_id.slice(0, 8)}…
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};
