const numberFormatter = new Intl.NumberFormat("en-US");
const percentFormatter = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 1,
});
const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
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

export function formatNumber(value) {
  return value === null || value === undefined ? "—" : numberFormatter.format(value);
}

export function formatPercent(value) {
  return Number.isFinite(Number(value)) ? percentFormatter.format(Number(value)) : "—";
}

export function formatCurrency(value) {
  return Number.isFinite(Number(value)) ? currencyFormatter.format(Number(value)) : "—";
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
