"use strict";

const SWITCH_TO_LAST_USED_TAB = "ctrl-tab-chrome.switchToLastUsedTab";

function isPlainCtrlTab(event) {
  return (
    event.key === "Tab" &&
    event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey &&
    !event.metaKey
  );
}

function requestLastUsedTabSwitch() {
  try {
    const response = chrome.runtime.sendMessage({ type: SWITCH_TO_LAST_USED_TAB });
    if (response && typeof response.catch === "function") {
      response.catch(() => {});
    }
  } catch (_error) {
    // The tab can outlive the extension context during reloads.
  }
}

window.addEventListener(
  "keydown",
  (event) => {
    if (!isPlainCtrlTab(event)) {
      return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();

    if (!event.repeat) {
      requestLastUsedTabSwitch();
    }
  },
  { capture: true }
);
