/* runO2 planner — talks to /run/loops, /run/report and /run/gpx.
 *
 * One rule runs through all of it: measured, modelled, forecast and unmeasured
 * are four different things and the interface never lets them look like one.
 * Colour, label and provenance row all follow the classification the API sent,
 * and a route that is 30% measured never renders as if it were 100%.
 */
'use strict';

// Wettsteinplatz, which is what the label says. The previous coordinates were
// Mittlere Bruecke, half a kilometre west of the name shown beside them.
const state = {
  lon: 7.5983, lat: 47.5606, distance: 8, pace: 6, hour: null,
  loops: [], selected: 0, layer: 'air', meta: null, report: null,
};

const $ = (id) => document.getElementById(id);

/* A fresh clone has no tram export and the API serves a synthetic field instead,
 * saying so in `air_source.fixture`. Every place that would print "measured" has
 * to print "synthetic" in that case — a fabricated number wearing the measured
 * label is the one mistake this whole project exists to avoid. */
const isSynthetic = () => Boolean(state.meta && state.meta.air_source && state.meta.air_source.fixture);
const measuredWord = () => (isSynthetic() ? 'synthetic' : 'measured');
const fmtPace = (p) => `${Math.floor(p)}:${String(Math.round((p - Math.floor(p)) * 60)).padStart(2, '0')}`;

const dateLine = new Date().toLocaleDateString('en-GB',
  { weekday: 'short', day: '2-digit', month: 'short' }).toUpperCase();
$('heroDate').textContent = dateLine;
$('sideDate').textContent = dateLine;

/* ---------- map ---------- */
const map = L.map('map', { zoomControl: false }).setView([state.lat, state.lon], 14);
L.control.zoom({ position: 'bottomleft' }).addTo(map);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19, attribution: '© OpenStreetMap contributors',
}).addTo(map);

const marker = L.marker([state.lat, state.lon], { draggable: true }).addTo(map);
let drawn = [];

marker.on('dragend', () => {
  const p = marker.getLatLng();
  state.lat = p.lat; state.lon = p.lng;
  $('startLabel').textContent = `${p.lat.toFixed(4)}, ${p.lng.toFixed(4)}`;
});
map.on('click', (e) => {
  marker.setLatLng(e.latlng);
  state.lat = e.latlng.lat; state.lon = e.latlng.lng;
  $('startLabel').textContent = `${e.latlng.lat.toFixed(4)}, ${e.latlng.lng.toFixed(4)}`;
});

/* ---------- controls ---------- */
function setDistance(km) {
  state.distance = km;
  $('dist').value = km;
  $('distValue').textContent = km.toFixed(1);
  $('distLabel').textContent = `${km.toFixed(1)} km`;
  document.querySelectorAll('#distPresets button').forEach((b) =>
    b.classList.toggle('active', Number(b.dataset.km) === km));
}
$('dist').addEventListener('input', (e) => setDistance(parseFloat(e.target.value)));
document.querySelectorAll('#distPresets button').forEach((b) =>
  b.addEventListener('click', () => setDistance(Number(b.dataset.km))));

$('pace').addEventListener('input', (e) => {
  state.pace = parseFloat(e.target.value);
  $('paceValue').textContent = fmtPace(state.pace);
  $('paceLabel').textContent = `${fmtPace(state.pace)} /km`;
});

document.querySelectorAll('#hours button').forEach((b) =>
  b.addEventListener('click', () => {
    state.hour = b.dataset.hour === '' ? null : Number(b.dataset.hour);
    document.querySelectorAll('#hours button').forEach((x) => x.classList.remove('active'));
    b.classList.add('active');
  }));

document.querySelectorAll('#layerToggle button').forEach((b) =>
  b.addEventListener('click', () => {
    state.layer = b.dataset.layer;
    document.querySelectorAll('#layerToggle button').forEach((x) => x.classList.remove('active'));
    b.classList.add('active');
    drawRoutes();
  }));

$('planBtn').addEventListener('click', loadLoops);

/* ---------- loading routes ---------- */
function query() {
  const p = new URLSearchParams({
    lon: state.lon, lat: state.lat,
    distance_m: Math.round(state.distance * 1000),
    pace_min_per_km: state.pace,
  });
  if (state.hour !== null) p.set('hour', state.hour);
  return p;
}

async function loadLoops() {
  const btn = $('planBtn');
  btn.disabled = true; btn.textContent = 'FINDING ROUTES…';
  $('routeResults').innerHTML = '';
  try {
    const res = await fetch('/run/loops?' + query());
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      showNotice(`<strong style="color:var(--orange)">No route.</strong> ${body.detail}`);
      return;
    }
    const data = await res.json();
    state.loops = data.loops;
    state.selected = 0;
    state.meta = data;
    renderCards();
    drawRoutes();
    showCoverageNotice(data);
    loadConditions();
  } catch (err) {
    showNotice(`Could not reach the planner: ${err}`);
  } finally {
    btn.disabled = false; btn.textContent = 'FIND 3 ROUTES →';
  }
}

function showNotice(html) { const n = $('notice'); n.hidden = false; n.innerHTML = html; }

function showCoverageNotice(data) {
  const cov = data.network_coverage;
  const bits = [];
  if (data.air_source && data.air_source.fixture) {
    bits.push(`<strong style="color:var(--orange)">${data.air_source.warning}</strong>`);
  } else if (data.air_source) {
    const w = data.air_source.measurement_window;
    bits.push(`Measured air: dataset ${data.air_source.dataset}, ${data.air_source.readings_total.toLocaleString('de-CH')} readings`
      + (w ? ` from ${w.first_month} to ${w.last_month} — a closed campaign, not today's air.` : '.'));
  }
  bits.push(`Tram sensors cover <b>${(cov.length_share * 100).toFixed(0)}%</b> of the walking network by length.
             The rest is unmeasured — shown as unmeasured, never as clean.`);
  if (data.ranked_by) bits.push(`Ranked by ${data.ranked_by}.`);
  showNotice(bits.join(' '));
}

/* ---------- route cards ---------- */
/* Two seconds to read: what it is, how far, how long, its air score, how much of
 * it anyone has actually measured. Everything else lives in the report. */
function renderCards() {
  const el = $('routeResults');
  el.innerHTML = '';
  state.loops.forEach((loop, i) => {
    const ex = loop.exposure;
    const measured = ex.coverage.measured_share;
    const card = document.createElement('div');
    card.className = 'route-card' + (i === state.selected ? ' active' : '');
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-pressed', i === state.selected);
    card.innerHTML = `
      <div class="route-head">
        <span class="route-name">${i === 0 ? 'BEST MATCH' : 'ALTERNATIVE ' + i}</span>
        <span class="rank">${i === 0 ? 'lowest modelled NO₂' : ''}</span>
      </div>
      <div class="route-size">
        <b>${loop.distance_km.toFixed(1)} km</b>
        <i>${Math.round(ex.parameters.duration_min)} min</i>
      </div>
      <div class="route-score">
        <b>${ex.baseline.mean ?? '—'}<s>µg/m³ NO₂</s></b>
        <span>air score · modelled</span>
      </div>
      <div class="coverage-bar" role="img"
           aria-label="${Math.round(measured * 100)} percent of this route was ${measuredWord()}">
        <i style="width:${measured * 100}%;background:${isSynthetic() ? 'var(--orange)' : 'var(--green)'}"></i>
        <i style="width:${(1 - measured) * 100}%;background:#3B4A4C"></i>
      </div>
      <div class="route-note">
        <strong>${(measured * 100).toFixed(0)}% ${measuredWord()}</strong>${
          ex.mean_concentration !== null
            ? ` · ${ex.mean_concentration} µg/m³ PM2.5 there`
            : ' · no sensor ever passed'} · rest unmeasured
      </div>`;
    const choose = () => { state.selected = i; renderCards(); drawRoutes(); };
    card.addEventListener('click', choose);
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(); }
    });
    el.appendChild(card);
  });
  const go = document.createElement('button');
  go.className = 'plan-btn';
  go.textContent = 'REVIEW THIS RUN →';
  go.addEventListener('click', openReport);
  el.appendChild(go);
}

/* ---------- drawing ---------- */
const COLOURS = {
  measured: '#4E9E86', unmeasured: '#4a5b5e', quiet: '#33474c',
};

function noToColour(v) {
  if (v === null || v === undefined) return COLOURS.unmeasured;
  // NO2 across Basel runs roughly 11–35 ug/m3 on the walking network.
  const t = Math.max(0, Math.min(1, (v - 11) / 24));
  const stops = [[78, 158, 134], [201, 162, 39], [214, 48, 31]];
  const i = t < 0.5 ? 0 : 1;
  const f = t < 0.5 ? t * 2 : (t - 0.5) * 2;
  const c = stops[i].map((a, k) => Math.round(a + (stops[i + 1][k] - a) * f));
  return `rgb(${c.join(',')})`;
}

function drawRoutes() {
  drawn.forEach((l) => map.removeLayer(l));
  drawn = [];
  state.loops.forEach((loop, i) => {
    const chosen = i === state.selected;
    const coords = loop.coordinates;
    loop.segments.forEach((seg, s) => {
      if (s + 1 >= coords.length) return;
      const a = coords[s], b = coords[s + 1];
      const isMeasured = seg.classification === 'measured';
      let colour, weight, dash = null;
      if (!chosen) {
        colour = COLOURS.quiet; weight = 2;
      } else if (state.layer === 'air') {
        colour = noToColour(seg.baseline_no2); weight = 6;
      } else if (state.layer === 'measured') {
        colour = isMeasured ? COLOURS.measured : COLOURS.unmeasured;
        weight = isMeasured ? 6 : 4;
        dash = isMeasured ? null : '3 7';
      } else {
        colour = '#DCE5E2'; weight = 5;
      }
      const line = L.polyline([[a[1], a[0]], [b[1], b[0]]], {
        color: colour, weight, opacity: chosen ? 0.95 : 0.5,
        dashArray: dash, lineCap: 'round',
      }).addTo(map);
      if (chosen) line.bindTooltip(segmentTooltip(seg), { sticky: true, className: 'prov' });
      drawn.push(line);
    });
  });
  const chosen = state.loops[state.selected];
  if (chosen) {
    const bounds = L.latLngBounds(chosen.coordinates.map((c) => [c[1], c[0]]));
    map.fitBounds(bounds, { paddingTopLeft: [40, 80], paddingBottomRight: [350, 60] });
  }
}

function segmentTooltip(seg) {
  const rows = [];
  if (seg.baseline_no2 !== null && seg.baseline_no2 !== undefined) {
    rows.push(`<b style="color:#8fa9bd">MODELLED</b> NO₂ ${seg.baseline_no2} µg/m³
               <span style="color:#7C8D8B">· annual mean, 20 m federal raster</span>`);
  }
  if (seg.classification === 'measured') {
    rows.push(isSynthetic()
      ? `<b style="color:#D6721F">SYNTHETIC</b> PM2.5 ${seg.concentration} µg/m³
         <span style="color:#7C8D8B">· generated fixture, not a measurement —
         fetch dataset 100113 for the real values</span>`
      : `<b style="color:#73B39E">MEASURED</b> PM2.5 ${seg.concentration} µg/m³
         <span style="color:#7C8D8B">· tram sensors, 2019–20 campaign</span>`);
  } else {
    rows.push(`<b style="color:#cf8353">UNMEASURED</b>
               <span style="color:#7C8D8B">No sensor ever passed. Unknown, not clean —
               contributes nothing to the measured figure.</span>`);
  }
  rows.push(`<span style="color:#7C8D8B">${seg.minutes} min on this stretch</span>`);
  return `<div style="font-family:'IBM Plex Mono';font-size:10px;line-height:1.6;max-width:270px">
            ${rows.join('<br>')}</div>`;
}

/* ---------- conditions strip ---------- */
async function loadConditions() {
  try {
    const res = await fetch(`/run/conditions?lat=${state.lat}&lon=${state.lon}`);
    if (!res.ok) return;
    const c = await res.json();
    const w = c.weather || {}, a = c.air_quality || {}, p = c.pollen || {};
    const chips = [];
    if (w.temperature_c !== undefined && w.temperature_c !== null) {
      chips.push(`<div class="context"><b>${w.temperature_c}°</b>${
        w.precipitation_probability_pct > 20 ? `${w.precipitation_probability_pct}% rain` : 'dry'}</div>`);
    }
    if (w.wind_speed_kmh !== undefined && w.wind_speed_kmh !== null) {
      chips.push(`<div class="context"><b>${Math.round(w.wind_speed_kmh)}</b>km/h ${w.wind_direction || ''}</div>`);
    }
    if (a.european_aqi !== undefined && a.european_aqi !== null) {
      const good = a.european_aqi <= 40;
      chips.push(`<div class="context ${good ? 'good' : 'warn'}"><b>AQI ${a.european_aqi}</b>${
        good ? 'good' : 'moderate'}</div>`);
    }
    if (p.worst) {
      const v = p.values[p.worst];
      chips.push(`<div class="context"><b>${p.worst}</b>${v.band} pollen</div>`);
    }
    chips.push('<div class="context" style="color:#566765">forecast · Open-Meteo</div>');
    $('contextRow').innerHTML = chips.join('');
  } catch (err) { /* conditions are a nicety; a route is not blocked on them */ }
}

/* ---------- pre-run report ---------- */
async function openReport() {
  $('reportModal').classList.add('open');
  $('reportSummary').innerHTML = '<div class="mono muted">Loading…</div>';
  $('reportAir').innerHTML = ''; $('reportProv').innerHTML = '';
  $('reportElev').innerHTML = ''; $('reportWeather').innerHTML = '';
  $('reportPollen').innerHTML = '';
  const p = query(); p.set('index', state.selected);
  try {
    const res = await fetch('/run/report?' + p);
    if (!res.ok) throw new Error((await res.json()).detail);
    state.report = await res.json();
    renderReport(state.report);
  } catch (err) {
    $('reportSummary').innerHTML = `<div class="mono" style="color:var(--orange)">${err}</div>`;
  }
}
function closeReport() { $('reportModal').classList.remove('open'); }
window.closeReport = closeReport;
$('reportModal').addEventListener('click', (e) => {
  if (e.target.id === 'reportModal') closeReport();
});

function renderReport(r) {
  const air = r.air, t = r.terrain || {}, c = r.conditions || {};
  $('reportTitle').textContent =
    `${r.run.distance_km} km loop · ${Math.round(r.run.duration_min)} min`;

  $('reportSummary').innerHTML = [
    [`${r.run.distance_km}`, 'distance km'],
    [`${Math.round(r.run.duration_min)}`, `min at ${fmtPace(r.run.pace_min_per_km)}`],
    [t.ascent_m !== null && t.ascent_m !== undefined ? `+${t.ascent_m} m` : '—', 'ascent'],
    [t.max_grade_pct ? `${t.max_grade_pct}%` : '—', 'max smoothed grade'],
    [`${Math.round(air.coverage.measured_share * 100)}%`, 'air measured'],
  ].map(([v, l]) => `<div class="metric"><b>${v}</b><span>${l}</span></div>`).join('');

  $('reportAir').innerHTML = r.why_this_route.map((line, i) =>
    `<p>${i === 0 ? '<strong>Route air.</strong> ' : ''}${line}</p>`).join('');

  // elevation profile
  const profile = t.profile || [];
  if (profile.length > 2) {
    const w = 560, h = 120, pad = 6;
    const es = profile.map((p) => p.elevation_m);
    const lo = Math.min(...es), hi = Math.max(...es), span = Math.max(1, hi - lo);
    const pts = profile.map((p, i) => {
      const x = (i / (profile.length - 1)) * w;
      const y = h - pad - ((p.elevation_m - lo) / span) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    $('reportElev').innerHTML = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <polyline points="${pts}" fill="none" stroke="var(--green)" stroke-width="1.5"/>
        <polyline points="0,${h} ${pts} ${w},${h}" fill="rgba(78,158,134,.10)" stroke="none"/>
      </svg>`;
    $('elevAxis').innerHTML =
      `<span>0 km</span><span>${(r.run.distance_km / 2).toFixed(1)} km</span>
       <span>${r.run.distance_km} km</span>`;
  } else {
    $('reportElev').innerHTML =
      `<div class="mono muted" style="font-size:10px;padding-top:38px">
         Elevation unavailable${t.unavailable ? ` (${t.unavailable})` : ''}.</div>`;
  }

  const w = c.weather || {}, a = c.air_quality || {}, pol = c.pollen || {};
  const val = (v, suffix) => (v === null || v === undefined ? '—' : `${v}${suffix || ''}`);
  $('reportWeather').innerHTML = [
    [val(w.temperature_c, '°C'), 'temperature'],
    [val(w.precipitation_probability_pct, '%'), 'rain probability'],
    [w.wind_speed_kmh === null || w.wind_speed_kmh === undefined
      ? '—' : `${Math.round(w.wind_speed_kmh)} km/h`, `wind ${w.wind_direction || ''}`],
    [val(a.european_aqi), 'european aqi'],
  ].map(([v, l]) => `<div class="wx"><b>${v}</b><span>${l}</span></div>`).join('');

  // Pollen gets its own row: a runner with hay fever reads this first, and it
  // does not belong squeezed in beside the wind.
  const kinds = Object.keys(pol.values || {});
  $('reportPollen').innerHTML = kinds.length
    ? kinds
        .sort((x, y) => pol.values[y].grains_per_m3 - pol.values[x].grains_per_m3)
        .map((k) => {
          const v = pol.values[k];
          const active = v.band !== 'none';
          return `<span class="pl${active ? ' on' : ''}"><b>${k}</b>${v.band}${
            active ? ` · ${v.grains_per_m3} grains/m³` : ''}</span>`;
        }).join('')
    : '<span class="pl">pollen forecast unavailable</span>';

  // provenance — one row per class, in the language of the class
  const rows = [];
  const m = r.provenance.modelled, meas = r.provenance.measured;
  if (m) {
    rows.push(['modelled', `NO₂ annual mean, ${m.year}, ${m.resolution_m} m raster.
      ${m.dataset}. ${m.attribution}. Used to rank these routes against each other —
      not valid for a single address.`]);
  }
  if (r.provenance.fixture_warning) {
    rows.push(['unmeasured', `<b style="color:var(--orange)">${r.provenance.fixture_warning}</b>
      No real tram readings are loaded, so the PM2.5 figures above are generated,
      not observed. The modelled NO₂ ranking is unaffected.`]);
  }
  if (meas && meas.dataset && !r.provenance.fixture_warning) {
    const win = meas.measurement_window;
    rows.push(['measured', `PM2.5 from tram-mounted sensors, dataset ${meas.dataset}
      (${meas.readings_total ? meas.readings_total.toLocaleString('de-CH') : '—'} readings${
      win ? `, ${win.first_month} to ${win.last_month}` : ''}). ${meas.license}.
      A closed campaign: no data has been added since. Shown as corroboration,
      not as the deciding number.`]);
  }
  rows.push(['dynamic', `Distance, duration, route candidates and the exposure total
    were computed for this request, at ${fmtPace(r.run.pace_min_per_km)} /km. A different
    pace or hour gives different numbers.`]);
  if (c.source) {
    rows.push(['forecast', `Temperature, precipitation, wind, European AQI and pollen
      from ${c.source} for this hour. A model's expectation, and sometimes wrong.`]);
  }
  if (t.source) {
    rows.push(['derived', `${t.source}. Smoothed over ${t.grade_window_m || 200} m —
      a 90 m elevation model cannot support a precise street gradient.`]);
  }
  const unmeasuredKm = (r.run.distance_km * (1 - air.coverage.measured_share)).toFixed(2);
  rows.push(['unmeasured', `${unmeasuredKm} km of this route has no nearby tram
    measurement. It contributes nothing to the measured figure. Unknown, not clean.`]);

  $('reportProv').innerHTML = rows.map(([cls, text]) =>
    `<div class="prov-row"><span class="badge ${cls}">${cls}</span><p>${text}</p></div>`).join('');

  $('exportBtn').onclick = () => {
    const p = query(); p.set('index', state.selected);
    window.location = '/run/gpx?' + p;
  };
}

/* first paint */
loadLoops();
