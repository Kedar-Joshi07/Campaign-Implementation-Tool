const compactNumberFormatter = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const exactIntegerFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});
const percentFormatter = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const dateFormatter = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
});
const dateTimeFormatter = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

const statusClasses = [
  "is-checking", "is-ready", "is-warning", "is-error", "is-not-loaded",
  "is-completed", "is-running", "is-failed", "is-neutral",
];

const statusPresentation = {
  CHECKING: ["Checking", "is-checking"],
  OK: ["Ready", "is-ready"],
  WARNING: ["Warning", "is-warning"],
  ERROR: ["Error", "is-error"],
  NOT_LOADED: ["Not loaded", "is-not-loaded"],
  COMPLETED: ["Completed", "is-completed"],
  RUNNING: ["Running", "is-running"],
  FAILED: ["Failed", "is-failed"],
};

const decimalFormatterCache = new Map();

function getDecimalFormatter(minimumFractionDigits, maximumFractionDigits) {
  const key = `${minimumFractionDigits}:${maximumFractionDigits}`;
  if (!decimalFormatterCache.has(key)) {
    decimalFormatterCache.set(key, new Intl.NumberFormat("en-US", {
      minimumFractionDigits,
      maximumFractionDigits,
    }));
  }
  return decimalFormatterCache.get(key);
}

function finiteNumber(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : null;
}

export function formatId(value) {
  const numericValue = finiteNumber(value);
  if (numericValue === null || !Number.isInteger(numericValue)) {
    return "—";
  }
  return exactIntegerFormatter.format(numericValue);
}

export function formatExactInteger(value) {
  const numericValue = finiteNumber(value);
  if (numericValue === null || !Number.isInteger(numericValue)) {
    return "—";
  }
  return exactIntegerFormatter.format(numericValue);
}

export function formatCompactNumber(value) {
  const numericValue = finiteNumber(value);
  if (numericValue === null) {
    return "—";
  }

  const absoluteValue = Math.abs(numericValue);
  const sign = numericValue < 0 ? "-" : "";
  if (absoluteValue >= 1_000_000_000) {
    return `${sign}${compactNumberFormatter.format(absoluteValue / 1_000_000_000)}B`;
  }
  if (absoluteValue >= 1_000_000) {
    return `${sign}${compactNumberFormatter.format(absoluteValue / 1_000_000)}M`;
  }
  if (absoluteValue >= 1_000) {
    return `${sign}${compactNumberFormatter.format(absoluteValue / 1_000)}K`;
  }
  return `${sign}${compactNumberFormatter.format(absoluteValue)}`;
}

export function formatDecimal(value, minimumFractionDigits = 2, maximumFractionDigits = 2) {
  const numericValue = finiteNumber(value);
  if (numericValue === null) {
    return "—";
  }
  return getDecimalFormatter(minimumFractionDigits, maximumFractionDigits).format(numericValue);
}

export function formatNumber(value) {
  return formatCompactNumber(value);
}

export function formatPercent(value) {
  return Number.isFinite(Number(value)) ? percentFormatter.format(Number(value)) : "—";
}

export function formatCurrency(value) {
  const numericValue = finiteNumber(value);
  if (numericValue === null) {
    return "—";
  }
  const sign = numericValue < 0 ? "-" : "";
  return `${sign}$${formatCompactNumber(Math.abs(numericValue))}`;
}

export function formatDate(value, includeTime = false) {
  if (!value) {
    return "—";
  }
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return (includeTime ? dateTimeFormatter : dateFormatter).format(date);
}

export function datasetLabel(datasetName) {
  return {
    customers: "Customers",
    campaign_sales: "Campaign sales",
    demographics: "Demographics",
  }[datasetName] || datasetName;
}

export function setStatusBadge(element, status) {
  const normalized = String(status || "").toUpperCase();
  const [label, className] = statusPresentation[normalized] || [status || "Unknown", "is-neutral"];
  element.classList.remove(...statusClasses);
  element.classList.add(className);
  element.textContent = label;
}

export function showError(container, messageElement, error) {
  messageElement.textContent = error?.message || "The backend request could not be completed.";
  container.hidden = false;
}

export function hideError(container) {
  container.hidden = true;
}

export function setButtonLoading(button, loading, loadingLabel) {
  if (!button.dataset.defaultLabel) {
    button.dataset.defaultLabel = button.textContent.trim();
  }
  button.disabled = loading;
  button.textContent = loading ? loadingLabel : button.dataset.defaultLabel;
}
