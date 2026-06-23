import { formatPercent } from "../formatters";

export function Metric({ label, value, tone }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={tone || ""}>{value}</strong>
    </div>
  );
}

export function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <span>{label}</span>
      {payload.map((item) => (
        <b key={item.dataKey} style={{ color: item.color }}>
          {item.name} {formatPercent(item.value)}
        </b>
      ))}
    </div>
  );
}

export function SettingRow({ label, children }) {
  return (
    <label className="setting-row">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function RateInput({ label, value, onChange, note }) {
  return (
    <SettingRow label={label}>
      <div className="rate-control">
        <div className="input-suffix">
          <input
            type="number"
            step="0.001"
            value={(value * 100).toFixed(3)}
            onChange={(event) => onChange(Number(event.target.value) / 100)}
          />
          <span>%</span>
        </div>
        <small>{note}</small>
      </div>
    </SettingRow>
  );
}
