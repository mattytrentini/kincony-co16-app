"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const refreshButton = byId("refresh-button");
  const refreshMessage = byId("refresh-message");
  const statusPanel = byId("status-panel");
  const ioPanel = byId("io-panel");
  let refreshing = false;
  let statusReadAt = null;
  let ioReadAt = null;

  function createChannels(id) {
    const list = byId(id);
    const channels = [];
    for (let index = 0; index < 16; index += 1) {
      const channel = document.createElement("li");
      channel.className = "channel";
      channel.dataset.value = "unknown";
      const number = document.createElement("span");
      number.className = "channel-number";
      number.textContent = "CH " + (index + 1);
      const state = document.createElement("span");
      state.className = "channel-state";
      state.textContent = "Unknown";
      channel.append(number, state);
      list.append(channel);
      channels.push({ channel, state });
    }
    return channels;
  }

  const relays = createChannels("relay-channels");
  const inputs = createChannels("input-channels");

  function updateChannels(channels, values, activeText, inactiveText) {
    channels.forEach(({ channel, state }, index) => {
      channel.dataset.value = values[index] ? "active" : "inactive";
      state.textContent = values[index] ? activeText : inactiveText;
    });
  }

  function timeLabel(date) {
    return date.toLocaleTimeString();
  }

  async function readAPI(path, label) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(path, {
        method: "GET",
        cache: "no-store",
        signal: controller.signal
      });
      if (!response.ok) {
        const error = label === "I/O" && response.status === 503
          ? "Board I/O could not be read (HTTP 503)."
          : label + " request failed (HTTP " + response.status + ").";
        return { ok: false, error };
      }
      const data = await response.json();
      return { ok: true, data };
    } catch (error) {
      return {
        ok: false,
        error: error.name === "AbortError"
          ? label + " request timed out. Check the board connection."
          : label + " request could not be completed. Check the board connection."
      };
    } finally {
      clearTimeout(timeout);
    }
  }

  function showStatus(result) {
    if (!result.ok) {
      statusPanel.dataset.state = "stale";
      byId("status-freshness").textContent = statusReadAt ? "Stale" : "Unavailable";
      byId("status-message").textContent = result.error + (statusReadAt
        ? " Showing last successful read at " + timeLabel(statusReadAt) + "."
        : " No board status is available.");
      return;
    }
    const data = result.data;
    byId("device-model").textContent = data.device.model;
    byId("firmware").textContent = data.device.firmware;
    byId("network-interface").textContent = data.network.interface;
    byId("network-connection").textContent = data.network.connected ? "Connected" : "Disconnected";
    byId("ipv4").textContent = data.network.ipv4 || "Not assigned";
    byId("heap-free").textContent = data.heap_free_bytes.toLocaleString() + " bytes";
    byId("app-name").textContent = data.app.name;
    byId("app-version").textContent = data.app.version;
    statusReadAt = new Date();
    statusPanel.dataset.state = "fresh";
    byId("status-freshness").textContent = "Current";
    byId("status-message").textContent = "Last successful read at " + timeLabel(statusReadAt) + ".";
  }

  function showIO(result) {
    if (!result.ok) {
      ioPanel.dataset.state = "stale";
      byId("io-freshness").textContent = ioReadAt ? "Stale" : "Unavailable";
      byId("io-message").textContent = result.error + (ioReadAt
        ? " Channel states are stale; last successful read at " + timeLabel(ioReadAt) + "."
        : " No channel data is available.");
      return;
    }
    updateChannels(relays, result.data.relays.on, "On", "Off");
    updateChannels(inputs, result.data.inputs.active, "Active", "Inactive");
    ioReadAt = new Date();
    ioPanel.dataset.state = "fresh";
    byId("io-freshness").textContent = "Current";
    byId("io-message").textContent = "Last successful read at " + timeLabel(ioReadAt) + ".";
  }

  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    refreshButton.disabled = true;
    refreshButton.textContent = "Refreshing…";
    statusPanel.setAttribute("aria-busy", "true");
    ioPanel.setAttribute("aria-busy", "true");
    try {
      const [status, io] = await Promise.all([
        readAPI("/api/v1/status", "Status"),
        readAPI("/api/v1/io", "I/O")
      ]);
      showStatus(status);
      showIO(io);
      refreshMessage.classList.toggle("has-error", !status.ok || !io.ok);
      if (status.ok && io.ok) {
        refreshMessage.textContent = "Status and I/O updated at " + timeLabel(ioReadAt) + ".";
      } else if (status.ok) {
        refreshMessage.textContent = "Board status updated. " + io.error;
      } else if (io.ok) {
        refreshMessage.textContent = "I/O updated. " + status.error;
      } else {
        refreshMessage.textContent = status.error + " " + io.error;
      }
    } finally {
      refreshing = false;
      refreshButton.disabled = false;
      refreshButton.textContent = "Refresh";
      statusPanel.setAttribute("aria-busy", "false");
      ioPanel.setAttribute("aria-busy", "false");
    }
  }

  refreshButton.addEventListener("click", refresh);
  setInterval(refresh, 5000);
  refresh();
})();
