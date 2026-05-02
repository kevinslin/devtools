"use strict";

const SWITCH_TO_LAST_USED_TAB = "ctrl-tab-chrome.switchToLastUsedTab";
const MAX_HISTORY_PER_WINDOW = 50;
const HISTORY_STORAGE_KEY = "historyByWindowId";

const historyByWindowId = new Map();
const historyReady = loadHistory();

async function loadHistory() {
  const stored = await chrome.storage.session.get(HISTORY_STORAGE_KEY);
  const serialized = stored[HISTORY_STORAGE_KEY] || {};

  for (const [windowId, history] of Object.entries(serialized)) {
    const numericWindowId = Number(windowId);
    if (Number.isInteger(numericWindowId) && Array.isArray(history)) {
      historyByWindowId.set(numericWindowId, history.filter(Number.isInteger));
    }
  }
}

async function saveHistory() {
  const serialized = {};
  for (const [windowId, history] of historyByWindowId.entries()) {
    serialized[windowId] = history;
  }
  await chrome.storage.session.set({ [HISTORY_STORAGE_KEY]: serialized });
}

async function rememberTab(windowId, tabId) {
  await historyReady;

  if (!Number.isInteger(windowId) || !Number.isInteger(tabId)) {
    return;
  }

  const existing = historyByWindowId.get(windowId) || [];
  const next = [tabId, ...existing.filter((existingTabId) => existingTabId !== tabId)];
  historyByWindowId.set(windowId, next.slice(0, MAX_HISTORY_PER_WINDOW));
  await saveHistory();
}

async function forgetTab(tabId) {
  await historyReady;

  for (const [windowId, history] of historyByWindowId.entries()) {
    const next = history.filter((existingTabId) => existingTabId !== tabId);
    if (next.length === 0) {
      historyByWindowId.delete(windowId);
    } else {
      historyByWindowId.set(windowId, next);
    }
  }
  await saveHistory();
}

async function forgetWindow(windowId) {
  await historyReady;
  historyByWindowId.delete(windowId);
  await saveHistory();
}

function getCandidateTabIds(windowId, currentTabId) {
  return (historyByWindowId.get(windowId) || []).filter((tabId) => tabId !== currentTabId);
}

async function seedActiveTabs() {
  await historyReady;
  const activeTabs = await chrome.tabs.query({ active: true });
  for (const tab of activeTabs) {
    await rememberTab(tab.windowId, tab.id);
  }
}

async function switchToLastUsedTab(senderTab) {
  await historyReady;

  if (!senderTab || !Number.isInteger(senderTab.id) || !Number.isInteger(senderTab.windowId)) {
    return { ok: false, reason: "missing-sender-tab" };
  }

  const currentTabId = senderTab.id;
  const windowId = senderTab.windowId;

  for (const tabId of getCandidateTabIds(windowId, currentTabId)) {
    try {
      const tab = await chrome.tabs.get(tabId);
      if (tab.windowId !== windowId) {
        await forgetTab(tabId);
        continue;
      }

      await chrome.tabs.update(tabId, { active: true });
      await chrome.windows.update(windowId, { focused: true });
      return { ok: true };
    } catch (_error) {
      await forgetTab(tabId);
    }
  }

  return { ok: false, reason: "no-previous-tab" };
}

chrome.tabs.onActivated.addListener(({ tabId, windowId }) => {
  rememberTab(windowId, tabId).catch(() => {});
});

chrome.tabs.onRemoved.addListener((tabId) => {
  forgetTab(tabId).catch(() => {});
});

chrome.windows.onRemoved.addListener((windowId) => {
  forgetWindow(windowId).catch(() => {});
});

chrome.runtime.onInstalled.addListener(() => {
  seedActiveTabs().catch(() => {});
});

chrome.runtime.onStartup.addListener(() => {
  seedActiveTabs().catch(() => {});
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== SWITCH_TO_LAST_USED_TAB) {
    return false;
  }

  switchToLastUsedTab(sender.tab)
    .then(sendResponse)
    .catch(() => sendResponse({ ok: false, reason: "switch-failed" }));
  return true;
});
