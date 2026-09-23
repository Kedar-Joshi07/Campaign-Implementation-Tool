const make = (tag, className, text) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
};

const count = (value) => Number(value || 0).toLocaleString();

function duration(seconds) {
  const value = Math.max(0, Number(seconds));
  if (value < 60) return `${Math.ceil(value)} sec`;
  if (value < 3600) return `${Math.ceil(value / 60)} min`;
  return `${(value / 3600).toLocaleString(undefined, { maximumFractionDigits: 1 })} hr`;
}

function etaText(progress) {
  const low = progress.estimated_seconds_remaining_low;
  const high = progress.estimated_seconds_remaining_high;
  if (low === 0 && high === 0) return "Completed";
  if (low === null || low === undefined || high === null || high === undefined) {
    return progress.lifecycle_status === "QUEUED"
      ? "Starts when processing capacity is available"
      : "Estimate available after measurable processing begins";
  }
  return `Approximately ${duration(low)} to ${duration(high)} remaining`;
}

export function isRunActive(run) {
  return new Set([
    "QUEUED", "PROCESSING", "PAUSE_REQUESTED", "PAUSED",
    "STOP_REQUESTED", "RESTART_REQUESTED",
  ]).has(run.progress?.lifecycle_status || run.status);
}

export function createRunProgress(run, { compact = false } = {}) {
  const progress = run.progress;
  const section = make("section", `run-progress${compact ? " is-compact" : ""}`);
  if (!progress) {
    section.append(make("p", "panel-note", "Detailed progress is not available for this saved search."));
    return section;
  }
  const heading = make("div", "run-progress-heading");
  heading.append(
    make("strong", null, progress.stage_label),
    make("span", null, `${progress.progress_percent}%`),
  );
  const track = make("div", "run-progress-track");
  track.setAttribute("role", "progressbar");
  track.setAttribute("aria-label", `Search progress: ${progress.stage_label}`);
  track.setAttribute("aria-valuemin", "0");
  track.setAttribute("aria-valuemax", "100");
  track.setAttribute("aria-valuenow", String(progress.progress_percent));
  const fill = make("span");
  fill.style.width = `${progress.progress_percent}%`;
  track.append(fill);
  const counters = progress.total_count === null
    ? `${count(progress.processed_count)} ${progress.progress_unit} processed; final total is confirmed at completion`
    : `${count(progress.processed_count)} of ${count(progress.total_count)} ${progress.progress_unit} processed`;
  section.append(
    heading,
    track,
    make("p", "run-progress-message", progress.status_message),
    make("p", "run-progress-meta", counters),
    make("p", "run-progress-meta", etaText(progress)),
  );
  return section;
}

export function createRunIssue(run) {
  if (!run.issue) return null;
  const section = make("section", "run-issue");
  section.setAttribute("role", "status");
  section.append(
    make("h4", null, run.status === "BLOCKED" ? "Why this search is blocked" : "Why this search failed"),
    make("p", null, run.issue.summary),
  );
  const list = make("ul");
  for (const step of run.issue.resolution_steps) list.append(make("li", null, step));
  section.append(list);
  if (run.issue.retryable) {
    section.append(make("p", "panel-note", "This condition is retryable after the suggested correction."));
  }
  return section;
}
