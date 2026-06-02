// ==UserScript==
// @name         Torn Racing Spy
// @namespace    https://github.com/live-commentary-agent
// @version      0.4
// @description  Parses live Torn race state and streams structured data to local commentary server
// @author       live-commentary-agent
// @match        https://www.torn.com/*
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const SERVER  = 'http://localhost:8766/data';
    const MAX_LOG = 60;

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    const logEntries = [];
    let lastStateJson = '';   // dedup: only send when state actually changed
    let sending = false;
    const sendQueue = [];

    // -----------------------------------------------------------------------
    // Parse live race state from DOM
    // Returns null if not on an active racing page
    // -----------------------------------------------------------------------
    function parseRaceState() {
        const scrollbar = document.getElementById('drivers-scrollbar');
        if (!scrollbar) return null;  // not on racing page / race not started

        const state = {
            ts:       Date.now(),
            track:    null,
            laps:     null,
            status:   null,
            drivers:  [],
            my_info:  null,
        };

        // --- Header: "Docks - 5 laps - Race started" ---
        const headerEl = document.querySelector('.drivers-list');
        if (headerEl) {
            const firstLine = (headerEl.innerText || '').split('\n')[0].trim();
            const m = firstLine.match(/^(.+?)\s*[-–]\s*(\d+)\s*laps?\s*[-–]\s*(.+)$/i);
            if (m) {
                state.track  = m[1].trim();
                state.laps   = parseInt(m[2], 10);
                state.status = m[3].trim();
            } else {
                state.track = firstLine || null;
            }
        }

        // --- Driver list: each ul.driver-item → "Name\nXX.XX%" ---
        const driverEls = scrollbar.querySelectorAll('ul[class*="driver-item"]');
        driverEls.forEach((el, idx) => {
            const lines = (el.innerText || '').trim().split('\n').map(l => l.trim()).filter(Boolean);
            if (!lines.length) return;
            const name       = lines[0];
            const raw        = lines[1] ? parseFloat(lines[1]) : NaN;
            const completion = isNaN(raw) ? null : raw;
            state.drivers.push({ position: idx + 1, name, completion });
        });

        // --- My own data from track-wrap ---
        const trackWrap = document.querySelector('.track-wrap');
        if (trackWrap) {
            const txt = trackWrap.innerText || '';
            const get = (label) => {
                const m = txt.match(new RegExp(label + '[:\\s]+([^\\n]+)', 'i'));
                return m ? m[1].trim() : null;
            };
            const compRaw = get('Completion');
            state.my_info = {
                name:       get('Name'),
                position:   get('Position'),
                lap:        get('Lap'),
                last_lap:   get('Last Lap'),
                completion: compRaw ? parseFloat(compRaw) : null,
            };
        }

        return state;
    }

    // -----------------------------------------------------------------------
    // Record + send
    // -----------------------------------------------------------------------
    function record(type, data) {
        const entry = { type, ts: Date.now(), data };
        logEntries.unshift(entry);
        if (logEntries.length > MAX_LOG) logEntries.pop();
        renderPanel();
        enqueue(entry);
    }

    function enqueue(entry) {
        sendQueue.push(entry);
        if (!sending) flush();
    }

    function flush() {
        if (!sendQueue.length) { sending = false; return; }
        sending = true;
        const batch = sendQueue.splice(0, 10);
        GM_xmlhttpRequest({
            method:  'POST',
            url:     SERVER,
            headers: { 'Content-Type': 'application/json' },
            data:    JSON.stringify(batch),
            onload:  () => flush(),
            onerror: () => {
                updatePill('server offline', '#f80');
                setTimeout(flush, 3000);
            },
        });
    }

    // -----------------------------------------------------------------------
    // Poll + MutationObserver (race data only)
    // -----------------------------------------------------------------------
    function checkAndSend() {
        const state = parseRaceState();
        if (!state || !state.drivers.length) return;

        // Only send if something actually changed
        const key = state.drivers.map(d => `${d.name}:${d.completion}`).join('|');
        if (key === lastStateJson) return;
        lastStateJson = key;

        record('race_state', state);
    }

    // Watch the drivers scrollbar for DOM mutations (fires on every completion % update)
    function attachObserver() {
        const target = document.getElementById('drivers-scrollbar') ||
                       document.querySelector('.drivers-list');
        if (!target) return false;

        const obs = new MutationObserver(() => checkAndSend());
        obs.observe(target, { childList: true, subtree: true, characterData: true });
        return true;
    }

    // Retry attaching observer until the racing DOM loads (SPA navigation)
    let observerAttached = false;
    const pollInterval = setInterval(() => {
        checkAndSend(); // also try an immediate read
        if (!observerAttached) {
            observerAttached = attachObserver();
            if (observerAttached) updatePill('watching', '#0f0');
        }
    }, 1000);

    // -----------------------------------------------------------------------
    // Panel UI
    // -----------------------------------------------------------------------
    let panel = null;
    let panelOpen = false;
    let pill = null;

    function buildUI() {
        pill = document.createElement('div');
        pill.style.cssText = `
            position:fixed;bottom:12px;right:12px;z-index:2147483647;
            background:#111;color:#aaa;border:1px solid #444;
            padding:5px 12px;border-radius:20px;font-size:12px;
            font-family:monospace;cursor:pointer;user-select:none;
        `;
        pill.textContent = '⬤ RacingSpy';
        pill.addEventListener('click', () => {
            panelOpen = !panelOpen;
            panel.style.display = panelOpen ? 'block' : 'none';
            if (panelOpen) renderPanel();
        });
        document.body.appendChild(pill);

        panel = document.createElement('div');
        panel.style.cssText = `
            position:fixed;bottom:48px;right:12px;z-index:2147483646;
            width:420px;max-height:440px;overflow-y:auto;
            background:#0a0a0a;color:#ccc;border:1px solid #0f0;
            font-family:monospace;font-size:11px;display:none;
            border-radius:6px;box-shadow:0 4px 20px rgba(0,255,0,.15);
        `;

        const hdr = document.createElement('div');
        hdr.style.cssText = 'padding:6px 10px;background:#111;border-bottom:1px solid #0f0;display:flex;justify-content:space-between;position:sticky;top:0;';
        hdr.innerHTML = `
            <span style="color:#0f0;font-weight:bold">RacingSpy — Race State</span>
            <button id="_spy_close" style="background:#222;color:#888;border:1px solid #444;
                border-radius:3px;padding:1px 7px;cursor:pointer;font-size:10px;">✕</button>
        `;
        panel.appendChild(hdr);

        const body = document.createElement('div');
        body.id = '_spy_body';
        body.style.padding = '8px 10px';
        panel.appendChild(body);

        document.body.appendChild(panel);
        document.getElementById('_spy_close').addEventListener('click', () => {
            panelOpen = false; panel.style.display = 'none';
        });
    }

    function updatePill(status, color) {
        if (!pill) return;
        pill.textContent  = `⬤ RacingSpy — ${status}`;
        pill.style.color  = color;
        pill.style.border = `1px solid ${color}`;
    }

    function renderPanel() {
        if (!pill) return;
        // Find latest race_state
        const latest = logEntries.find(e => e.type === 'race_state');
        const count  = logEntries.filter(e => e.type === 'race_state').length;
        pill.textContent = `⬤ RacingSpy [${count} updates]`;
        pill.style.color  = '#0f0';
        pill.style.border = '1px solid #0f0';

        if (!panelOpen || !panel) return;
        const body = document.getElementById('_spy_body');
        if (!body) return;

        if (!latest) { body.innerHTML = '<div style="color:#555;padding:4px">No race data yet — join a race</div>'; return; }

        const d  = latest.data;
        const ts = new Date(latest.ts).toLocaleTimeString('en-GB', { hour12: false });

        let html = `<div style="color:#0f0;margin-bottom:6px">
            ${d.track || '?'} &nbsp;•&nbsp; ${d.laps || '?'} laps &nbsp;•&nbsp;
            <span style="color:#fa0">${d.status || '?'}</span>
            &nbsp;<span style="color:#555;font-size:10px">${ts}</span>
        </div>`;

        html += `<table style="width:100%;border-collapse:collapse">
            <tr style="color:#555;font-size:10px;border-bottom:1px solid #222">
                <td>POS</td><td>DRIVER</td><td style="text-align:right">COMPLETION</td><td style="padding-left:8px">TRACK</td>
            </tr>`;

        d.drivers.forEach(dr => {
            const pct    = dr.completion ?? 0;
            const barFill= Math.round(pct / 5);   // out of 20 chars
            const bar    = '█'.repeat(barFill) + '░'.repeat(20 - barFill);
            const isMe   = d.my_info && dr.name === d.my_info.name;
            const style  = isMe ? 'color:#fa0' : 'color:#ccc';
            html += `<tr style="${style};border-bottom:1px solid #111">
                <td style="padding:3px 4px">${dr.position}</td>
                <td style="padding:3px 4px">${dr.name}${isMe ? ' ★' : ''}</td>
                <td style="text-align:right;padding:3px 4px">${dr.completion != null ? dr.completion.toFixed(2) + '%' : '?'}</td>
                <td style="padding:3px 8px;font-size:9px;color:#0a0">${bar}</td>
            </tr>`;
        });

        html += '</table>';

        if (d.my_info) {
            html += `<div style="margin-top:8px;color:#555;font-size:10px;border-top:1px solid #222;padding-top:6px">
                My lap: ${d.my_info.lap || '?'} &nbsp;•&nbsp;
                Last lap: ${d.my_info.last_lap || '?'} &nbsp;•&nbsp;
                Position: ${d.my_info.position || '?'}
            </div>`;
        }

        body.innerHTML = html;
    }

    // -----------------------------------------------------------------------
    // Boot
    // -----------------------------------------------------------------------
    if (document.body) {
        buildUI();
        updatePill('waiting for race', '#888');
        record('connected', { href: location.href });
    } else {
        document.addEventListener('DOMContentLoaded', () => {
            buildUI();
            updatePill('waiting for race', '#888');
            record('connected', { href: location.href });
        });
    }

})();
