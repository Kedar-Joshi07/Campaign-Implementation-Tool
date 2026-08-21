import { getCachedJSON } from "./api.js";
import { formatCurrency, formatDate, formatNumber, formatPercent } from "./ui.js";

const SVG_NAMESPACE = "http://www.w3.org/2000/svg";

function setVisibility({ loading = false, empty = false, unavailable = false, content = false }) {
  document.querySelector("#historical-overview-loading").hidden = !loading;
  document.querySelector("#historical-overview-empty").hidden = !empty;
  document.querySelector("#historical-overview-unavailable").hidden = !unavailable;
  document.querySelector("#historical-overview-content").hidden = !content;
}

function safeLabel(value) {
  return String(value || "").trim() || "Unknown/Other";
}

function createSvgElement(name, attributes = {}) {
  const element = document.createElementNS(SVG_NAMESPACE, name);
  for (const [attribute, value] of Object.entries(attributes)) {
    element.setAttribute(attribute, String(value));
  }
  return element;
}

function renderMonthlyTrend(rows) {
  const container = document.querySelector("#historical-monthly-chart");
  const dataList = document.querySelector("#historical-monthly-data");
  container.replaceChildren();
  dataList.replaceChildren();

  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "chart-empty-note";
    empty.textContent = "No monthly performance is available.";
    container.append(empty);
    return;
  }

  const width = Math.max(360, rows.length * 40);
  const height = 184;
  const padding = { top: 18, right: 18, bottom: 34, left: 42 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const maxRate = Math.max(
    ...rows.map((row) => Number(row.attributed_purchase_rate) || 0),
    0.01,
  );
  const labelStep = Math.max(1, Math.ceil(rows.length / 6));
  const points = [];

  const svg = createSvgElement("svg", {
    viewBox: `0 0 ${width} ${height}`,
    width,
    height,
    role: "img",
    "aria-labelledby": "historical-monthly-chart-title historical-monthly-chart-description",
  });
  const title = createSvgElement("title", { id: "historical-monthly-chart-title" });
  title.textContent = "Monthly attributed-purchase rate";
  const description = createSvgElement("desc", { id: "historical-monthly-chart-description" });
  description.textContent = `${rows.length} monthly values. A complete text equivalent follows the chart.`;
  svg.append(title, description);

  for (const fraction of [0, 0.5, 1]) {
    const y = padding.top + plotHeight * (1 - fraction);
    svg.append(createSvgElement("line", {
      x1: padding.left,
      x2: width - padding.right,
      y1: y,
      y2: y,
      class: "chart-grid-line",
    }));
    const label = createSvgElement("text", {
      x: padding.left - 8,
      y: y + 4,
      class: "chart-axis-label",
      "text-anchor": "end",
    });
    label.textContent = formatPercent(maxRate * fraction);
    svg.append(label);
  }

  rows.forEach((row, index) => {
    const rate = Number(row.attributed_purchase_rate) || 0;
    const x = rows.length === 1
      ? padding.left + plotWidth / 2
      : padding.left + (plotWidth * index) / (rows.length - 1);
    const y = padding.top + plotHeight * (1 - rate / maxRate);
    points.push(`${x},${y}`);

    if (index % labelStep === 0 || index === rows.length - 1) {
      const label = createSvgElement("text", {
        x,
        y: height - 12,
        class: "chart-axis-label",
        "text-anchor": "middle",
      });
      label.textContent = safeLabel(row.month);
      svg.append(label);
    }

    const item = document.createElement("li");
    item.textContent = `${safeLabel(row.month)}: ${formatPercent(rate)}, ${formatNumber(row.attributed_purchase_count)} attributed purchases from ${formatNumber(row.contacted_count)} contacted observations.`;
    dataList.append(item);
  });

  svg.append(createSvgElement("polyline", {
    points: points.join(" "),
    class: "chart-trend-line",
  }));
  rows.forEach((row, index) => {
    const rate = Number(row.attributed_purchase_rate) || 0;
    const x = rows.length === 1
      ? padding.left + plotWidth / 2
      : padding.left + (plotWidth * index) / (rows.length - 1);
    const y = padding.top + plotHeight * (1 - rate / maxRate);
    svg.append(createSvgElement("circle", {
      cx: x,
      cy: y,
      r: 3.5,
      class: "chart-trend-point",
      tabindex: 0,
      "aria-label": `${safeLabel(row.month)}: ${formatPercent(rate)} attributed-purchase rate`,
    }));
  });
  container.append(svg);
}

function renderPerformanceBars(selector, rows) {
  const list = document.querySelector(selector);
  list.replaceChildren();
  if (!rows.length) {
    const item = document.createElement("li");
    item.className = "chart-empty-note";
    item.textContent = "No breakdown is available.";
    list.append(item);
    return;
  }

  const maxRate = Math.max(
    ...rows.map((row) => Number(row.attributed_purchase_rate) || 0),
    0.01,
  );
  for (const row of rows) {
    const rate = Number(row.attributed_purchase_rate) || 0;
    const labelText = safeLabel(row.label);
    const item = document.createElement("li");
    item.className = "performance-bar-row";

    const heading = document.createElement("div");
    heading.className = "performance-bar-heading";
    const label = document.createElement("span");
    label.className = "performance-bar-label";
    label.textContent = labelText;
    label.title = labelText;
    const value = document.createElement("strong");
    value.textContent = formatPercent(rate);
    heading.append(label, value);

    const track = document.createElement("div");
    track.className = "performance-bar-track";
    const fill = document.createElement("span");
    fill.className = "performance-bar-fill";
    fill.style.width = `${Math.max(2, (rate / maxRate) * 100)}%`;
    fill.setAttribute("aria-hidden", "true");
    track.append(fill);

    const context = document.createElement("small");
    context.textContent = `${formatNumber(row.attributed_purchase_count)} attributed purchases · ${formatNumber(row.observation_count)} observations`;
    item.append(heading, track, context);
    list.append(item);
  }
}

function renderHistoricalOverview(payload) {
  const summary = payload.summary;
  if (!summary || summary.observation_count === 0) {
    setVisibility({ empty: true });
    return;
  }

  document.querySelector("#historical-observation-count").textContent = formatNumber(summary.observation_count);
  document.querySelector("#historical-attributed-rate").textContent = formatPercent(summary.attributed_purchase_rate);
  document.querySelector("#historical-net-sales").textContent = formatCurrency(summary.net_sales_amount);
  document.querySelector("#historical-date-range").textContent = `${formatDate(summary.contact_date_from)} — ${formatDate(summary.contact_date_to)}`;
  renderMonthlyTrend(payload.monthly_trend || []);
  renderPerformanceBars("#historical-channel-chart", payload.channel_performance || []);
  renderPerformanceBars("#historical-category-chart", payload.product_category_performance || []);
  setVisibility({ content: true });
}

export async function loadHistoricalOverview(force = false) {
  setVisibility({ loading: true });
  try {
    const payload = await getCachedJSON("/api/historical/overview", {
      maxAgeMs: 300_000,
      force,
    });
    renderHistoricalOverview(payload);
    return payload;
  } catch (error) {
    setVisibility({ unavailable: true });
    throw error;
  }
}
