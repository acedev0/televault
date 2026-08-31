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

  const randomToggle = document.querySelector("[data-random-toggle]");
  randomToggle?.addEventListener("click", () => {
    const url = new URL(window.location.href);
    const enabled = randomToggle.getAttribute("aria-checked") === "true";
    if (enabled) {
      url.searchParams.set("sort", "newest");
      url.searchParams.delete("seed");
    } else {
      const seedBuffer = new Uint32Array(1);
      window.crypto?.getRandomValues?.(seedBuffer);
      const seed = (seedBuffer[0] || Date.now()) % 2147483647 || 1;
      url.searchParams.set("sort", "random");
      url.searchParams.set("seed", String(seed));
    }
    window.location.assign(`${url.pathname}?${url.searchParams.toString()}`);
  });

  const mediaGrid = document.querySelector("[data-media-grid]");
  const infiniteLoader = document.querySelector("[data-infinite-loader]");
  const infiniteToggle = document.querySelector("[data-infinite-toggle]");
  const savedInfinitePreference = window.localStorage.getItem("televault.infiniteScroll");
  let infiniteEnabled = savedInfinitePreference !== "false";

  const updateInfiniteToggle = () => {
    if (!infiniteToggle) return;
    infiniteToggle.setAttribute("aria-checked", String(infiniteEnabled));
    infiniteToggle.classList.toggle("active", infiniteEnabled);
  };
  updateInfiniteToggle();

  if (mediaGrid && infiniteLoader) {
    const loaderMessage = infiniteLoader.querySelector("[data-loader-message]");
    const retryButton = infiniteLoader.querySelector("[data-loader-retry]");
    let loading = false;
    let hasMore = true;
    let observer;
    let fallbackScroll;

    const stopWatching = () => {
      observer?.disconnect();
      if (fallbackScroll) window.removeEventListener("scroll", fallbackScroll);
    };

    const startWatching = () => {
      if (!hasMore || !infiniteEnabled) return;
      stopWatching();
      infiniteLoader.classList.remove("manual");
      if (loaderMessage) loaderMessage.textContent = "Scroll for more media";
      if ("IntersectionObserver" in window) {
        if (!observer) {
          observer = new IntersectionObserver(
            (entries) => {
              if (entries.some((entry) => entry.isIntersecting)) loadMore();
            },
            { rootMargin: "700px 0px" },
          );
        }
        observer.observe(infiniteLoader);
      } else {
        fallbackScroll = () => {
          if (infiniteLoader.getBoundingClientRect().top < window.innerHeight + 700) loadMore();
        };
        window.addEventListener("scroll", fallbackScroll, { passive: true });
        fallbackScroll();
      }
    };

    const applyInfiniteMode = (enabled, persist = true) => {
      infiniteEnabled = enabled;
      if (persist) window.localStorage.setItem("televault.infiniteScroll", String(enabled));
      updateInfiniteToggle();
      stopWatching();
      infiniteLoader.classList.toggle("manual", !enabled);
      if (!enabled && hasMore) {
        infiniteLoader.classList.remove("failed");
        if (loaderMessage) loaderMessage.textContent = "Infinite scroll is off";
        if (retryButton) retryButton.textContent = "Load more";
      } else {
        startWatching();
      }
    };

    const loadMore = async () => {
      if (loading || !hasMore) return;
      loading = true;
      mediaGrid.setAttribute("aria-busy", "true");
      infiniteLoader.classList.remove("failed");
      infiniteLoader.classList.add("loading");
      if (loaderMessage) loaderMessage.textContent = "Loading more media…";
      try {
        const url = new URL("/api/media", window.location.origin);
        const current = new URLSearchParams(window.location.search);
        ["q", "kind", "sort", "seed"].forEach((key) => {
          const value = current.get(key);
          if (value) url.searchParams.set(key, value);
        });
        if (!url.searchParams.has("seed") && infiniteLoader.dataset.seed) {
          url.searchParams.set("seed", infiniteLoader.dataset.seed);
        }
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
          stopWatching();
          infiniteLoader.classList.remove("manual", "failed");
          infiniteLoader.classList.add("complete");
          if (loaderMessage) loaderMessage.textContent = "Everything is loaded";
        } else if (!infiniteEnabled) {
          infiniteLoader.classList.add("manual");
          if (loaderMessage) loaderMessage.textContent = "Infinite scroll is off";
          if (retryButton) retryButton.textContent = "Load more";
        } else {
          window.setTimeout(startWatching, 0);
        }
      } catch (error) {
        stopWatching();
        infiniteLoader.classList.add("failed");
        if (loaderMessage) loaderMessage.textContent = "Could not load more media";
        if (retryButton) retryButton.textContent = "Retry";
      } finally {
        loading = false;
        infiniteLoader.classList.remove("loading");
        mediaGrid.setAttribute("aria-busy", "false");
      }
    };

    retryButton?.addEventListener("click", () => {
      loadMore();
    });
    infiniteToggle?.addEventListener("click", () => applyInfiniteMode(!infiniteEnabled));
    applyInfiniteMode(infiniteEnabled, false);
  } else {
    infiniteToggle?.addEventListener("click", () => {
      infiniteEnabled = !infiniteEnabled;
      window.localStorage.setItem("televault.infiniteScroll", String(infiniteEnabled));
      updateInfiniteToggle();
    });
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
