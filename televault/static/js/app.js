(() => {
  const sidebar = document.querySelector("[data-sidebar]");
  const scrim = document.querySelector("[data-sidebar-scrim]");
  const toggle = document.querySelector("[data-sidebar-toggle]");
  const setSidebar = (open) => {
    if (!sidebar) return;
    sidebar.classList.toggle("open", open);
    scrim?.classList.toggle("open", open);
    document.body.classList.toggle("nav-open", open);
  };
  toggle?.addEventListener("click", () => setSidebar(!sidebar?.classList.contains("open")));
  scrim?.addEventListener("click", () => setSidebar(false));

  document.querySelectorAll("[data-auto-submit]").forEach((control) => {
    control.addEventListener("change", () => control.form?.submit());
  });

  const toast = document.querySelector("[data-toast]");
  let toastTimer;
  const showToast = (message, error = false) => {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("error", error);
    toast.classList.add("visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 4200);
  };

  const syncForm = document.querySelector("[data-sync-form]");
  const syncButton = document.querySelector("[data-sync-button]");
  const pollSync = async () => {
    try {
      const response = await fetch("/api/status", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Status request failed");
      const status = await response.json();
      if (status.telegram_error) {
        syncButton?.classList.remove("loading");
        showToast(status.telegram_error, true);
        return;
      }
      if (status.index?.running) {
        if (syncButton) {
          syncButton.classList.add("loading");
          const label = syncButton.querySelector("span");
          if (label) label.textContent = `${status.index.media_found} found`;
        }
        window.setTimeout(pollSync, 1800);
        return;
      }
      showToast("Library sync complete");
      window.setTimeout(() => window.location.reload(), 650);
    } catch (error) {
      syncButton?.classList.remove("loading");
      showToast("Could not check sync status", true);
    }
  };
  syncForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (syncButton?.classList.contains("loading")) return;
    syncButton?.classList.add("loading");
    const label = syncButton?.querySelector("span");
    if (label) label.textContent = "Starting";
    try {
      const response = await fetch(syncForm.action, { method: "POST", body: new FormData(syncForm) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Sync failed");
      showToast(result.status === "already_running" ? "Sync already running" : "Scanning Telegram…");
      window.setTimeout(pollSync, 900);
    } catch (error) {
      syncButton?.classList.remove("loading");
      if (label) label.textContent = "Sync";
      showToast(error.message || "Could not start sync", true);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "")) {
      const search = document.querySelector('input[type="search"]');
      if (search) {
        event.preventDefault();
        search.focus();
      }
    }
    if (event.key === "Escape") setSidebar(false);
  });
})();

