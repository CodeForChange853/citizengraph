# Landing page motion spec (`/welcome`)

Status: second version. The first version of `/welcome` was an architecture sheet with a typed terminal.
This version is a product-launch advertisement told by scrolling: "Two cores. One answer."
Code: `frontend/src/landing/`. This file is the source for the story, timings, copy rules and sound design;
the constants in `scenes.ts` and `beats.ts` must match section 5.

## 1. Reference and how it was analysed

`frontend/reference/ref.mp4` (not in the repository: the folder is git-ignored). 60.0 s, 720x900, 30 fps,
h264 + HE-AAC (44.1 kHz, 48 kb/s). A kinetic-typography motion graphic; the on-screen credit reads
"mexicat/x".

Method (all local, with a static ffmpeg build in a throwaway environment; the frames and sheets were viewed
again for this version):

- 120 frames at 2 fps on five contact sheets; 18 full-resolution key frames; a 15 fps pass over 22.2 to 24.2 s.
- ffmpeg scene detection at threshold 0.25, and the mean luma of every frame (`signalstats`).
- Audio: mono 44.1 kHz WAV, then (a) a 2.5 kHz high-pass envelope with peak picking and (b) spectral flux in
  1.5 to 4 kHz and 4 to 9 kHz, to find short terminal-like transients. Only timing, length, level and spectral
  centre were measured. Nothing from the audio or the frames is stored in the repository.

**Reference rule.** Technique and pacing only. No frame, sound, lyric, character or illustration is copied or
embedded, none of its text is quoted (the shot list describes the words, it does not repeat them), and there is
no music. All copy and all drawings on `/welcome` are written from scratch.

## 2. What the analysis found, against the starting notes

| Starting note | Finding |
|---|---|
| Near-black stage, one hot orange accent | Confirmed for about nine tenths of the clip. Exceptions: a yellow-green word at 29.0 to 30.0 s, white-on-black inverted cards at 22.8 to 24.0 s, a solid orange end card at 59.0 s. **There is no cyan anywhere.** Cyan is our own addition and now has one meaning: Core 1, the Guide. Orange is Core 2, the Watch, plus sparks, alerts and the orb. |
| (earlier note) Monospace terminal HUD, typing caret, small tables | **Not used in this version: the page has no terminal, typing, caret, input box or code.** For the record, the reference has no terminal window. It is a **one-line prompt bar** across the frame: a chevron, text typed word by word, a block caret, the newest word in orange with an underline, a return-key glyph at the right when it is sent. A small table of candidates sits above the caret and two lines of tiny read-outs below. It appears twice (16.5 to 22.4 s and 52.5 to 58.8 s), so it is a recurring motif, not a one-off. |
| Corner crop marks, callouts with leader lines, grain, vignette | Crop marks sit at all four corners of the frame for the whole clip: they are the constant frame. Callouts with leader lines are densest at 33.5 to 37.5 s (boxes snapping on, then lines to labels). Grain and vignette are faint. |
| Big bold type revealed word by word, in sync with the audio | Confirmed, and more specific: words land on a steady grid of about **455 ms** (kick spacing measured from 24.4 s onward, about 132 a minute) with half-steps. The **newest word is orange and turns white when the next one lands**, and the **next word is pre-set as a dim ghost** before it lands. Both are worth taking. |
| Text set on a path | Five cases: riding a plotted curve behind its moving head (9.5 to 10.7 s), along a contour line in perspective (11.3 to 12.5 s), on a sine wave (38.5 to 41.0 s), on an arc round the orb (42.5 to 45.0 s), on an arc lying on a floor grid (45.5 to 49.0 s). In every case the **line's head writes the text**: letters appear just behind the head. |
| Self-drawing glow trails with spark particles | The trail head is a bright dot with a small bloom. **Sparks are rare**: one burst at 3.5 to 4.5 s where a line strikes a shape. They mark an impact; they are not a constant shower. We use them the same way (the line head, the Enter key, the trail landing). |
| Topographic contour rings | Fine grey-white lines that fill the whole frame, first as terrain in perspective (11.0 to 16.0 s), then flat and concentric behind the prompt bar with a soft orange core (16.5 to 22.4 s). They drift slowly; they do not pulse. |
| Voronoi cell map | Short (24.4 to 25.7 s): edges **grow from the vertices with bright heads** until the frame is tiled. |
| Perspective wireframe grids and a wireframe 3D room | Two kinds: a 3D wireframe room that the camera flies through to a signboard (26.0 to 29.5 s) and a flat floor grid seen at an angle (45.5 to 52.0 s). With WebGL both are now in scope: the room becomes the queue corridor of scene 1. |
| Warped-grid singularity orb with accretion ring | 41.5 to 45.0 s: a flat grid bends toward the centre, a black disc with an orange ring and fine streaks, text on an arc above and below. At 45.5 s the view tilts and the orb becomes a funnel in the floor grid. |
| Matching cuts | Stronger than expected: scene detection finds hard cuts only round the flash and at the end card. Almost every change is a **match move** (a line carries on into the next picture, or the view pushes through a shape). |
| A bright full-screen flash | 22.43 to 22.77 s: ten frames at near white (mean luma 205 to 227 of 255), **followed by four more light/dark swaps in the next 1.2 s** (23.0, 23.4 to 23.6, 23.87 s). A second full-frame change (to orange) at 59.0 s. That is at or over the general flash limit of WCAG 2.3.1. **Not reproduced in any form** (section 6). |
| (not in the notes) | The picture area is **landscape**, about 720x408, letterboxed in the 720x900 file with a caption under it. The design is composed for a wide stage; on phones we restack it instead of scaling it. Characters and illustrations (an animal outline, a creature, a face) carry several shots; none of them is reproduced. |

## 3. Shot list

Times are seconds in the reference. The last column names the scene (section 5) that each technique serves. Words in the reference are described, not quoted.

| Time | On screen | Technique | Length | Easing and rhythm | Serves |
|---|---|---|---|---|---|
| 0.0 to 0.5 | One orange dot in the middle of a dark frame; crop marks | Hold on a single live point before anything moves | 0.5 s | Still, then lines burst out | Scene 0: black stage, one orange spark, held before anything moves |
| 0.5 to 2.0 | Thin lines shoot out from the dot; axes, a ruled circle, tick labels; a line of prompt text is typed at the top left | Self-drawing lines with a bright head; HUD micro text | 1.5 s | Fast out, slow settle; about 9 short ticks between 2.1 and 3.7 s | Scene 0: the spark throws out lines that become the two cores; scene 6: the self-drawing thread |
| 2.0 to 3.5 | A curve is drawn on the axes; code scrolls at the left; a small table appears bottom right | Path drawing, typed code, small data table | 1.5 s | Steady draw speed | Not used (no code, no tables) |
| 3.5 to 5.0 | Big two-line headline, word by word; sparks where a line strikes the first big letter; the big word starts as a ghost | Word reveal on the beat, ghost of the next word, one spark burst | 1.5 s | One word per half beat (about 230 ms) | Every headline: word by word, ghost first, newest word hot; sparks only at impacts (scene 0 ignition, scene 6 overrun) |
| 5.0 to 9.5 | Outline drawing completes; three-line headlines at the side | New word orange, earlier words white, next word dim | 4.5 s | Words on the 455 ms grid | Every headline |
| 9.5 to 10.9 | A plotted curve draws left to right; a sentence rides it, appearing behind the head | Text on a moving path, written by the head | 1.4 s | Constant speed, linear | Scene 4: arc text round the orb |
| 11.0 to 12.6 | Contour terrain in perspective; text follows one contour | Contours filling the frame; text on a contour | 1.6 s | Slow push in | Scene 2: listening rings round the cyan core |
| 12.6 to 16.0 | An orange trail wanders through the contours to the centre; one huge word fills in letter by letter from an outline; small callout at the centre | Glow trail with a head; outline-to-fill letters; leader-line callout | 3.4 s | Trail ease-in-out; letters about 80 ms apart | Scene 6: the glowing thread; scenes 2, 3 and 6: callouts with leader lines |
| 16.0 to 16.5 | The frame turns half a turn; the earlier word is seen upside down | Whole-frame rotation as a transition | 0.5 s | Fast ease-in-out | Not used (large moving area) |
| 16.5 to 22.4 | Flat concentric contours with an orange core; prompt bar typed word by word; candidate table above the caret; read-outs below; return glyph at the end | Prompt bar, newest word orange and underlined, block caret | 5.9 s | A word roughly every beat or half beat; slow zoom the whole time | Rings only (scene 2). **The prompt bar is not used**: the sample question materialises as glowing words |
| 22.4 to 24.2 | Core swells to a white frame, then alternating black and white word cards, then a number counting up | Full-frame flash and hard inversions | 1.8 s | Hard cuts about every 0.3 s | **Not used.** Scene changes use soft bloom or a matching cut |
| 24.4 to 25.7 | Three-line headline at the left; Voronoi edges grow from vertices; a four-digit counter at the top right | Edge growth with bright heads; counter | 1.3 s | Edges ease out; counter steps | Scene 3: the beam fans out to the four office constellations; a scene counter in the HUD |
| 25.7 to 26.0 | Two outlined rings pulse out from the middle of a word | Ring pulse from a point | 0.3 s | Ease-out | Scene 3: the safety sweep ring; scene 6: the pulse at the late step; scene 7: the heartbeat rings |
| 26.0 to 29.5 | Camera flies through a wireframe room to a signboard with a two-line headline | 3D wireframe fly-through | 3.5 s | Continuous move | Scene 1: the wireframe queue corridor, flown through to the module at its end |
| 29.5 to 37.6 | Characters and an illustration; callout boxes snap on one after another with leader lines to stacked labels | Callout boxes, leader lines, stacked mono labels | 8.1 s | One box about every half beat | Callouts in scenes 2, 3 and 6 (technique only; no character is reproduced) |
| 38.0 to 41.0 | A horizontal orange line draws across a ruled grid, becomes a sine wave; a sentence rides the wave | Line across the frame; text on a wave; ruled grid; corner read-outs | 3.0 s | Line: about 0.5 s ease-out; text constant speed | Scene 6: the thread through the steps |
| 41.0 to 41.6 | Two-word headline in orange over a grid starting to bend | Grid begins to warp; headline pops | 0.6 s | Quick ease-out | Scene 4: the floor grid bends as the 40 points fall in |
| 41.6 to 45.0 | Orb: black disc, orange ring, streaks; grid bent toward it; text on an arc above, then below | Warped grid, accretion ring, arc text letter by letter | 3.4 s | Letters about 110 ms apart; slow rotation | Scene 4: singularity orb (lensing, warped grid, accretion ring) with arc text; scene 8: the orb becomes the call to action |
| 45.5 to 52.0 | View tilts to a floor grid; text lies on an arc on the floor; later the grid tilts the other way | Perspective floor grid; text in perspective | 6.5 s | Slow drift | Scenes 3 to 6: perspective floor grid under the constellations and the timeline |
| 52.5 to 58.8 | Vertical bars in front; the prompt bar again with another typed line | Prompt bar reprise | 6.3 s | As 16.5 to 22.4 | Not used |
| 59.0 to 60.0 | Solid orange frame with a huge black word, then black with a white word | Full-frame colour change | 1.0 s | Hard cut | **Not used** |

Pacing summary: shots last 1.3 to 6.5 s; a new word or mark lands every 230 or 455 ms; a line takes about
0.5 s to cross the frame; nothing loops.

## 4. String audit of the first version

Every string that was visible or exposed to assistive technology on `/welcome` before this rewrite, and what
happens to it. "Delete" means the string and the thing it labelled are gone.

| String | Where | Verdict | Why |
|---|---|---|---|
| Citizen Graph | header | keep | product name |
| Thesis prototype, not an official government app | header, footer | keep | required label; the only use of "official" |
| EN / FIL (English, Filipino) | header toggle | keep, disabled | language lock (section 6) |
| Sound: on / Sound: off | header | keep | |
| Skip intro | skip link | rewrite | there is no intro now; the skip link goes to the call to action |
| Replay intro | header | delete | replaced by "Watch the film" |
| Ask once. Bring the right papers. | headline | rewrite | new headline per scene |
| A citizen asks | terminal label | delete | no terminal |
| Ano po ang requirements para sa business permit? | typed question | keep, restaged | shown as glowing words, never typed; still marked for native review in the code |
| Diagram: the four city offices as four cells ... BPLO 7, LCRO 17, CHO 15, CSWDO 1. | canvas text alternative | rewrite | plain words, no office codes |
| Offices: 4 / Services: 40 | HUD chips | rewrite | "4 city offices, 40 services" inside a sentence |
| BPLO, LCRO, CHO, CSWDO and their counts | drawn on the canvas | rewrite | plain office names as real text |
| Illustrative query, read-only | terminal label | delete | banned: query, read-only |
| MATCH (s:Service ...) ... LIMIT 25 | typed code | delete | no code anywhere |
| Guardrail checks; Read-only; Labelled nodes and types; Inside the schema; LIMIT set | check list | delete | banned terms; the idea becomes "Checks every request." |
| retrieved, never generated | arc text | rewrite | "straight from the charter" |
| Many charter pages, one retrieved answer | orb note | delete | |
| The answer comes from the charter, not from the model | section title | rewrite | banned: model |
| The model only writes the query. Every fact ... charter graph. | section body | delete | banned: model, query, graph |
| What to bring / Fees / Steps and time / Read from the charter | card rows | keep, reworded | neutral placeholders stay |
| Sample layout. Amounts, times and lists are left out here on purpose. | card note | rewrite | shorter |
| Sample data | tag | keep | the existing `SampleDataTag` |
| A second agent watches the clock | section title | rewrite | banned: agent |
| It compares each step ... not counted as a delay by the office. | section body | rewrite | plain wording |
| Step 1 to 4; On time; At an outside agency, not counted; Past the allowed time; Not started | timeline | rewrite | fewer labels, as callouts |
| Drafting an alert for staff review | alert card | rewrite | "Early heads-up, drafted for staff review" |
| Runs on the office's own computer | section title | delete | claims policy: no claim about where or how it runs |
| No cloud service is used while it runs. It only reads ... | section body | delete | banned: cloud; no such claim |
| Local / Offline / Read-only | chips | delete | banned or not claimable |
| Model: a file on this computer; Network: not needed while it runs; Charter graph: read-only; Design target: CPU-only laptop, 16 GB; The design target is a goal, not a measured result. | status read-out | delete | banned terms and hardware claims |
| Start asking | call to action | keep | |
| Scroll to follow the answer | hint | rewrite | "Scroll to begin" |
| step counter (digits) | drawn on the canvas | rewrite | scene counter "01 / 09" as real text |

## 5. The story

One pinned full-viewport stage. The native scroll position is the playhead: scrubbed, reversible, no wheel
hijacking. Scene 0 opens with a 3 s hook that plays by itself; after that only scrolling (or the film) moves
the story. Each scene is one idea, a headline of at most 12 words revealed word by word, and at most 25
words of support.

| # | id | Scroll length | Film time | Headline | What you see | Matching cut into the next scene |
|---|---|---|---|---|---|---|
| 0 | `title` | 100 vh | 3 s after the 3 s hook | Two cores. One answer. | Black. One orange spark. It splits; two cores ignite inside a glass module: cyan (Core 1) and orange (Core 2). | The camera pushes through the module; its outline becomes the first frame of the corridor. |
| 1 | `question` | 120 vh | 6 s | Every trip starts with: what do I bring? | A wireframe queue corridor with posts and ropes; sheets of paper lift and scatter past the camera. | The last frame of the corridor is the module, waiting at the end. |
| 2 | `guide` | 120 vh | 6 s | It understands you. Filipino, English, Taglish. | The module splits open; the cyan core takes the stage with listening rings and three language callouts. | A listening ring becomes the safety sweep ring. |
| 3 | `journey` | 400 vh (four shots) | 15 s | Checks every request. / Finds the exact service. / Reads only the city's charter. / Never makes things up. | (a) the sample question materialises as glowing words and a sweep ring passes over it; (b) the words decode into chips that merge into a service icon, and a beam fans out to four office constellations, 40 points; (c) the camera flies in, the beam narrows, one point lights; (d) sheets of paper fly out of it and line up as a checklist. | The 40 points and the sheets fall inward. |
| 4 | `answer` | 150 vh | 7 s | What to bring. Where to go. Straight from the charter. | The points collapse into a singularity orb (lensing, warped floor grid, accretion ring, arc text). The orb resolves into a checklist card with neutral placeholders under the sample tag; items tick off. | The orb's ring flies to the orange core and becomes the clock ring. |
| 5 | `watch` | 120 vh | 5 s | It never stops watching the deadlines. | The camera swings to the orange core inside a ticking clock ring. | The clock hand runs out into the thread. |
| 6 | `request` | 250 vh (three shots) | 9 s | A person decides. Core 2 only drafts. | A glowing thread runs through the steps of one request. The stretch at an outside agency turns grey. One step runs over: an orange pulse, and an alert card drafts itself. Label: Prototype feature. | The thread reels back into the core. |
| 7 | `together` | 120 vh | 5 s | Citizens know what to bring. Offices see delays early. | Both cores back in the module, beating in step. | The two cores merge. |
| 8 | `close` | 100 vh | 3 s | Ask your first question. | The merged orb becomes a large call to action to `/`. The prototype label and a quiet "For reviewers" link to `/help`. | |

Total scroll length 1,480 vh; the film runs 62 s.

Sub-shot timing (share of the scene, `beats.ts`): headline words land over the first 0.06 to 0.30 of a scene
or shot; the support text follows at 0.30; the scene's own action runs from about 0.2 to 0.9; the last 0.1
is the matching cut. Scene 3's four shots are each a quarter of the scene.

Kinetic type: the next word is pre-set as a dim ghost, the newest word is hot (cyan in Core 1 scenes, orange
in Core 2 scenes), earlier words are white. Glitch: a chromatic split and one scanline on the headline as it
enters, 140 ms, one run, confined to the headline box.

Playhead smoothing: the shown playhead eases toward the scroll position (about 120 ms), which gives the
weight of smooth scrolling without taking over the wheel. A jump of more than three quarters of a scene (a
chapter dot, Home/End) is a cut: the stage dips to dark and comes back over 220 ms; it never whips through
the scenes in between.

"Watch the film" scrolls the page by itself at the film pace above (62 s measured). Any wheel, touch, key or
pointer press stops it where it is.

Chapter dots are real links to anchors inside the scroll track; PageDown, Space, the arrow keys and Home/End
work because the page really scrolls. A thin bar at the top shows progress.

## 6. Words: language, voice, claims

- **English only.** The page renders in English whatever language the app is set to, through its own i18next
  instance (`copy.ts`), so the app's stored language is not changed by a visit. `i18n/fil.json` is an empty
  stub; the landing strings are no longer in `NEEDS-NATIVE-REVIEW.md`. The EN/FIL toggle stays in the header,
  greyed out, `aria-disabled`, with no handler (`LANDING_FIL_ENABLED = false`).
- **One non-English string:** the sample citizen question is Taglish because that is how citizens write. It
  is marked `lang="fil"` and still carries a NEEDS-NATIVE-REVIEW comment in the code.
- **Voice:** product launch, for people who are not technical: short, concrete, second person.
- **Allowed:** AI, Core 1, Core 2, Guide, Watch, charter, deadline, alert.
- **Banned in any visible or accessible text:** model, LLM, SLM, neural, Cypher, query, graph, node, Neo4j,
  database, schema, guardrail, LIMIT, read-only, agent, SLA, pipeline, QLoRA, GGUF, CPU, RAM, GB, hardware,
  "design target", network, offline-first, local-first, cloud, server, API, latency, token, benchmark,
  accuracy, and file locations (the test also bans terminal, prompt and offline). A vitest (`banned.test.tsx`) scans the copy file and the rendered page (text,
  `aria-label`, `alt`, `title`). The product name "Citizen Graph" is the one allowed use of "graph"; "agency"
  is not "agent" (whole-word match).
- **Claims:** the page shows what each core does, never that it is proven. No numbers about speed, accuracy,
  time saved, cost, users or fees. "Designed to" for behaviour. No claim that it works offline, that any office
  uses it or that it is approved. The only numbers are 4 offices and 40 services (the received charters). The
  word "official" appears only in "Thesis prototype, not an official government app"; where the brief suggested
  "never changes official records" the page says "never changes the city's records" to keep that rule.
- **"Built on one AI"** is not written anywhere (not confirmed). Scene 7 uses "Two cores. One city."
- No seals, emblems or government marks. No terminal, typing, caret, input box, code or query text.

## 7. Sound

Web Audio, synthesized from one noise buffer and short sines. No files, no music, nothing sustained (longest
sound 0.6 s). Muted by default; a visible toggle that remembers the choice (`localStorage`,
`cg.landing.sound`); no audio context before a user gesture; suspended while the tab is hidden; never created
with reduced motion. Cues fire when the playhead crosses them going forward, by scroll or by film; a jump
(chapter dot) fires nothing.

| Cue | When | Recipe |
|---|---|---|
| `ignite` | each core ignites (hook), the cyan core takes the stage, the orange core takes the stage | noise through a band-pass sweeping 300 to 1,400 Hz, 120 ms attack, 380 ms decay, with a quiet sine rising 80 to 130 Hz |
| `whoosh` | camera moves: into the corridor, arrival at the module, the fly-through, the swing to Core 2 | noise through a band-pass sweeping 500 to 2,600 Hz and back, 350 ms, low level |
| `tick` | each checklist item ticks | noise through a 6 kHz band-pass, 18 ms, with a 30 ms sine at 2.1 kHz under it |
| `pulse` | the late step; the first heartbeat of scene 7 | sine falling 70 to 42 Hz in 260 ms with a low-passed noise thump |

The terminal sound analysis of the first version (key clicks in the reference at about 4.4 kHz, 64 ms, gaps of
about 180 ms) is kept only as the origin of the `tick` recipe; there are no key clicks now.

## 8. Accessibility and safety limits

- No full-screen flash and no inverted frames. Bloom is soft and local. Cuts dip to dark, never to light. At
  most 3 flashes a second anywhere: the glitch is one 140 ms run on one headline; the heartbeat is about one
  beat pair a second and brightens only the two cores.
- Reduced motion: the stage is not pinned. All nine scenes are stacked as static readable sections, each with
  its headline, support text and a still poster; no autoplay, no hook, no film, no glitch, no sound, no WebGL.
- No WebGL (or a lost context): the same pinned scroll story with the still posters in place of the picture. Nothing in the page depends on the 3D picture: every fact is real text.
- The skip link is first in the tab order and goes to the call to action. Every control is a real link or
  button with a visible focus ring. Focusing a control inside a scene scrolls to that scene.
- The canvas is decoration (`aria-hidden`); every scene is a labelled section in reading order, so a screen
  reader reads the whole story without scrolling.

## 9. Technology and performance design

- three.js with custom GLSL (cores, glass, corridor, paper sheets, constellation, beams, orb with lensing,
  warped floor grid, thread, sparks as GPU particles) and a small post chain: bloom, then one pass for
  chromatic aberration, grain and vignette. All text is DOM, never drawn in WebGL.
- `director.ts` is a pure function from (playhead, hook, clock, aspect) to every number the picture needs. It
  imports nothing from three, so it is unit-tested and the picture can be scrubbed in both directions.
- Loading: the landing is its own chunk, loaded only on `/welcome`; the 3D code is a second chunk loaded by the
  landing after first paint. Both, and the display font, are kept out of the service-worker precache and are
  cached at run time on first use. The main chunk does not grow.
- Display type: Archivo (bundled). Body: Atkinson Hyperlegible. HUD micro text: Atkinson Hyperlegible Mono.
  No external requests.
- Tokens: one file, `tokens.ts`, with the values in `tokens.json` beside it (stage #050505, panel #121212, neon #FF4500, accent #00F0FF, text #E2E8F0,
  heading #FFFFFF, muted #9CA3AF). The landing is not part of the contrast gate; body text is kept at light
  grey on near-black.
- Quality scaling (`quality.ts`, the sliding-window rule from the first version: 6 late frames of the last 40,
  a frame is late over 25 ms): full: pixel ratio up to 1.5, bloom, 4x multisampling; high: pixel ratio 1, bloom, 2x multisampling;
  medium: pixel ratio 1, half-resolution bloom, fewer sparks, a simpler orb; low: pixel ratio 0.75, no bloom and
  no last pass. The first 1.5 s after the canvas starts are not counted. It only steps down. The loop stops when the tab is hidden and drops to half rate when nothing has moved for 2 s.
  Target: 60 frames a second on a Ryzen 5 7520U with integrated graphics (a goal, not a gate).

## 10. Measurements

Headless Chromium 153 (Playwright build 1243) on the development laptop, built app served by `vite preview`.
The laptop's own GPU was used through ANGLE and Direct3D 11: "AMD Radeon(TM) Graphics (0x1506)", the
integrated graphics of the Ryzen 5 7520U family, which is the target. Frame gaps are the times between
animation frames in the page; a frame is late over 25 ms. One run each, on one machine: these are checks of
the page, not a benchmark of the system.

| Setup | Phase | Median | 95th | Late (>25 ms) | Quality level |
|---|---|---|---|---|---|
| Desktop 1366x768 | hook (3.5 s after load) | 16.7 ms | 16.8 ms | 4 % | full |
| Desktop 1366x768 | whole story scrolled in 24 s | 16.7 ms | 16.7 ms | 0 % | full |
| Desktop 1366x768, CPU slowed 4x | hook | 16.7 ms | 50.1 ms | 14 % | full, then high at 4.0 s, medium at 4.4 s, low at 7.5 s |
| Desktop 1366x768, CPU slowed 4x | scroll | 16.7 ms | 50.0 ms | 24 % | low (1024x576, no bloom) |
| Phone 390x700 at pixel ratio 3 | hook | 16.7 ms | 16.8 ms | 4 % | full (585x1050: ratio capped at 1.5) |
| Phone 390x700 at pixel ratio 3 | scroll | 16.7 ms | 16.7 ms | 0 % | full |
| Phone 390x700 at pixel ratio 3, CPU slowed 4x | scroll | 16.7 ms | 33.4 ms | 18 % | low (292x525) |
| Desktop 1536x864 at pixel ratio 1.25 | scroll | 16.7 ms | 16.8 ms | 1 % | full (1920x1080), then high and medium during the hook |

The late frames during the hook are the page loading (the 3D chunk compiling its shaders), not the picture.
CPU time per frame while scrolling, from the DevTools profiler: script 2.7 ms, style 2.7 ms, layout 0.3 ms.

Two faults were found by measuring and fixed:

- The scroll loop scheduled one extra frame callback per frame, so a long scroll slowed down steadily (23 %
  late frames over the story, 76 % in the last scene). It now holds one callback at a time; a test pins that.
- The progress variable was set on the page root, which restyled the whole page every frame (8.3 ms of style
  work per frame). It is now a transform on the bar alone (2.7 ms).

Flash check: the whole film (62 s) captured as 1,169 screenshots, about 55 ms apart, 683x384. The largest
change of the mean frame level between two shots was 0.037 of full scale (a general flash needs 0.10); the
brightest frame had a mean level of 0.225. In any one sixteenth of the frame, ten changes over 0.10 in the
whole film, at most three within one second. The first run of this check found a real fault: a sheet of paper
passing through the camera in scene 1 raised the frame level by 0.2 in a tenth of a second. Sheets now drift
away from the camera's path and fade out before they come within 1.4 units of it; a test pins that.

Other headless checks: no cross-origin requests and no console errors or warnings over the whole story; the
home page fetches no landing asset; the precache holds none (19 entries, as before); after one visit the
run-time cache holds the landing chunk, the 3D chunk and the two fonts. With reduced motion: nine still
sections, no canvas, no animation frames, no audio context, the 3D chunk is not requested. With WebGL
switched off: the pinned story with posters, no errors.

Software-rendered WebGL (SwiftShader) draws the same picture but at one to three frames a second, so it says
nothing about speed; it was used only to check that the page still works there.

Not measured: real phones, other laptops and GPUs, Safari, Firefox, a throttled GPU.
