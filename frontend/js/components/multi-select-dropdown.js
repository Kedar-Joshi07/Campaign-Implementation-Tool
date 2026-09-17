// Progressive enhancement: the native select remains the authoritative form/state bridge.
// Options and labels come from the caller; this component owns no business vocabulary.
const instances = new WeakMap();

export class MultiSelectDropdown {
  constructor(select, { label } = {}) {
    if (select?.tagName !== "SELECT" || !select.multiple || !select.id) {
      throw new TypeError("A named native multiple select with an ID is required.");
    }
    this.select = select;
    this.document = select.ownerDocument;
    this.rows = [];
    this.state = { loading: false, disabled: false, error: "" };
    this.original = {
      hidden: select.hidden, tabIndex: select.getAttribute("tabindex"),
      ariaHidden: select.getAttribute("aria-hidden"), labels: [...select.labels],
    };
    this.label = label || this.original.labels[0]?.childNodes[0]?.textContent.trim() || select.id;
    const make = (tag, className, text) => {
      const element = this.document.createElement(tag);
      if (className) element.className = className;
      if (text !== undefined) element.textContent = text;
      return element;
    };
    this.make = make;
    this.root = make("div", "multi-select-dropdown");
    this.root.setAttribute("role", "group");
    this.root.setAttribute("aria-label", `${this.label} selection`);
    this.root.dataset.multiSelectFor = select.id;
    this.trigger = make("button", "multi-select-trigger");
    this.trigger.type = "button";
    this.trigger.id = `${select.id}-trigger`;
    this.trigger.setAttribute("aria-haspopup", "dialog");
    this.trigger.setAttribute("aria-expanded", "false");
    this.trigger.setAttribute("aria-label", this.label);
    this.trigger.setAttribute("aria-describedby", [
      select.getAttribute("aria-describedby"), `${select.id}-selection-summary`, `${select.id}-status`,
    ].filter(Boolean).join(" "));
    this.summary = make("span", "multi-select-summary", "0 selected");
    this.summary.id = `${select.id}-selection-summary`;
    this.trigger.append(this.summary, make("span", "multi-select-arrow", "▾"));
    this.trigger.lastChild.setAttribute("aria-hidden", "true");
    this.chips = make("div", "multi-select-chips");
    this.chips.setAttribute("role", "list");
    this.chips.setAttribute("aria-label", `Selected ${this.label}`);
    this.status = make("p", "multi-select-status");
    this.status.id = `${select.id}-status`;
    this.root.setAttribute("aria-describedby", this.status.id);
    this.status.setAttribute("role", "status");
    this.status.setAttribute("aria-live", "polite");
    this.panel = make("div", "multi-select-panel");
    this.panel.id = `${select.id}-panel`;
    this.panel.hidden = true;
    this.panel.setAttribute("role", "dialog");
    this.panel.setAttribute("aria-label", `Choose ${this.label}`);
    this.trigger.setAttribute("aria-controls", this.panel.id);
    const searchLabel = make("label", "visually-hidden", `Search ${this.label}`);
    this.search = make("input", "multi-select-search");
    this.search.type = "search";
    this.search.id = `${select.id}-search`;
    searchLabel.htmlFor = this.search.id;
    this.search.placeholder = "Search options";
    this.search.autocomplete = "off";
    const actions = make("div", "multi-select-actions");
    this.selectAll = make("button", "button button-secondary");
    this.clearAll = make("button", "button button-secondary", "Clear All");
    this.selectAll.type = this.clearAll.type = "button";
    actions.append(this.selectAll, this.clearAll);
    const help = make("small", "multi-select-help",
      "Select All visible adds filtered, available options. Clear All removes every selection, including hidden matches. Use arrows to move; Space or Enter toggles; Escape closes.");
    help.id = `${select.id}-dropdown-help`;
    this.selectAll.setAttribute("aria-describedby", help.id);
    this.clearAll.setAttribute("aria-describedby", help.id);
    this.options = make("div", "multi-select-options");
    this.options.setAttribute("role", "group");
    this.options.setAttribute("aria-label", `${this.label} options`);
    this.empty = make("p", "multi-select-empty", "No matching options.");
    this.empty.setAttribute("role", "status");
    this.panel.append(searchLabel, this.search, actions, help, this.empty, this.options);
    this.root.append(this.trigger, this.chips, this.status, this.panel);
    select.after(this.root);
    for (const associated of this.original.labels) associated.htmlFor = this.trigger.id;
    select.hidden = true;
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");

    this.trigger.addEventListener("click", () => this.panel.hidden ? this.open() : this.close());
    this.trigger.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        this.open({ focusOptions: true, last: event.key === "ArrowUp" });
      }
    });
    this.search.addEventListener("input", (event) => {
      // Searching is UI-only, never a business-form input or a persistence event.
      event.stopPropagation();
      this.filter();
    });
    this.root.addEventListener("input", (event) => event.stopPropagation());
    this.root.addEventListener("change", (event) => event.stopPropagation());
    this.root.addEventListener("keydown", (event) => this.onKeydown(event));
    this.root.addEventListener("focusout", (event) => {
      if (event.relatedTarget && !this.root.contains(event.relatedTarget)) this.close({ restoreFocus: false });
    });
    this.selectAll.addEventListener("click", () => {
      if (this.blocked()) return;
      for (const row of this.availableRows()) row.option.selected = true;
      this.commit();
    });
    this.clearAll.addEventListener("click", () => {
      if (this.blocked()) return;
      for (const option of select.options) option.selected = false;
      this.commit();
    });
    this.onOutside = (event) => {
      if (!this.root.contains(event.target)) this.close({ restoreFocus: false });
    };
    this.onSelectChange = () => this.refresh();
    this.onInvalid = (event) => {
      event.preventDefault();
      this.close({ restoreFocus: false });
      this.status.textContent = select.validationMessage;
      this.trigger.setAttribute("aria-invalid", "true");
      this.trigger.focus();
    };
    this.onReset = () => queueMicrotask(() => this.refresh());
    this.document.addEventListener("pointerdown", this.onOutside);
    select.addEventListener("change", this.onSelectChange);
    select.addEventListener("invalid", this.onInvalid);
    select.form?.addEventListener("reset", this.onReset);
    this.refresh();
  }

  values() { return [...this.select.selectedOptions].map((option) => option.value); }
  blocked() { return this.select.disabled || this.state.disabled || this.state.loading || Boolean(this.state.error); }
  availableRows() { return this.rows.filter((row) => !row.label.hidden && !row.option.disabled); }

  setOptions(options) {
    const seen = new Set();
    const normalized = options.map((item) => typeof item === "string" ? { value: item, label: item } : item);
    for (const item of normalized) {
      if (!item || typeof item.value !== "string" || typeof (item.label ?? item.value) !== "string" || seen.has(item.value)) {
        throw new TypeError("Options require unique string values and string labels.");
      }
      seen.add(item.value);
    }
    const selected = new Set(this.values());
    const fragment = this.document.createDocumentFragment();
    for (const item of normalized) {
      const option = this.make("option", null, item.label ?? item.value);
      option.value = item.value;
      option.disabled = Boolean(item.disabled);
      option.selected = selected.has(item.value);
      fragment.append(option);
    }
    this.select.replaceChildren(fragment);
    this.refresh();
  }

  setValues(values, { emitChange = false } = {}) {
    const known = new Set([...this.select.options].map((option) => option.value));
    if (values.some((value) => !known.has(value))) throw new TypeError("Selections must use supplied option values.");
    const selected = new Set(values);
    for (const option of this.select.options) option.selected = selected.has(option.value);
    if (emitChange) this.commit();
    else this.refresh();
  }

  setState(patch) {
    const hadFocus = this.root.contains(this.document.activeElement);
    this.state = { ...this.state, ...patch };
    if (this.blocked()) this.close({ restoreFocus: false });
    this.refresh();
    if (this.blocked() && hadFocus) { this.root.tabIndex = -1; this.root.focus(); }
  }

  refresh() {
    const options = [...this.select.options];
    const changed = options.length !== this.rows.length || options.some((option, index) => {
      const row = this.rows[index];
      return row?.option !== option || row.value !== option.value || row.text !== option.label || row.disabled !== option.disabled;
    });
    if (changed) {
      const fragment = this.document.createDocumentFragment();
      this.rows = options.map((option, index) => {
        const label = this.make("label", "multi-select-option");
        const input = this.make("input");
        input.type = "checkbox";
        input.id = `${this.select.id}-option-${index}`;
        input.value = option.value;
        label.htmlFor = input.id;
        const text = this.make("span", null, option.label);
        label.append(input, text);
        if (option.disabled) label.append(this.make("small", null, "Unavailable"));
        input.addEventListener("change", (event) => {
          event.stopPropagation();
          if (!this.blocked() && !option.disabled) { option.selected = input.checked; this.commit(); }
        });
        fragment.append(label);
        return { option, label, input, value: option.value, text: option.label, disabled: option.disabled };
      });
      this.options.replaceChildren(fragment);
    }
    const blocked = this.blocked();
    this.trigger.disabled = blocked;
    this.search.disabled = blocked;
    if (blocked && !this.panel.hidden) {
      const hadFocus = this.root.contains(this.document.activeElement);
      this.close({ restoreFocus: false });
      if (hadFocus) { this.root.tabIndex = -1; this.root.focus(); }
    }
    this.root.setAttribute("aria-busy", String(this.state.loading));
    this.root.setAttribute("aria-disabled", String(blocked));
    for (const row of this.rows) {
      row.input.checked = row.option.selected;
      row.input.disabled = blocked || row.option.disabled;
    }
    const selected = [...this.select.selectedOptions];
    this.summary.textContent = `${selected.length} selected`;
    const fragment = this.document.createDocumentFragment();
    // Bounded chips keep collapsed controls compact, even for hundreds of products.
    for (const option of selected.slice(0, 5)) {
      const chip = this.make("span", "multi-select-chip");
      chip.setAttribute("role", "listitem");
      const remove = this.make("button", "multi-select-remove", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", `Remove ${option.label} from ${this.label}`);
      remove.disabled = blocked;
      remove.addEventListener("click", () => {
        if (this.blocked()) return;
        option.selected = false;
        this.commit();
        this.trigger.focus();
      });
      chip.append(this.make("span", null, option.label), remove);
      fragment.append(chip);
    }
    if (selected.length > 5) {
      const more = this.make("span", "multi-select-more", `+${selected.length - 5} more; open to review`);
      more.setAttribute("role", "listitem");
      fragment.append(more);
    }
    this.chips.replaceChildren(fragment);
    this.chips.hidden = selected.length === 0;
    this.status.textContent = this.state.loading ? "Loading choices…"
      : this.state.error || (this.select.disabled || this.state.disabled ? "Choices disabled." : "");
    this.trigger.removeAttribute("aria-invalid");
    this.filter();
  }

  filter() {
    const query = this.search.value.trim().toLocaleLowerCase();
    for (const row of this.rows) {
      row.label.hidden = !`${row.text} ${row.value}`.toLocaleLowerCase().includes(query);
      row.input.tabIndex = -1;
    }
    const available = this.availableRows();
    const focused = available.find((row) => row.input === this.document.activeElement) || available[0];
    if (focused) focused.input.tabIndex = 0;
    const matching = this.rows.filter((row) => !row.label.hidden).length;
    this.empty.hidden = matching !== 0;
    this.empty.textContent = this.rows.length ? "No matching options." : "No options available.";
    this.selectAll.textContent = `Select All visible (${available.length})`;
    this.selectAll.disabled = this.blocked() || available.length === 0;
    this.clearAll.disabled = this.blocked() || this.select.selectedOptions.length === 0;
  }

  commit() {
    this.refresh();
    this.select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  open({ focusOptions = false, last = false } = {}) {
    if (this.blocked()) return;
    this.panel.hidden = false;
    this.trigger.setAttribute("aria-expanded", "true");
    const available = this.availableRows();
    const row = last ? available.at(-1) : available[0];
    if (focusOptions && row) row.input.focus();
    else this.search.focus();
  }

  close({ restoreFocus = true } = {}) {
    const wasOpen = !this.panel.hidden;
    this.panel.hidden = true;
    this.trigger.setAttribute("aria-expanded", "false");
    if (wasOpen && restoreFocus) this.trigger.focus();
  }

  onKeydown(event) {
    if (event.key === "Escape" && !this.panel.hidden) {
      event.preventDefault(); event.stopPropagation(); this.close(); return;
    }
    const available = this.availableRows();
    const index = available.findIndex((row) => row.input === event.target);
    if (event.target === this.search && event.key === "ArrowDown") {
      event.preventDefault(); available[0]?.input.focus(); return;
    }
    if (index < 0) return;
    if (event.key === "Enter") {
      event.preventDefault();
      if (!this.blocked()) {
        available[index].option.selected = !available[index].option.selected;
        this.commit();
      }
    } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? available.length - 1
        : (index + (event.key === "ArrowDown" ? 1 : -1) + available.length) % available.length;
      for (const row of available) row.input.tabIndex = -1;
      available[next].input.tabIndex = 0;
      available[next].input.focus();
    }
  }

  destroy() {
    this.document.removeEventListener("pointerdown", this.onOutside);
    this.select.removeEventListener("change", this.onSelectChange);
    this.select.removeEventListener("invalid", this.onInvalid);
    this.select.form?.removeEventListener("reset", this.onReset);
    for (const label of this.original.labels) label.htmlFor = this.select.id;
    this.select.hidden = this.original.hidden;
    for (const [attribute, value] of [["tabindex", this.original.tabIndex], ["aria-hidden", this.original.ariaHidden]]) {
      if (value === null) this.select.removeAttribute(attribute);
      else this.select.setAttribute(attribute, value);
    }
    this.root.remove();
    instances.delete(this.select);
  }
}

export function enhanceMultiSelect(select, configuration) {
  if (!instances.has(select)) instances.set(select, new MultiSelectDropdown(select, configuration));
  return instances.get(select);
}
export function refreshMultiSelect(select) { instances.get(select)?.refresh(); }
export function setMultiSelectState(select, state) { instances.get(select)?.setState(state); }
export function focusMultiSelect(select) { (instances.get(select)?.trigger || select)?.focus(); }
