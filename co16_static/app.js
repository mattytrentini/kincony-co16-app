"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const refreshButton = byId("refresh-button");
  const refreshMessage = byId("refresh-message");
  const relayMessage = byId("relay-message");
  const ioStaleAfter = 10000;
  const resources = {};
  for (const name of ["status", "io", "clock"]) {
    resources[name] = {
      panel: byId(name + "-panel"),
      freshness: byId(name + "-freshness"),
      message: byId(name + "-message"),
      readAt: null,
      busy: false,
      error: null
    };
  }
  let ioCurrent = false;
  let confirmedRelays = null;
  let mutating = false;
  let pendingRelay = null;
  let pendingOn = null;
  let writeStarted = false;

  function createChannels(id, controllable) {
    const list = byId(id);
    const channels = [];
    for (let index = 0; index < 16; index += 1) {
      const item = document.createElement("li");
      const channel = controllable ? document.createElement("button") : item;
      channel.className = controllable ? "channel relay-control" : "channel";
      channel.dataset.value = "unknown";
      const number = document.createElement("span");
      number.className = "channel-number";
      number.textContent = "CH " + (index + 1);
      const state = document.createElement("span");
      state.className = "channel-state";
      state.textContent = "Unknown";
      channel.append(number, state);
      let pending = null;
      if (controllable) {
        channel.type = "button";
        channel.disabled = true;
        channel.dataset.channel = String(index + 1);
        channel.setAttribute("aria-pressed", "mixed");
        channel.setAttribute("aria-describedby", "io-message relay-message");
        channel.addEventListener("click", () => setRelay(index));
        pending = document.createElement("span");
        pending.className = "channel-pending";
        pending.textContent = "Pending…";
        pending.hidden = true;
        channel.append(pending);
        item.append(channel);
      }
      list.append(item);
      channels.push({ channel, state, pending });
    }
    return channels;
  }

  const relays = createChannels("relay-channels", true);
  const inputs = createChannels("input-channels", false);

  function updateChannels(channels, values, activeText, inactiveText) {
    channels.forEach(({ channel, state }, index) => {
      channel.dataset.value = values[index] ? "active" : "inactive";
      state.textContent = values[index] ? activeText : inactiveText;
    });
  }

  function timeLabel(date) {
    return date.toLocaleTimeString();
  }

  function usableIO() {
    return ioCurrent && confirmedRelays !== null
      && Date.now() - resources.io.readAt.getTime() <= ioStaleAfter;
  }

  function syncControls() {
    const blocked = resources.io.busy || mutating || !usableIO();
    relays.forEach(({ channel, pending }, index) => {
      const value = confirmedRelays === null ? "unknown" : confirmedRelays[index] ? "on" : "off";
      const isPending = pendingRelay === index;
      channel.disabled = blocked;
      channel.dataset.pending = String(isPending);
      channel.setAttribute("aria-busy", String(isPending));
      channel.setAttribute("aria-pressed", confirmedRelays === null ? "mixed" : String(confirmedRelays[index]));
      pending.hidden = !isPending;
      let label = "Relay " + (index + 1) + ", " + value + ".";
      if (isPending) {
        label += " Pending " + (pendingOn ? "on" : "off") + " write; awaiting hardware readback.";
      } else if (blocked) {
        label += " Control paused until fresh I/O is available and no read or write is pending.";
      } else {
        label += " Turn " + (confirmedRelays[index] ? "off" : "on") + ".";
      }
      channel.setAttribute("aria-label", label);
    });
    // Only I/O work gates relay controls; a slow clock/status read must not gate them.
    refreshButton.disabled = resources.io.busy || mutating;
    refreshButton.textContent = mutating ? "Writing…" : resources.io.busy ? "Refreshing…" : "Refresh";
    for (const [name, resource] of Object.entries(resources)) {
      resource.panel.setAttribute("aria-busy", String(resource.busy || (name === "io" && mutating)));
    }
    const reading = Object.entries(resources).filter(([, resource]) => resource.busy).map(([name]) => name === "io" ? "I/O" : name);
    const failed = Object.entries(resources).filter(([, resource]) => resource.error).map(([name]) => name === "io" ? "I/O" : name);
    refreshMessage.classList.toggle("has-error", failed.length > 0);
    if (mutating) {
      refreshMessage.textContent = "Relay write pending. Controls stay locked until hardware readback completes.";
    } else if (reading.length) {
      refreshMessage.textContent = "Reading " + reading.join(", ") + "… Each panel updates independently.";
    } else if (failed.length) {
      refreshMessage.textContent = "Could not refresh " + failed.join(", ") + ". See each panel for its own freshness and error.";
    } else {
      refreshMessage.textContent = "Board readings updated. Refreshes every 5 seconds; the clock shows its last received value.";
    }
  }

  async function requestAPI(path, label, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const options = {
      method: body === undefined ? "GET" : "POST",
      cache: "no-store",
      signal: controller.signal
    };
    if (body !== undefined) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(body);
    }
    try {
      const response = await fetch(path, options);
      if (!response.ok) {
        return { ok: false, error: label + " request failed (HTTP " + response.status + ")." };
      }
      return { ok: true, data: await response.json() };
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

  function showFailure(name, error) {
    const resource = resources[name];
    resource.error = error;
    resource.panel.dataset.state = "stale";
    resource.freshness.textContent = resource.readAt ? "Stale" : "Unavailable";
    resource.message.textContent = error + (resource.readAt
      ? " Showing last successful read received at " + timeLabel(resource.readAt) + " (browser time)."
      : " No successful read is available.");
    if (name === "io") {
      ioCurrent = false;
      resource.message.textContent += " Relay controls are disabled until a fresh I/O read succeeds.";
    }
    if (name === "clock" && resource.readAt) {
      byId("clock-validity").textContent = byId("clock-validity").dataset.valid === "true"
        ? "Valid at last read" : "Invalid at last read · oscillator stop flag";
    }
  }

  function showFresh(name) {
    const resource = resources[name];
    resource.readAt = new Date();
    resource.error = null;
    resource.panel.dataset.state = "fresh";
    resource.freshness.textContent = "Current";
    resource.message.textContent = "Last successful read received at " + timeLabel(resource.readAt) + " (browser time).";
  }

  function showStatus(data) {
    byId("device-model").textContent = data.device.model;
    byId("firmware").textContent = data.device.firmware;
    byId("network-interface").textContent = data.network.interface;
    byId("network-connection").textContent = data.network.connected ? "Connected" : "Disconnected";
    byId("ipv4").textContent = data.network.ipv4 || "Not assigned";
    byId("heap-free").textContent = data.heap_free_bytes.toLocaleString() + " bytes";
    byId("app-name").textContent = data.app.name;
    byId("app-version").textContent = data.app.version;
    showFresh("status");
  }

  function booleanChannels(values) {
    return Array.isArray(values) && values.length === 16 && values.every((value) => typeof value === "boolean");
  }

  function showIO(data) {
    if (!booleanChannels(data.relays.on) || !booleanChannels(data.inputs.active)) {
      throw new Error("Invalid I/O readback");
    }
    confirmedRelays = data.relays.on.slice();
    updateChannels(relays, confirmedRelays, "On", "Off");
    updateChannels(inputs, data.inputs.active, "Active", "Inactive");
    showFresh("io");
    ioCurrent = true;
    if (!writeStarted) {
      relayMessage.textContent = "Choose a relay to switch its physical output. States are confirmed hardware readback.";
    }
  }

  function showClock(data) {
    if (data.source !== "ds3231" || typeof data.valid !== "boolean"
        || typeof data.datetime !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(data.datetime)) {
      throw new Error("Invalid clock readback");
    }
    const datetime = byId("clock-datetime");
    datetime.textContent = data.datetime;
    datetime.dateTime = data.datetime;
    byId("clock-validity").dataset.valid = String(data.valid);
    byId("clock-validity").textContent = data.valid ? "Valid" : "Invalid · oscillator stop flag";
    showFresh("clock");
    if (!data.valid) {
      resources.clock.message.textContent += " The DS3231 reports an oscillator stop; these wall-clock fields are untrusted until explicitly set through the API.";
    }
  }

  async function refreshResource(name, path, label, show) {
    const resource = resources[name];
    if (resource.busy) return null;
    resource.busy = true;
    syncControls();
    let result;
    try {
      result = await requestAPI(path, label);
      if (result.ok) {
        try {
          show(result.data);
        } catch (error) {
          result = { ok: false, error: label + " response did not contain usable readback." };
        }
      }
      if (!result.ok) showFailure(name, result.error);
      return result;
    } finally {
      resource.busy = false;
      syncControls();
    }
  }

  function refreshIO() {
    return refreshResource("io", "/api/v1/io", "I/O", showIO);
  }

  function expireIO() {
    if (ioCurrent && !usableIO()) {
      showFailure("io", "The last I/O read is more than 10 seconds old.");
      syncControls();
    }
  }

  function refresh() {
    expireIO();
    refreshResource("status", "/api/v1/status", "Status", showStatus);
    refreshResource("clock", "/api/v1/time", "Clock", showClock);
    if (!mutating) refreshIO();
  }

  async function setRelay(index) {
    expireIO();
    if (mutating || resources.io.busy || !usableIO()) return;
    const channelNumber = index + 1;
    const desired = !confirmedRelays[index];
    // Polling and writes cannot overlap: this lock is set before the first await.
    mutating = true;
    pendingRelay = index;
    pendingOn = desired;
    writeStarted = true;
    ioCurrent = false;
    resources.io.panel.dataset.state = "stale";
    resources.io.freshness.textContent = "Write pending";
    resources.io.message.textContent = "Relay write pending. Displayed channel states are the last confirmed hardware readback.";
    relayMessage.classList.remove("has-error");
    relayMessage.textContent = "Relay " + channelNumber + ": requesting " + (desired ? "on" : "off") + "; awaiting hardware confirmation…";
    syncControls();
    try {
      let result = await requestAPI("/api/v1/relays/" + channelNumber, "Relay " + channelNumber, { on: desired });
      if (result.ok && (!result.data || result.data.channel !== channelNumber || typeof result.data.on !== "boolean")) {
        result = { ok: false, error: "Relay " + channelNumber + " response did not confirm a hardware state." };
      }
      if (result.ok) {
        confirmedRelays[index] = result.data.on;
        updateChannels(relays, confirmedRelays, "On", "Off");
        relayMessage.textContent = "Relay " + channelNumber + " POST hardware readback: " + (result.data.on ? "on" : "off") + ". Refreshing all I/O…";
        syncControls();
      } else {
        relayMessage.classList.add("has-error");
        relayMessage.textContent = result.error + " The output may have changed. Re-reading I/O; the POST will not be retried automatically.";
        showFailure("io", "The relay write was not confirmed; checking hardware I/O again.");
      }
      // Always re-read I/O after a possibly applied write, never re-send the POST.
      // This read does not await or depend on either status or the DS3231 clock.
      const io = await refreshIO();
      if (result.ok) {
        relayMessage.textContent = "Relay " + channelNumber + " POST hardware readback was " + (result.data.on ? "on" : "off") + ". "
          + (io && io.ok ? "All channel states were refreshed." : "The post-write I/O read also failed; see the I/O panel for current freshness.");
      } else {
        relayMessage.textContent = result.error + " The output may have changed; no automatic POST retry was sent. "
          + (io && io.ok ? "Channel states were confirmed by a new hardware I/O read." : "The post-write I/O read also failed. Controls require a successful I/O read; see its freshness above.");
      }
    } finally {
      mutating = false;
      pendingRelay = null;
      pendingOn = null;
      syncControls();
    }
  }

  refreshButton.addEventListener("click", refresh);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
  setInterval(refresh, 5000);
  syncControls();
  refresh();
})();
