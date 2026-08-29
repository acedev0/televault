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

  const mediaGrid = document.querySelector("[data-media-grid]");
  const infiniteLoader = document.querySelector("[data-infinite-loader]");
  if (mediaGrid && infiniteLoader) {
    const loaderMessage = infiniteLoader.querySelector("[data-loader-message]");
    const retryButton = infiniteLoader.querySelector("[data-loader-retry]");
    let loading = false;
    let hasMore = true;
    let observer;

    const loadMore = async () => {
      if (loading || !hasMore) return;
      loading = true;
      mediaGrid.setAttribute("aria-busy", "true");
      infiniteLoader.classList.remove("failed");
      if (loaderMessage) loaderMessage.textContent = "Loading more media…";
      try {
        const url = new URL("/api/media", window.location.origin);
        const current = new URLSearchParams(window.location.search);
        ["q", "kind", "sort"].forEach((key) => {
          const value = current.get(key);
          if (value) url.searchParams.set(key, value);
        });
        url.searchParams.set("offset", infiniteLoader.dataset.offset || "0");
        const response = await fetch(url, {
          headers: { Accept: "text/html", "X-Requested-With": "TeleVault" },
        });
        if (response.status === 401) {
          window.location.assign("/login");
          return;
        }
        if (!response.ok) throw new Error("Media request failed");
        const markup = await response.text();
        if (markup.trim()) mediaGrid.insertAdjacentHTML("beforeend", markup);
        infiniteLoader.dataset.offset = response.headers.get("X-Next-Offset") || infiniteLoader.dataset.offset || "0";
        hasMore = response.headers.get("X-Has-More") === "true" && Boolean(markup.trim());
        if (!hasMore) {
          observer?.disconnect();
          infiniteLoader.classList.add("complete");
          if (loaderMessage) loaderMessage.textContent = "Everything is loaded";
          window.setTimeout(() => infiniteLoader.remove(), 260);
        }
      } catch (error) {
        observer?.unobserve(infiniteLoader);
        infiniteLoader.classList.add("failed");
        if (loaderMessage) loaderMessage.textContent = "Could not load more media";
      } finally {
        loading = false;
        mediaGrid.setAttribute("aria-busy", "false");
      }
    };

    retryButton?.addEventListener("click", () => {
      observer?.observe(infiniteLoader);
      loadMore();
    });

    if ("IntersectionObserver" in window) {
      observer = new IntersectionObserver(
        (entries) => {
          if (entries.some((entry) => entry.isIntersecting)) loadMore();
        },
        { rootMargin: "700px 0px" },
      );
      observer.observe(infiniteLoader);
    } else {
      const onScroll = () => {
        if (infiniteLoader.getBoundingClientRect().top < window.innerHeight + 700) loadMore();
      };
      window.addEventListener("scroll", onScroll, { passive: true });
      onScroll();
    }
  }

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
