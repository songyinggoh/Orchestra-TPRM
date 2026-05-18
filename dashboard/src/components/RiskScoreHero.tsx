import React from "react";

export interface RiskDriver {
  dimension: string;
  finding_id: string;
  severity: "low" | "medium" | "high" | "critical";
  one_liner: string;
}

export interface RiskScore {
  overall: number;
  verdict: "green" | "amber" | "red";
  dimensions: Record<string, number>;
  top_risk_drivers: RiskDriver[];
  explanation: string;
}

const VERDICT_STYLES: Record<RiskScore["verdict"], { bg: string; fg: string; label: string }> = {
  green: { bg: "#1c2a1f", fg: "#86efac", label: "GREEN" },
  amber: { bg: "#2a2317", fg: "#fbbf24", label: "AMBER" },
  red:   { bg: "#2a1717", fg: "#f87171", label: "RED" },
};

export const RiskScoreHero: React.FC<{ score: RiskScore | null }> = ({ score }) => {
  if (!score) return null;
  const v = VERDICT_STYLES[score.verdict];
  const sortedDims = Object.entries(score.dimensions).sort(([, a], [, b]) => b - a);

  return (
    <section
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(180px, auto) 1fr",
        gap: "24px",
        padding: "24px",
        background: "#0f1115",
        border: "1px solid #1f2329",
        borderRadius: "8px",
        marginBottom: "16px",
        fontFamily: "'Roboto Mono', monospace",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: "72px", lineHeight: 1, fontWeight: 700, color: "#e6e9ef" }}>
          {score.overall}
        </div>
        <div style={{ fontSize: "11px", color: "#7a8390", marginTop: "4px" }}>RISK SCORE</div>
        <div
          style={{
            marginTop: "12px",
            padding: "4px 12px",
            borderRadius: "999px",
            background: v.bg,
            color: v.fg,
            fontSize: "12px",
            fontWeight: 600,
            letterSpacing: "0.05em",
          }}
        >
          {v.label}
        </div>
      </div>
      <div>
        <p style={{ color: "#c4cad4", marginTop: 0, fontStyle: "italic" }}>{score.explanation}</p>

        {score.top_risk_drivers.length > 0 && (
          <>
            <div style={{ color: "#7a8390", fontSize: "11px", margin: "12px 0 6px", letterSpacing: "0.05em" }}>
              TOP RISK DRIVERS
            </div>
            <ul style={{ listStyle: "none", padding: 0, margin: 0, color: "#e6e9ef" }}>
              {score.top_risk_drivers.map((d) => (
                <li key={d.finding_id} style={{ marginBottom: "6px", fontSize: "13px" }}>
                  <span style={{ color: "#7a8390" }}>[{d.dimension}]</span>{" "}
                  <span style={{ color: VERDICT_STYLES[d.severity === "critical" || d.severity === "high" ? "red" : d.severity === "medium" ? "amber" : "green"].fg }}>
                    ({d.severity})
                  </span>{" "}
                  {d.one_liner}
                </li>
              ))}
            </ul>
          </>
        )}

        <div style={{ color: "#7a8390", fontSize: "11px", margin: "16px 0 6px", letterSpacing: "0.05em" }}>
          PER-DIMENSION
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          {sortedDims.map(([dim, val]) => (
            <div key={dim} style={{ display: "grid", gridTemplateColumns: "120px 1fr 40px", alignItems: "center", gap: "8px", fontSize: "12px", color: "#c4cad4" }}>
              <span>{dim}</span>
              <div style={{ height: "8px", background: "#1f2329", borderRadius: "2px", overflow: "hidden" }}>
                <div
                  style={{
                    width: `${val}%`,
                    height: "100%",
                    background: val >= 70 ? VERDICT_STYLES.red.fg : val >= 31 ? VERDICT_STYLES.amber.fg : VERDICT_STYLES.green.fg,
                    transition: "width 300ms ease",
                  }}
                />
              </div>
              <span style={{ textAlign: "right", color: "#7a8390" }}>{val}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
