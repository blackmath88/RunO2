/* Hack am Rhein framing for runO2.
 *
 * This deliberately sits beside the planner rather than inside its data logic:
 * the experiment/story may evolve without changing the deterministic evidence
 * pipeline. The overlay is a first-visit editorial preface, not a consent gate.
 */
'use strict';

(() => {
  const HACK_URL = 'https://hackamrhein.dev/warm-up';
  const STORAGE_KEY = 'runo2-warmup-intro-seen-v1';

  const style = document.createElement('style');
  style.textContent = `
    .warmup-overlay{position:fixed;inset:0;z-index:5000;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(3,7,8,.34);backdrop-filter:blur(15px) brightness(.52);-webkit-backdrop-filter:blur(15px) brightness(.52);opacity:0;pointer-events:none;transition:opacity .24s ease}
    .warmup-overlay.open{opacity:1;pointer-events:auto}
    .warmup-card{width:min(690px,94vw);max-height:88vh;overflow:auto;background:rgba(11,17,20,.96);border:1px solid #334347;box-shadow:0 30px 100px rgba(0,0,0,.62);padding:30px 30px 26px}
    .warmup-kicker{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--green2);display:flex;justify-content:space-between;gap:20px;align-items:center}
    .warmup-kicker a{color:inherit;text-decoration:none;border-bottom:1px solid rgba(115,179,158,.35)}
    .warmup-card h2{font-size:clamp(30px,5vw,48px);font-weight:300;letter-spacing:-.045em;line-height:1.02;margin:24px 0 18px;max-width:14ch}
    .warmup-card .answer{font-size:clamp(20px,3vw,28px);font-weight:300;color:var(--green2);margin:0 0 18px}
    .warmup-card p{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11.5px;line-height:1.72;color:#9fb0ac;margin:0 0 14px;max-width:72ch}
    .warmup-card p strong{color:var(--ink);font-weight:400}
    .warmup-facts{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin:22px 0}
    .warmup-fact{background:var(--panel2);padding:13px 14px;font-family:"IBM Plex Mono",ui-monospace,monospace}
    .warmup-fact b{display:block;font-size:17px;font-weight:300;color:var(--ink);margin-bottom:4px}
    .warmup-fact span{font-size:8.5px;line-height:1.4;color:var(--dim);text-transform:uppercase;letter-spacing:.08em}
    .warmup-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:24px}
    .warmup-actions button,.warmup-actions a{border:1px solid var(--line);background:none;color:var(--ink);padding:11px 14px;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:10.5px;text-decoration:none;cursor:pointer}
    .warmup-actions .primary{background:var(--white);color:#07100d;border-color:var(--white)}
    .story-pill{position:fixed;z-index:1400;right:18px;bottom:18px;border:1px solid #314349;background:rgba(11,17,20,.9);backdrop-filter:blur(9px);color:#aab9b5;padding:9px 11px;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:9.5px;letter-spacing:.04em;cursor:pointer;display:none}
    .story-pill.show{display:block}
    .story-extension{margin:0 0 70px}
    .story-extension .story-kicker{font-family:"IBM Plex Mono",ui-monospace,monospace;color:var(--green2);font-size:9px;letter-spacing:.14em;text-transform:uppercase;margin-bottom:12px}
    .story-extension h3{font-size:28px;font-weight:300;letter-spacing:-.025em;margin:0 0 12px}
    .story-extension p{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11.5px;line-height:1.75;color:var(--dim);max-width:76ch;margin:0 0 16px}
    .journey{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin:26px 0 54px}
    .journey-step{background:var(--paper);padding:16px 14px;min-height:128px}
    .journey-step .step-no{font-family:"IBM Plex Mono",ui-monospace,monospace;color:var(--green2);font-size:8px;letter-spacing:.12em;margin-bottom:10px}
    .journey-step b{display:block;font-weight:400;font-size:14px;margin-bottom:7px}
    .journey-step span{font-family:"IBM Plex Mono",ui-monospace,monospace;color:var(--dim);font-size:9.5px;line-height:1.55}
    .open-question{border:1px solid var(--line);background:var(--panel2);padding:22px;margin:28px 0 52px}
    .open-question strong{display:block;font-size:20px;font-weight:300;color:var(--ink);margin-bottom:10px}
    .architecture-breaks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:24px 0 56px}
    .architecture-break{border:1px solid var(--line);padding:16px;background:var(--paper)}
    .architecture-break b{display:block;font-size:13px;font-weight:400;margin-bottom:7px}
    .architecture-break p{font-size:10px;line-height:1.62;margin:0;color:var(--dim)}
    .ai-note{border-left:2px solid var(--green);padding:4px 0 4px 17px;margin:28px 0 52px}
    .ai-note strong{font-weight:400;color:var(--ink)}
    @media(max-width:760px){.warmup-card{padding:23px 20px}.warmup-facts{grid-template-columns:1fr}.journey{grid-template-columns:1fr}.architecture-breaks{grid-template-columns:1fr}.story-pill{right:12px;bottom:12px}}
  `;
  document.head.appendChild(style);

  const overlay = document.createElement('div');
  overlay.className = 'warmup-overlay';
  overlay.id = 'warmupIntro';
  overlay.innerHTML = `
    <div class="warmup-card" role="dialog" aria-modal="true" aria-labelledby="warmupTitle">
      <div class="warmup-kicker">
        <span>Hack am Rhein · Warm Up · Basel 2026</span>
        <a href="${HACK_URL}" target="_blank" rel="noopener">official challenge ↗</a>
      </div>
      <h2 id="warmupTitle">Can Basel's tram data plan a better run?</h2>
      <div class="answer">I tried it. The surprising answer: not reliably.</div>
      <p>Basel published particulate measurements from sensors riding on trams. I run here, so I asked the obvious question: <strong>could those measurements help choose a running route?</strong></p>
      <p>The experiment said no. The sensors disagree with each other more than many streets differ. Instead of smoothing that problem away, runO2 widened the evidence: official air models, reference stations, forecasts, pollen and terrain each do only the job they can support.</p>
      <div class="warmup-facts">
        <div class="warmup-fact"><b>0.51</b><span>µg/m³ difference between two streets</span></div>
        <div class="warmup-fact"><b>1.41</b><span>µg/m³ disagreement between sensors</span></div>
        <div class="warmup-fact"><b>0.36</b><span>signal ÷ noise · not enough to rank</span></div>
      </div>
      <p>This was a <strong>quick hackathon build and an experiment, not a validated health product</strong>. Maybe the product idea works with better data — perhaps in another city. What became more interesting is the question underneath: when is open data actually good enough to make a decision?</p>
      <p>Built heavily with <strong>ChatGPT, Claude, delta.dev and VS Code</strong>. AI accelerated research, coding, tests and iteration; the evidence rules and reproducible checks remain deterministic.</p>
      <div class="warmup-actions">
        <button class="primary" data-action="explore">EXPLORE THE PLANNER →</button>
        <button data-action="story">READ THE STORY ↓</button>
        <a href="${HACK_URL}" target="_blank" rel="noopener">HACK AM RHEIN ↗</a>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const pill = document.createElement('button');
  pill.className = 'story-pill';
  pill.textContent = 'ⓘ HACK AM RHEIN / STORY';
  pill.setAttribute('aria-label', 'Open the Hack am Rhein project introduction');
  document.body.appendChild(pill);

  const story = document.getElementById('data');
  if (story) {
    const extension = document.createElement('div');
    extension.className = 'story-extension';
    extension.id = 'story';
    extension.innerHTML = `
      <div class="story-kicker">Hack am Rhein Warm Up · why this exists</div>
      <h3>A route planner? Maybe. An experiment in what open data can tell us? Definitely.</h3>
      <p>The Warm Up asked for one Basel dataset, one genuine question and the smallest thing that answers it. The tram measurements supplied the dataset; running supplied the question. The useful result was not the one I expected.</p>
      <p><a href="${HACK_URL}" target="_blank" rel="noopener">See the official Hack am Rhein Warm Up ↗</a></p>

      <div class="journey">
        <div class="journey-step"><div class="step-no">01 / CURIOSITY</div><b>Trams measure air</b><span>Could a moving sensor network tell me where to run?</span></div>
        <div class="journey-step"><div class="step-no">02 / JOIN</div><b>Put it on the street graph</b><span>Use the earlier Basel Spatial Graph work to compare candidate loops.</span></div>
        <div class="journey-step"><div class="step-no">03 / TEST</div><b>Check the signal</b><span>Measure street contrast against disagreement between independent sensors.</span></div>
        <div class="journey-step"><div class="step-no">04 / FAIL</div><b>The dataset says no</b><span>The noise floor is nearly three times the street signal needed for ranking.</span></div>
        <div class="journey-step"><div class="step-no">05 / WIDEN</div><b>Compose evidence</b><span>Use stronger sources for spatial ranking and keep the tram data as corroboration.</span></div>
      </div>

      <div class="open-question">
        <strong>Does runO2 make sense as a product? I am not sure yet.</strong>
        <p>The intuition is appealing: if two runs are otherwise similar, environmental conditions could be another signal. But this build has not shown that the differences are large enough to matter to runners, that the current Basel data is the right proxy, or that combining several imperfect sources creates a better decision rather than a more sophisticated-looking one.</p>
        <p>A city with denser, calibrated and current mobile sensing might produce a very different answer. For now, runO2 should be read as an experiment, not a product or health claim.</p>
      </div>

      <h3>What is interesting underneath the app?</h3>
      <p>The architecture has to know the difference between <em>available data</em>, <em>usable evidence</em> and an <em>unsupported conclusion</em>. That means measured, modelled, forecast, dynamic and unknown values stay separate all the way to the interface.</p>

      <div class="ai-note"><p><strong>Built with AI — extensively.</strong> ChatGPT, Claude, delta.dev and VS Code were used for exploration, implementation, refactoring, tests, data investigation and interface iteration. The goal was not to prove I can type every line unaided. The boundary I cared about was different: AI may propose code and interpretations, but it does not get to decide what the data proves.</p></div>

      <h3>What would break this architecture?</h3>
      <div class="architecture-breaks">
        <div class="architecture-break"><b>1 · Fake precision from one magic score</b><p>Annual NO₂, live station readings, forecasts, pollen and terrain are different evidence types. Blending them into an unexplained scalar would make the interface simpler and the claim weaker.</p></div>
        <div class="architecture-break"><b>2 · Temporal mismatch</b><p>An annual spatial baseline is not a 17:00 measurement. Every source needs a visible validity scope so a time-specific UI does not imply time-specific evidence where none exists.</p></div>
        <div class="architecture-break"><b>3 · False spatial precision</b><p>A 20 m model raster looks exact. runO2 uses it for relative route comparison, not to claim an exact concentration at an address or street corner.</p></div>
        <div class="architecture-break"><b>4 · Weak-data fallback</b><p>If the defensible spatial baseline disappears, the system must not silently rank by the tram measurements that already failed the resolution test. Better no air ranking than a confident bad one.</p></div>
        <div class="architecture-break"><b>5 · Silent staleness</b><p>A source can stop updating while the application keeps working. Observation period, retrieval date, expected update rhythm and source mode belong to runtime provenance.</p></div>
        <div class="architecture-break"><b>6 · Basel leaking into the core</b><p>The routing/evidence model can be portable; Basel dataset IDs, BAFU semantics, sensor schemas and providers are not. Another-city support should arrive through source adapters, not conditionals scattered through the product.</p></div>
      </div>
    `;
    story.insertBefore(extension, story.firstChild);
  }

  function movePlannerBehindOverlay() {
    if (window.location.hash) return;
    const planner = document.getElementById('planner');
    if (planner) planner.scrollIntoView({ block: 'start' });
  }

  function openIntro() {
    movePlannerBehindOverlay();
    overlay.classList.add('open');
    pill.classList.remove('show');
  }

  function closeIntro(target) {
    overlay.classList.remove('open');
    sessionStorage.setItem(STORAGE_KEY, '1');
    pill.classList.add('show');
    if (target) setTimeout(() => document.querySelector(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
  }

  overlay.addEventListener('click', (event) => {
    const action = event.target.closest('[data-action]')?.dataset.action;
    if (action === 'explore') closeIntro('#planner');
    if (action === 'story') closeIntro('#story');
  });
  pill.addEventListener('click', openIntro);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && overlay.classList.contains('open')) closeIntro('#planner');
  });

  if (sessionStorage.getItem(STORAGE_KEY)) pill.classList.add('show');
  else requestAnimationFrame(openIntro);
})();
