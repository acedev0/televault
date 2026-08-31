(() => {
  const shell = document.querySelector("[data-player]");
  const video = shell?.querySelector("[data-player-video]");
  if (!shell || !video) return;

  video.controls = false;

  const find = (selector) => shell.querySelector(selector);
  const playButton = find("[data-player-play]");
  const centerButton = find("[data-player-toggle]");
  const nextButton = find("[data-player-next]");
  const muteButton = find("[data-player-mute]");
  const volumeRange = find("[data-player-volume]");
  const progress = find("[data-player-progress]");
  const currentLabel = find("[data-player-current]");
  const durationLabel = find("[data-player-duration]");
  const spinner = find("[data-player-spinner]");
  const feedback = find("[data-player-feedback]");
  const autoNextButton = find("[data-player-auto-next]");
  const speedToggle = find("[data-player-speed-menu-toggle]");
  const speedMenu = find("[data-player-speed-menu]");
  const speedLabel = find("[data-player-speed-label]");
  const shortcutsButton = find("[data-player-shortcuts]");
  const shortcutsPanel = find("[data-player-shortcut-panel]");
  const shortcutsClose = find("[data-player-shortcuts-close]");
  const pipButton = find("[data-player-pip]");
  const theatreButton = find("[data-player-theatre]");
  const fullscreenButton = find("[data-player-fullscreen]");
  const playIcon = find("[data-icon-play]");
  const pauseIcon = find("[data-icon-pause]");
  const volumeIcon = find("[data-icon-volume]");
  const mutedIcon = find("[data-icon-muted]");
  const fullscreenIcon = find("[data-icon-fullscreen]");
  const exitFullscreenIcon = find("[data-icon-exit-fullscreen]");
  const nextUrl = shell.dataset.nextUrl || "";
  const previousUrl = shell.dataset.previousUrl || "";
  const rates = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];

  let controlsTimer;
  let feedbackTimer;
  let singleClickTimer;
  let autoNext = window.localStorage.getItem("televault.autoplayNext") !== "false";

  const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));
  const formatTime = (value) => {
    if (!Number.isFinite(value) || value < 0) return "0:00";
    const total = Math.floor(value);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    return hours
      ? `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
      : `${minutes}:${String(seconds).padStart(2, "0")}`;
  };

  const showControls = () => {
    shell.classList.remove("controls-hidden");
    window.clearTimeout(controlsTimer);
  };

  const scheduleControls = () => {
    showControls();
    if (!video.paused && speedMenu && !speedMenu.hidden) return;
    if (!video.paused) {
      controlsTimer = window.setTimeout(() => shell.classList.add("controls-hidden"), 2400);
    }
  };

  const showFeedback = (message) => {
    if (!feedback) return;
    feedback.textContent = message;
    feedback.classList.add("visible");
    window.clearTimeout(feedbackTimer);
    feedbackTimer = window.setTimeout(() => feedback.classList.remove("visible"), 800);
  };

  const updatePlayState = () => {
    const paused = video.paused;
    if (playIcon) playIcon.hidden = !paused;
    if (pauseIcon) pauseIcon.hidden = paused;
    if (playButton) playButton.setAttribute("aria-label", paused ? "Play" : "Pause");
    if (centerButton) {
      centerButton.setAttribute("aria-label", paused ? "Play video" : "Pause video");
      centerButton.classList.toggle("playing", !paused);
    }
    shell.classList.toggle("is-playing", !paused);
    if (paused) showControls();
    else scheduleControls();
  };

  const togglePlay = async () => {
    try {
      if (video.paused || video.ended) await video.play();
      else video.pause();
    } catch (error) {
      showFeedback("Playback could not start");
    }
  };

  const updateTimeline = () => {
    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    const current = clamp(video.currentTime || 0, 0, duration || 0);
    const playedPercent = duration ? (current / duration) * 100 : 0;
    let bufferedPercent = 0;
    if (duration && video.buffered.length) {
      for (let index = 0; index < video.buffered.length; index += 1) {
        if (video.buffered.start(index) <= current + 0.5) {
          bufferedPercent = Math.max(bufferedPercent, (video.buffered.end(index) / duration) * 100);
        }
      }
    }
    if (progress) {
      progress.value = String(Math.round(playedPercent * 10));
      progress.style.setProperty("--played", `${playedPercent}%`);
      progress.style.setProperty("--buffered", `${clamp(bufferedPercent, 0, 100)}%`);
      progress.setAttribute("aria-valuetext", `${formatTime(current)} of ${formatTime(duration)}`);
    }
    if (currentLabel) currentLabel.textContent = formatTime(current);
    if (durationLabel) durationLabel.textContent = formatTime(duration);
  };

  const seekTo = (value, message = "") => {
    if (!Number.isFinite(video.duration)) return;
    video.currentTime = clamp(value, 0, video.duration);
    updateTimeline();
    if (message) showFeedback(message);
  };

  const seekBy = (seconds) => {
    const direction = seconds > 0 ? "+" : "−";
    seekTo(video.currentTime + seconds, `${direction}${Math.abs(seconds)} seconds`);
  };

  const updateVolumeState = () => {
    const muted = video.muted || video.volume === 0;
    if (volumeIcon) volumeIcon.hidden = muted;
    if (mutedIcon) mutedIcon.hidden = !muted;
    if (muteButton) muteButton.setAttribute("aria-label", muted ? "Unmute" : "Mute");
    if (volumeRange) {
      volumeRange.value = String(video.muted ? 0 : video.volume);
      volumeRange.style.setProperty("--volume", `${(video.muted ? 0 : video.volume) * 100}%`);
    }
  };

  const setVolume = (value, announce = false) => {
    video.volume = clamp(value, 0, 1);
    video.muted = video.volume === 0;
    window.localStorage.setItem("televault.volume", String(video.volume));
    updateVolumeState();
    if (announce) showFeedback(`Volume ${Math.round(video.volume * 100)}%`);
  };

  const setRate = (value, announce = true) => {
    const rate = rates.reduce((closest, candidate) =>
      Math.abs(candidate - value) < Math.abs(closest - value) ? candidate : closest,
    rates[0]);
    video.playbackRate = rate;
    window.localStorage.setItem("televault.playbackRate", String(rate));
    if (speedLabel) speedLabel.textContent = `${rate}×`;
    shell.querySelectorAll("[data-player-speed]").forEach((button) => {
      button.setAttribute("aria-checked", String(Number(button.dataset.playerSpeed) === rate));
    });
    if (announce) showFeedback(`${rate}× speed`);
  };

  const changeRate = (direction) => {
    const currentIndex = Math.max(0, rates.indexOf(video.playbackRate));
    setRate(rates[clamp(currentIndex + direction, 0, rates.length - 1)]);
  };

  const navigate = (url) => {
    if (url) window.location.assign(url);
  };

  const updateAutoNext = (enabled) => {
    autoNext = enabled;
    window.localStorage.setItem("televault.autoplayNext", String(enabled));
    if (autoNextButton) {
      autoNextButton.setAttribute("aria-pressed", String(enabled));
      autoNextButton.classList.toggle("active", enabled);
    }
  };

  const closeMenus = () => {
    if (speedMenu) speedMenu.hidden = true;
    speedToggle?.setAttribute("aria-expanded", "false");
  };

  const toggleShortcuts = (open = shortcutsPanel?.hidden) => {
    if (!shortcutsPanel) return;
    shortcutsPanel.hidden = !open;
    if (open) {
      showControls();
      shortcutsClose?.focus();
    } else {
      shortcutsButton?.focus();
      scheduleControls();
    }
  };

  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await shell.requestFullscreen({ navigationUI: "hide" });
    } catch (error) {
      showFeedback("Full screen is not available");
    }
  };

  const updateFullscreenState = () => {
    const active = document.fullscreenElement === shell;
    shell.classList.toggle("is-fullscreen", active);
    if (fullscreenIcon) fullscreenIcon.hidden = active;
    if (exitFullscreenIcon) exitFullscreenIcon.hidden = !active;
    fullscreenButton?.setAttribute("aria-label", active ? "Exit full screen" : "Full screen");
    showControls();
  };

  const toggleTheatre = () => {
    const enabled = !document.body.classList.contains("theatre-mode");
    document.body.classList.toggle("theatre-mode", enabled);
    theatreButton?.setAttribute("aria-pressed", String(enabled));
    window.localStorage.setItem("televault.theatreMode", String(enabled));
    showFeedback(enabled ? "Theatre mode" : "Default view");
  };

  playButton?.addEventListener("click", togglePlay);
  centerButton?.addEventListener("click", togglePlay);
  nextButton?.addEventListener("click", () => navigate(nextUrl));
  muteButton?.addEventListener("click", () => {
    video.muted = !video.muted;
    updateVolumeState();
    showFeedback(video.muted ? "Muted" : `Volume ${Math.round(video.volume * 100)}%`);
  });
  volumeRange?.addEventListener("input", () => setVolume(Number(volumeRange.value)));
  progress?.addEventListener("input", () => {
    if (!Number.isFinite(video.duration)) return;
    seekTo((Number(progress.value) / 1000) * video.duration);
  });

  speedToggle?.addEventListener("click", (event) => {
    event.stopPropagation();
    if (!speedMenu) return;
    speedMenu.hidden = !speedMenu.hidden;
    speedToggle.setAttribute("aria-expanded", String(!speedMenu.hidden));
    showControls();
  });
  shell.querySelectorAll("[data-player-speed]").forEach((button) => {
    button.addEventListener("click", () => {
      setRate(Number(button.dataset.playerSpeed));
      closeMenus();
      scheduleControls();
    });
  });
  shortcutsButton?.addEventListener("click", () => toggleShortcuts());
  shortcutsClose?.addEventListener("click", () => toggleShortcuts(false));
  autoNextButton?.addEventListener("click", () => updateAutoNext(!autoNext));
  fullscreenButton?.addEventListener("click", toggleFullscreen);
  theatreButton?.addEventListener("click", toggleTheatre);

  if (!document.pictureInPictureEnabled || typeof video.requestPictureInPicture !== "function") {
    if (pipButton) pipButton.hidden = true;
  } else {
    pipButton?.addEventListener("click", async () => {
      try {
        if (document.pictureInPictureElement) await document.exitPictureInPicture();
        else await video.requestPictureInPicture();
      } catch (error) {
        showFeedback("Picture in picture is not available");
      }
    });
  }

  video.addEventListener("click", () => {
    window.clearTimeout(singleClickTimer);
    singleClickTimer = window.setTimeout(togglePlay, 190);
  });
  video.addEventListener("dblclick", (event) => {
    event.preventDefault();
    window.clearTimeout(singleClickTimer);
    toggleFullscreen();
  });
  shell.addEventListener("mousemove", scheduleControls);
  shell.addEventListener("touchstart", showControls, { passive: true });
  shell.addEventListener("mouseleave", () => {
    if (!video.paused) shell.classList.add("controls-hidden");
  });
  find("[data-player-controls]")?.addEventListener("mouseenter", showControls);

  video.addEventListener("loadedmetadata", updateTimeline);
  video.addEventListener("durationchange", updateTimeline);
  video.addEventListener("timeupdate", updateTimeline);
  video.addEventListener("progress", updateTimeline);
  video.addEventListener("play", updatePlayState);
  video.addEventListener("pause", updatePlayState);
  video.addEventListener("volumechange", updateVolumeState);
  video.addEventListener("waiting", () => spinner?.classList.add("visible"));
  video.addEventListener("seeking", () => spinner?.classList.add("visible"));
  ["playing", "canplay", "seeked"].forEach((eventName) => {
    video.addEventListener(eventName, () => spinner?.classList.remove("visible"));
  });
  video.addEventListener("error", () => {
    spinner?.classList.remove("visible");
    showFeedback("This video format may not be supported by your browser");
    showControls();
  });
  video.addEventListener("ended", () => {
    updatePlayState();
    if (autoNext && nextUrl) {
      showFeedback("Playing next video…");
      window.setTimeout(() => navigate(nextUrl), 850);
    }
  });

  document.addEventListener("fullscreenchange", updateFullscreenState);
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".player-menu-wrap")) closeMenus();
  });

  document.addEventListener("keydown", (event) => {
    const active = document.activeElement;
    const tag = active?.tagName || "";
    if (/^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(tag) || active?.isContentEditable) return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;

    const key = event.key.toLowerCase();
    let handled = true;
    if (key === " " || key === "k") togglePlay();
    else if (key === "arrowleft") seekBy(-5);
    else if (key === "arrowright") seekBy(5);
    else if (key === "j") seekBy(-10);
    else if (key === "l") seekBy(10);
    else if (key === "arrowup") setVolume(video.muted ? 0.05 : video.volume + 0.05, true);
    else if (key === "arrowdown") setVolume(video.muted ? 0 : video.volume - 0.05, true);
    else if (key === "m") {
      video.muted = !video.muted;
      updateVolumeState();
      showFeedback(video.muted ? "Muted" : `Volume ${Math.round(video.volume * 100)}%`);
    } else if (key === "f") toggleFullscreen();
    else if (key === ">") changeRate(1);
    else if (key === "<") changeRate(-1);
    else if (key === "home") seekTo(0, "Start");
    else if (key === "end") seekTo(video.duration, "End");
    else if (key === "n") navigate(nextUrl);
    else if (key === "p") navigate(previousUrl);
    else if (event.key === "?") toggleShortcuts();
    else if (/^[0-9]$/.test(event.key) && Number.isFinite(video.duration)) {
      seekTo((Number(event.key) / 10) * video.duration, `${Number(event.key) * 10}%`);
    } else if (key === "escape" && shortcutsPanel && !shortcutsPanel.hidden) {
      toggleShortcuts(false);
    } else {
      handled = false;
    }
    if (handled) {
      event.preventDefault();
      showControls();
      scheduleControls();
    }
  });

  const savedVolume = Number(window.localStorage.getItem("televault.volume"));
  if (Number.isFinite(savedVolume) && savedVolume >= 0 && savedVolume <= 1) {
    video.volume = savedVolume;
  }
  const savedRate = Number(window.localStorage.getItem("televault.playbackRate"));
  setRate(rates.includes(savedRate) ? savedRate : 1, false);
  updateAutoNext(autoNext);
  updateVolumeState();
  updatePlayState();
  updateTimeline();

  if (window.localStorage.getItem("televault.theatreMode") === "true") {
    document.body.classList.add("theatre-mode");
    theatreButton?.setAttribute("aria-pressed", "true");
  }

  if ("mediaSession" in navigator) {
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: shell.dataset.title || document.title,
        artist: "TeleVault",
        album: "Private Telegram library",
        artwork: [{ src: shell.dataset.artwork, sizes: "720x405", type: "image/webp" }],
      });
      const setAction = (name, handler) => {
        try {
          navigator.mediaSession.setActionHandler(name, handler);
        } catch (error) {
          // Browsers expose different Media Session action sets.
        }
      };
      setAction("play", () => video.play());
      setAction("pause", () => video.pause());
      setAction("seekbackward", (details) => seekBy(-(details.seekOffset || 10)));
      setAction("seekforward", (details) => seekBy(details.seekOffset || 10));
      setAction("seekto", (details) => seekTo(details.seekTime || 0));
      if (nextUrl) setAction("nexttrack", () => navigate(nextUrl));
      if (previousUrl) setAction("previoustrack", () => navigate(previousUrl));
    } catch (error) {
      // Media Session is an enhancement; playback remains fully functional without it.
    }
  }
})();
