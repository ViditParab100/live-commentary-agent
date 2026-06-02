// ==UserScript==
// @name         Torn Racing Spy
// @namespace    https://github.com/live-commentary-agent
// @version      0.5
// @description  Live race map view + leaderboard overlay for Torn City Racing
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
    // Driver colours — assigned by leaderboard position index
    // -----------------------------------------------------------------------
    const COLORS = ['#ff4444','#44aaff','#44ff88','#ffaa00','#ff44ff','#44ffff'];

    // -----------------------------------------------------------------------
    // SVG track path — a generic oval circuit (clockwise, 0% = bottom-centre)
    // Viewbox 260×170.  Tune per track later.
    // -----------------------------------------------------------------------
    const MAP_W = 260, MAP_H = 170;
    const TRACK_PATH = 'M 130,155 C 200,155 240,135 240,100 C 240,55 200,15 130,15 C 60,15 20,55 20,100 C 20,135 60,155 130,155 Z';

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    const logEntries = [];
    let lastKey  = '';
    let sending  = false;
    const sendQueue = [];
    let svgDrivers = {};     // name → { g, circle, label }
    let trackPathEl = null;

    // -----------------------------------------------------------------------
    // Race state parser
    // -----------------------------------------------------------------------
    function parseRaceState() {
        const scrollbar = document.getElementById('drivers-scrollbar');
        if (!scrollbar) return null;

        const state = { ts: Date.now(), track: null, laps: null, status: null, drivers: [], my_info: null };

        const headerEl = document.querySelector('.drivers-list');
        if (headerEl) {
            const firstLine = (headerEl.innerText || '').split('\n')[0].trim();
            const m = firstLine.match(/^(.+?)\s*[-–]\s*(\d+)\s*laps?\s*[-–]\s*(.+)$/i);
            if (m) { state.track = m[1].trim(); state.laps = parseInt(m[2], 10); state.status = m[3].trim(); }
        }

        scrollbar.querySelectorAll('ul[class*="driver-item"]').forEach((el, idx) => {
            const lines = (el.innerText || '').trim().split('\n').map(l => l.trim()).filter(Boolean);
            if (!lines.length) return;
            const name = lines[0];
            const raw  = lines[1] ? parseFloat(lines[1]) : NaN;
            state.drivers.push({ position: idx + 1, name, completion: isNaN(raw) ? null : raw });
        });

        const wrap = document.querySelector('.track-wrap');
        if (wrap) {
            const txt = wrap.innerText || '';
            const g = (label) => { const m = txt.match(new RegExp(label + '[:\\s]+([^\\n]+)', 'i')); return m ? m[1].trim() : null; };
            state.my_info = { name: g('Name'), position: g('Position'), lap: g('Lap'), last_lap: g('Last Lap'), completion: parseFloat(g('Completion') || '') || null };
        }

        return state;
    }

    // -----------------------------------------------------------------------
    // Send to server
    // -----------------------------------------------------------------------
    function record(type, data) {
        logEntries.unshift({ type, ts: Date.now(), data });
        if (logEntries.length > MAX_LOG) logEntries.pop();
        renderAll();
        enqueue({ type, ts: Date.now(), data });
    }

    function enqueue(entry) {
        sendQueue.push(entry);
        if (!sending) flush();
    }

    function flush() {
        if (!sendQueue.length) { sending = false; return; }
        sending = true;
        GM_xmlhttpRequest({
            method: 'POST', url: SERVER,
            headers: { 'Content-Type': 'application/json' },
            data: JSON.stringify(sendQueue.splice(0, 10)),
            onload:  () => flush(),
            onerror: () => { setPillStatus('server offline', '#f80'); setTimeout(flush, 3000); },
        });
    }

    // -----------------------------------------------------------------------
    // Observer + polling
    // -----------------------------------------------------------------------
    function checkAndSend() {
        const state = parseRaceState();
        if (!state || !state.drivers.length) return;
        const key = state.drivers.map(d => `${d.name}:${d.completion}`).join('|');
        if (key === lastKey) return;
        lastKey = key;
        record('race_state', state);
    }

    let observerAttached = false;
    setInterval(() => {
        checkAndSend();
        if (!observerAttached) {
            const target = document.getElementById('drivers-scrollbar');
            if (target) {
                new MutationObserver(checkAndSend).observe(target, { childList: true, subtree: true, characterData: true });
                observerAttached = true;
                setPillStatus('watching', '#0f0');
            }
        }
    }, 1000);

    // -----------------------------------------------------------------------
    // Build UI
    // -----------------------------------------------------------------------
    let pill = null, panel = null, panelOpen = false;

    function buildUI() {
        // Pill
        pill = el('div', {
            style: `position:fixed;bottom:12px;right:12px;z-index:2147483647;
                    background:#111;color:#888;border:1px solid #444;
                    padding:5px 14px;border-radius:20px;font-size:12px;
                    font-family:monospace;cursor:pointer;user-select:none;`,
            textContent: '⬤ RacingSpy',
            onclick: togglePanel,
        });
        document.body.appendChild(pill);

        // Panel
        panel = el('div', {
            style: `position:fixed;bottom:48px;right:12px;z-index:2147483646;
                    width:500px;background:#0d0d0d;border:1px solid #0f0;
                    border-radius:8px;font-family:monospace;font-size:11px;
                    display:none;box-shadow:0 4px 24px rgba(0,255,0,.12);`,
        });

        // Header bar
        const hdr = el('div', {
            style: `padding:7px 12px;background:#111;border-bottom:1px solid #0f0;
                    display:flex;justify-content:space-between;align-items:center;
                    border-radius:8px 8px 0 0;`,
        });
        hdr.innerHTML = `
            <span style="color:#0f0;font-weight:bold;font-size:12px">⬤ RacingSpy</span>
            <span id="_spy_header_info" style="color:#888;font-size:11px"></span>
            <button id="_spy_close" style="background:#1a1a1a;color:#888;border:1px solid #333;
                border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px;">✕</button>
        `;
        panel.appendChild(hdr);

        // Body: map (left) + leaderboard (right)
        const body = el('div', { style: 'display:flex;padding:10px;gap:10px;' });

        // --- SVG map ---
        const mapWrap = el('div', { style: 'flex:0 0 auto;' });
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', `0 0 ${MAP_W} ${MAP_H}`);
        svg.setAttribute('width', MAP_W);
        svg.setAttribute('height', MAP_H);
        svg.style.cssText = 'display:block;background:#111;border-radius:6px;border:1px solid #1a1a1a;';

        // Track fill (inner area, darker)
        const trackFill = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        trackFill.setAttribute('d', TRACK_PATH);
        trackFill.setAttribute('fill', '#161616');
        trackFill.setAttribute('stroke', 'none');
        svg.appendChild(trackFill);

        // Track outline
        const trackOutline = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        trackOutline.setAttribute('d', TRACK_PATH);
        trackOutline.setAttribute('fill', 'none');
        trackOutline.setAttribute('stroke', '#2a5a2a');
        trackOutline.setAttribute('stroke-width', '12');
        trackOutline.setAttribute('stroke-linejoin', 'round');
        svg.appendChild(trackOutline);

        // Track centreline (dashed)
        const trackLine = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        trackLine.id = '_spy_track_path';
        trackLine.setAttribute('d', TRACK_PATH);
        trackLine.setAttribute('fill', 'none');
        trackLine.setAttribute('stroke', '#1e3a1e');
        trackLine.setAttribute('stroke-width', '1');
        trackLine.setAttribute('stroke-dasharray', '4 4');
        svg.appendChild(trackLine);
        trackPathEl = trackLine;

        // Start/finish line at 0% (bottom centre of oval)
        const sfLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        sfLine.setAttribute('x1', '118'); sfLine.setAttribute('y1', '150');
        sfLine.setAttribute('x2', '142'); sfLine.setAttribute('y2', '160');
        sfLine.setAttribute('stroke', '#fff');
        sfLine.setAttribute('stroke-width', '2');
        svg.appendChild(sfLine);

        // Driver layer (circles go here, on top of track)
        const driverLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        driverLayer.id = '_spy_driver_layer';
        svg.appendChild(driverLayer);

        mapWrap.appendChild(svg);
        body.appendChild(mapWrap);

        // --- Leaderboard ---
        const lb = el('div', { id: '_spy_lb', style: 'flex:1;overflow:hidden;' });
        body.appendChild(lb);

        panel.appendChild(body);

        // Footer
        const footer = el('div', { id: '_spy_footer', style: 'padding:5px 12px 8px;color:#444;font-size:10px;border-top:1px solid #1a1a1a;' });
        panel.appendChild(footer);

        document.body.appendChild(panel);
        document.getElementById('_spy_close').addEventListener('click', () => { panelOpen = false; panel.style.display = 'none'; });
    }

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------
    function renderAll() {
        if (!pill) return;
        const updates = logEntries.filter(e => e.type === 'race_state').length;
        pill.textContent = `⬤ RacingSpy [${updates}]`;
        pill.style.color  = '#0f0';
        pill.style.border = '1px solid #0f0';

        if (!panelOpen) return;

        const latest = logEntries.find(e => e.type === 'race_state');
        if (!latest) return;

        renderMap(latest.data);
        renderLeaderboard(latest.data);
        renderFooter(latest.data);
    }

    function renderMap(state) {
        if (!trackPathEl) return;
        const layer = document.getElementById('_spy_driver_layer');
        if (!layer) return;

        const totalLen = trackPathEl.getTotalLength();
        const myName   = state.my_info?.name;

        state.drivers.forEach((d, idx) => {
            const pct   = (d.completion ?? 0) / 100;
            const pt    = trackPathEl.getPointAtLength(pct * totalLen);
            const color = COLORS[idx % COLORS.length];
            const isMe  = d.name === myName;

            let g = svgDrivers[d.name]?.g;

            if (!g) {
                // Create group for this driver
                g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                g.style.transition = 'transform 0.7s ease-out';

                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('r', isMe ? '7' : '5');
                circle.setAttribute('fill', color);
                circle.setAttribute('stroke', isMe ? '#fff' : '#000');
                circle.setAttribute('stroke-width', isMe ? '2' : '1');

                const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                label.setAttribute('text-anchor', 'middle');
                label.setAttribute('dy', '0.35em');
                label.setAttribute('font-size', '7');
                label.setAttribute('font-family', 'monospace');
                label.setAttribute('fill', isMe ? '#000' : '#fff');
                label.setAttribute('font-weight', 'bold');
                label.setAttribute('pointer-events', 'none');
                label.textContent = String(d.position);

                // Tooltip: driver name on hover
                const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
                title.textContent = `${d.name} — ${d.completion?.toFixed(1) ?? '?'}%`;

                g.appendChild(circle);
                g.appendChild(label);
                g.appendChild(title);
                layer.appendChild(g);

                svgDrivers[d.name] = { g, circle, label };
            }

            // Update label and completion tooltip
            svgDrivers[d.name].label.textContent = String(d.position);
            const titleEl = g.querySelector('title');
            if (titleEl) titleEl.textContent = `${d.name} — ${d.completion?.toFixed(1) ?? '?'}%`;

            // Animate to new position
            g.setAttribute('transform', `translate(${pt.x.toFixed(1)}, ${pt.y.toFixed(1)})`);
        });

        // Remove drivers no longer in the race
        for (const name of Object.keys(svgDrivers)) {
            if (!state.drivers.find(d => d.name === name)) {
                svgDrivers[name].g.remove();
                delete svgDrivers[name];
            }
        }
    }

    function renderLeaderboard(state) {
        const lb = document.getElementById('_spy_lb');
        if (!lb) return;
        const myName = state.my_info?.name;

        let html = '';
        state.drivers.forEach((d, idx) => {
            const color  = COLORS[idx % COLORS.length];
            const isMe   = d.name === myName;
            const pct    = d.completion ?? 0;
            const barW   = Math.round(pct / 100 * 80);  // max 80px
            const name   = d.name.length > 14 ? d.name.slice(0, 13) + '…' : d.name;
            html += `
                <div style="margin-bottom:5px;">
                    <div style="display:flex;align-items:center;gap:5px;margin-bottom:2px;">
                        <span style="color:${color};font-size:9px;">●</span>
                        <span style="color:${isMe ? '#ffaa00' : '#ccc'};flex:1;overflow:hidden;white-space:nowrap;">
                            ${d.position}. ${name}${isMe ? ' ★' : ''}
                        </span>
                        <span style="color:#888;font-size:10px;">${d.completion != null ? d.completion.toFixed(2) + '%' : '?'}</span>
                    </div>
                    <div style="background:#1a1a1a;border-radius:2px;height:3px;width:100%;">
                        <div style="background:${color};height:3px;width:${barW}px;border-radius:2px;transition:width 0.7s ease-out;"></div>
                    </div>
                </div>`;
        });
        lb.innerHTML = html;
    }

    function renderFooter(state) {
        const footer = document.getElementById('_spy_footer');
        if (!footer || !state.my_info) return;
        const mi = state.my_info;
        footer.textContent = `Lap ${mi.lap ?? '?'}  ·  Last lap ${mi.last_lap ?? '?'}  ·  Position ${mi.position ?? '?'}`;
    }

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------
    function togglePanel() {
        panelOpen = !panelOpen;
        panel.style.display = panelOpen ? 'block' : 'none';
        if (panelOpen) renderAll();
    }

    function setPillStatus(status, color) {
        if (!pill) return;
        pill.textContent  = `⬤ RacingSpy — ${status}`;
        pill.style.color  = color;
        pill.style.border = `1px solid ${color}`;
    }

    function el(tag, props = {}) {
        const e = document.createElement(tag);
        Object.entries(props).forEach(([k, v]) => {
            if (k === 'style')   e.style.cssText = v;
            else if (k === 'onclick') e.addEventListener('click', v);
            else e[k] = v;
        });
        return e;
    }

    // -----------------------------------------------------------------------
    // Boot
    // -----------------------------------------------------------------------
    function boot() {
        buildUI();
        setPillStatus('waiting for race', '#888');
        record('connected', { href: location.href });
    }

    document.body ? boot() : document.addEventListener('DOMContentLoaded', boot);

})();
