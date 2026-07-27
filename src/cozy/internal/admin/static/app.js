"use strict";

const sitesElement = document.querySelector("#sites");
const feedbackElement = document.querySelector("#feedback");
const countElement = document.querySelector("#count");
const refreshButton = document.querySelector("#refresh");
const addForm = document.querySelector("#add-form");

function feedback(message, error = false) {
  feedbackElement.textContent = message;
  feedbackElement.classList.toggle("error", error);
}

async function request(path, options) {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const data = await response.json();
      message = data.error || data.message || message;
    } catch {
      // Preserve the useful HTTP status when the response is not JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

function siteCard(site) {
  const card = document.createElement("article");
  card.className = "card";
  const top = document.createElement("div");
  top.className = "card-top";
  const title = document.createElement("h3");
  title.className = "site-name";
  title.textContent = site.name;
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = "Running";
  top.append(title, badge);
  const link = document.createElement("a");
  link.className = "site-link";
  try {
    const url = new URL(site.url || `http://${site.name}/`);
    url.port = location.port;
    link.href = url.href;
    link.textContent = url.host;
  } catch {
    link.textContent = site.name;
  }
  const process = document.createElement("p");
  process.className = "meta";
  process.textContent = `PID ${site.pid || "—"} · port ${site.port || "—"}`;
  const command = document.createElement("p");
  command.className = "meta";
  command.textContent = site.run || "No start command";
  command.title = site.run || "";
  const restart = document.createElement("button");
  restart.className = "restart";
  restart.type = "button";
  restart.textContent = "↻ Restart";
  restart.addEventListener("click", async () => {
    restart.disabled = true;
    restart.textContent = "Restarting…";
    try {
      await request(`/api/sites/${encodeURIComponent(site.name)}/restart`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      feedback(`${site.name} is feeling refreshed.`);
      await refresh();
    } catch (error) {
      feedback(error.message, true);
      restart.disabled = false;
      restart.textContent = "↻ Restart";
    }
  });
  card.append(top, link, process, command, restart);
  return card;
}

async function refresh() {
  refreshButton.disabled = true;
  try {
    const result = await request("/api/sites");
    const sites = Array.isArray(result.sites) ? result.sites : [];
    sitesElement.replaceChildren();
    if (sites.length === 0) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "The neighborhood is quiet. Invite your first service below.";
      sitesElement.append(empty);
    } else {
      sites.forEach((site) => sitesElement.append(siteCard(site)));
    }
    countElement.textContent = String(sites.length);
  } catch (error) {
    feedback(error.message, true);
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener("click", refresh);
addForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("#add-button");
  let name = document.querySelector("#name").value.trim().toLowerCase();
  const run = document.querySelector("#run").value.trim();
  if (!name.endsWith(".localhost")) name += ".localhost";
  button.disabled = true;
  button.textContent = "Making room…";
  try {
    await request("/api/sites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, run }),
    });
    addForm.reset();
    feedback(`Welcome home, ${name}!`);
    await refresh();
  } catch (error) {
    feedback(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "＋ Add to the neighborhood";
  }
});

refresh();
setInterval(refresh, 10_000);
