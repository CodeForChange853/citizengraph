# Landing page motion spec (`/welcome`)

Status: written in Phase A from an analysis of the reference clip, then kept current as the phases landed.
Code: `frontend/src/landing/`. This file is the source for timings, easings and the sound design; the code
constants in `timeline.ts` and `demo.ts` must match section 4.

## 1. Reference and how it was analysed

`frontend/reference/ref.mp4` (not in the repository: the folder is git-ignored). 60.0 s, 720x900, 30 fps,
h264 + HE-AAC (44.1 kHz, 48 kb/s). A kinetic-typography motion graphic; the on-screen credit reads
"mexicat/x".

Method (all local, with a static ffmpeg build in a throwaway environment):

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
| Near-black stage, one hot orange accent | Confirmed for about nine tenths of the clip. Exceptions: a yellow-green word at 29.0 to 30.0 s, white-on-black inverted cards at 22.8 to 24.0 s, a solid orange end card at 59.0 s. **There is no cyan anywhere.** Cyan is our own addition, so it is kept to one job (things the system or the visitor operates: prompt, caret, focus ring, pressed controls, the call to action) and never competes with orange for the story. |
| Monospace terminal HUD, typing caret, small tables | Not a terminal window. It is a **one-line prompt bar** across the frame: a chevron, text typed word by word, a block caret, the newest word in orange with an underline, a return-key glyph at the right when it is sent. A small table of candidates sits above the caret and two lines of tiny read-outs below. It appears twice (16.5 to 22.4 s and 52.5 to 58.8 s), so it is a recurring motif, not a one-off. |
| Corner crop marks, callouts with leader lines, grain, vignette | Crop marks sit at all four corners of the frame for the whole clip: they are the constant frame. Callouts with leader lines are densest at 33.5 to 37.5 s (boxes snapping on, then lines to labels). Grain and vignette are faint. |
| Big bold type revealed word by word, in sync with the audio | Confirmed, and more specific: words land on a steady grid of about **455 ms** (kick spacing measured from 24.4 s onward, about 132 a minute) with half-steps. The **newest word is orange and turns white when the next one lands**, and the **next word is pre-set as a dim ghost** before it lands. Both are worth taking. |
| Text set on a path | Five cases: riding a plotted curve behind its moving head (9.5 to 10.7 s), along a contour line in perspective (11.3 to 12.5 s), on a sine wave (38.5 to 41.0 s), on an arc round the orb (42.5 to 45.0 s), on an arc lying on a floor grid (45.5 to 49.0 s). In every case the **line's head writes the text**: letters appear just behind the head. |
| Self-drawing glow trails with spark particles | The trail head is a bright dot with a small bloom. **Sparks are rare**: one burst at 3.5 to 4.5 s where a line strikes a shape. They mark an impact; they are not a constant shower. We use them the same way (the line head, the Enter key, the trail landing). |
| Topographic contour rings | Fine grey-white lines that fill the whole frame, first as terrain in perspective (11.0 to 16.0 s), then flat and concentric behind the prompt bar with a soft orange core (16.5 to 22.4 s). They drift slowly; they do not pulse. |
| Voronoi cell map | Short (24.4 to 25.7 s): edges **grow from the vertices with bright heads** until the frame is tiled. |
| Perspective wireframe grids | Two kinds: a 3D wireframe room (26.0 to 29.5 s) and a flat floor grid seen at an angle (45.5 to 52.0 s). The room needs real 3D and is out of scope for Canvas 2D; only the floor grid is used. |
| Warped-grid singularity orb with accretion ring | 41.5 to 45.0 s: a flat grid bends toward the centre, a black disc with an orange ring and fine streaks, text on an arc above and below. At 45.5 s the view tilts and the orb becomes a funnel in the floor grid. |
| Matching cuts | Stronger than expected: scene detection finds hard cuts only round the flash and at the end card. Almost every change is a **match move** (a line carries on into the next picture, or the view pushes through a shape). |
| A bright full-screen flash | 22.43 to 22.77 s: ten frames at near white (mean luma 205 to 227 of 255), **followed by four more light/dark swaps in the next 1.2 s** (23.0, 23.4 to 23.6, 23.87 s). A second full-frame change (to orange) at 59.0 s. That is at or over the general flash limit of WCAG 2.3.1. **Not reproduced in any form** (section 6). |
| (not in the notes) | The picture area is **landscape**, about 720x408, letterboxed in the 720x900 file with a caption under it. The design is composed for a wide stage; on phones we restack it instead of scaling it. Characters and illustrations (an animal outline, a creature, a face) carry several shots; none of them is reproduced. |

## 3. Shot list

Times are seconds in the reference. "Maps to" names the Citizen Graph beat (section 4) that borrows the
technique. Words in the reference are described, not quoted.

| Time | On screen | Technique | Length | Easing and rhythm | Maps to |
|---|---|---|---|---|---|
| 0.0 to 0.5 | One orange dot in the middle of a dark frame; crop marks | Hold on a single live point before anything moves | 0.5 s | Still, then lines burst out | Beat 1, t=0: a glowing start point and the caret, so the first frame is never empty |
| 0.5 to 2.0 | Thin lines shoot out from the dot; axes, a ruled circle, tick labels; a line of prompt text is typed at the top left | Self-drawing lines with a bright head; HUD micro text | 1.5 s | Fast out, slow settle; about 9 short ticks between 2.1 and 3.7 s | Beat 1: the orange line draws across the stage; faint ruled grid |
| 2.0 to 3.5 | A curve is drawn on the axes; code scrolls at the left; a small table appears bottom right | Path drawing, typed code, small data table | 1.5 s | Steady draw speed | Beat 3 table of offices; beat 4 typed query |
| 3.5 to 5.0 | Big two-line headline, word by word; sparks where a line strikes the first big letter; the big word starts as a ghost | Word reveal on the beat, ghost of the next word, one spark burst | 1.5 s | One word per half beat (about 230 ms) | Beat 2 headline: word by word, ghost first, newest word in orange |
| 5.0 to 9.5 | Outline drawing completes; three-line headlines at the side | New word orange, earlier words white, next word dim | 4.5 s | Words on the 455 ms grid | Headlines of beats 6 to 8 |
| 9.5 to 10.9 | A plotted curve draws left to right; a sentence rides it, appearing behind the head | Text on a moving path, written by the head | 1.4 s | Constant speed, linear | Beat 5: arc text written by the trail |
| 11.0 to 12.6 | Contour terrain in perspective; text follows one contour | Contours filling the frame; text on a contour | 1.6 s | Slow push in | Beat 2 contour rings across the whole stage |
| 12.6 to 16.0 | An orange trail wanders through the contours to the centre; one huge word fills in letter by letter from an outline; small callout at the centre | Glow trail with a head; outline-to-fill letters; leader-line callout | 3.4 s | Trail ease-in-out; letters about 80 ms apart | Beat 5 trail through the graph; beat 3 callouts |
| 16.0 to 16.5 | The frame turns half a turn; the earlier word is seen upside down | Whole-frame rotation as a transition | 0.5 s | Fast ease-in-out | Not used (large moving area) |
| 16.5 to 22.4 | Flat concentric contours with an orange core; prompt bar typed word by word; candidate table above the caret; read-outs below; return glyph at the end | Prompt bar, newest word orange and underlined, block caret | 5.9 s | A word roughly every beat or half beat; slow zoom the whole time | Beats 1 and 4: prompt line, typed text, small table; rings behind |
| 22.4 to 24.2 | Core swells to a white frame, then alternating black and white word cards, then a number counting up | Full-frame flash and hard inversions | 1.8 s | Hard cuts about every 0.3 s | **Not used.** Beat 5's orb uses a soft bloom limited to the orb |
| 24.4 to 25.7 | Three-line headline at the left; Voronoi edges grow from vertices; a four-digit counter at the top right | Edge growth with bright heads; counter | 1.3 s | Edges ease out; counter steps | Beat 3: office cells grow from their corners; a step counter |
| 25.7 to 26.0 | Two outlined rings pulse out from the middle of a word | Ring pulse from a point | 0.3 s | Ease-out | Beat 5: ring pulse where the trail lands |
| 26.0 to 29.5 | Camera flies through a wireframe room to a signboard with a two-line headline | 3D wireframe fly-through | 3.5 s | Continuous move | Not used (needs real 3D) |
| 29.5 to 37.6 | Characters and an illustration; callout boxes snap on one after another with leader lines to stacked labels | Callout boxes, leader lines, stacked mono labels | 8.1 s | One box about every half beat | Beat 3 callouts (technique only; no character is reproduced) |
| 38.0 to 41.0 | A horizontal orange line draws across a ruled grid, becomes a sine wave; a sentence rides the wave | Line across the frame; text on a wave; ruled grid; corner read-outs | 3.0 s | Line: about 0.5 s ease-out; text constant speed | Beat 1: line across the stage on a ruled grid |
| 41.0 to 41.6 | Two-word headline in orange over a grid starting to bend | Grid begins to warp; headline pops | 0.6 s | Quick ease-out | Beat 5: grid starts to bend as the nodes fall in |
| 41.6 to 45.0 | Orb: black disc, orange ring, streaks; grid bent toward it; text on an arc above, then below | Warped grid, accretion ring, arc text letter by letter | 3.4 s | Letters about 110 ms apart; slow rotation | Beat 5: singularity orb with the arc text round it |
| 45.5 to 52.0 | View tilts to a floor grid; text lies on an arc on the floor; later the grid tilts the other way | Perspective floor grid; text in perspective | 6.5 s | Slow drift | Beat 7: perspective floor under the SLA timeline |
| 52.5 to 58.8 | Vertical bars in front; the prompt bar again with another typed line | Prompt bar reprise | 6.3 s | As 16.5 to 22.4 | Beat 8: the terminal look returns in the status read-out |
| 59.0 to 60.0 | Solid orange frame with a huge black word, then black with a white word | Full-frame colour change | 1.0 s | Hard cut | **Not used** |

Pacing summary: shots last 1.3 to 6.5 s; a new word or mark lands every 230 or 455 ms; a line takes about
0.5 s to cross the frame; nothing loops.

## 4. The Citizen Graph timeline

One number line in milliseconds (`timeline.ts`). Beats 1 to 4 play by themselves (12.6 s). Beats 5 to 8 are
1,000 units each and are set by the scroll position. Visuals and sound read the same clock; sound cues fire
only while the intro plays, never on a seek, a skip or a scroll.

| Beat | id | Start | Length | What happens |
|---|---|---|---|---|
| 1 | `ask` | 0 | 3,600 | t=0: faint ruled grid, crop marks, a glowing start point, blinking cyan caret. 0 to 520: the orange line draws across the stage (ease-out cubic), sparks at its head. From 600: the Taglish question is typed, 44 ms a character with a 90 ms pause between words. 180 ms after the last character: Enter. |
| 2 | `contours` | 3,600 | 1,800 | Contour rings ripple out from the end of the question across the whole stage (each ring 0.4 of the beat, 0.1 apart, ease in-out). Sparks run along the line. The headline lands word by word, about one word per 230 ms, each word a ghost first and orange while it is the newest. |
| 3 | `offices` | 5,400 | 2,800 | Office cells grow from their corners (0 to 45 %). 40 service nodes pop in on spokes (30 to 85 %). Callouts with leader lines (20 to 50 %). Corner crop marks round the graph and a step counter. The counts are also real text (HUD chips above the graph). |
| 4 | `query` | 8,200 | 4,400 | The illustrative query is typed (0 to 2,000). Four guardrail checks tick at 2,400 + n x 455 (the reference's beat spacing); each tick turns one crop mark of the graph cyan. |
| 5 | `trail` | 12,600 | 1,000 | Scroll, stage pinned. 0 to 0.34: the glow trail leaves the question, enters the graph and lands on the service through its office. 0.14 to 0.48: the arc text is written behind the trail head. 0.5 to 0.8: the 40 nodes spiral in and the grid bends. 0.72 to 1: the orb (black core, orange ring, cyan rim), with the arc text round it. |
| 6 | `answer` | 13,600 | 1,000 | A ring opens into the outline of the answer card (soft wipe); the card holds neutral placeholders under the sample tag. |
| 7 | `sla` | 14,600 | 1,000 | Perspective floor; four steps appear in order; step 2 is at an outside agency and not counted; step 3 is past the allowed time and raises the alert draft. |
| 8 | `local` | 15,600 | 1,000 | Headline, three chips (local, offline, read-only), a status read-out, the call to action. |

Easing: `ramp()` (smoothstep) for scrubbed values; ease-out cubic for anything that draws itself; words use
a 450 ms ease-out `(0.2, 0.7, 0.2, 1)` transition. Glitch: a cyan and orange split on a headline word as it
lands, 2 px, 140 ms, one run, only that word.

Reduced motion: no autoplay, no scroll following, no glitch, no sound, no caret blink. The DOM shows every
beat finished; the canvas shows one poster frame (the graph with the trail landed), not the orb, because the
graph is the more informative still.

## 5. Sound

### What was measured (terminal-like sounds only)

- The track is music and voice throughout; 95 % of its energy is below 1.9 kHz and 99 % below 6.3 kHz, so
  detail above that is limited by the codec.
- **Opening (0 to 4 s, sparse backing).** Nine clear short transients between 2.09 and 3.68 s: gap median
  179 ms (93 to 318 ms), each about 64 ms at half power, spectral centre about 4.4 kHz (3.1 to 7.0 kHz), about
  14 dB over the high-band bed, level spread about 1 dB. The first 10 ms carries the click; a tail lingers about
  60 ms.
- **Prompt-bar passages (16.5 to 22.4 s, 52.5 to 58.8 s).** The energy envelope finds nothing separable: the
  music's high band is about 9 dB louder here. Spectral flux finds 4 to 6 onsets a second in bursts 40 to 80 ms
  apart with longer gaps between bursts, and 61 to 71 % of them sit on the 455 ms grid or its half step in the
  first passage. **Uncertain:** these could be key clicks or the percussion; the two cannot be told apart from
  this file. What can be taken safely is the shape: short bursts of clicks per word, then a gap.
- Kick spacing 455 ms from 24.4 s on (used as the spacing of the guardrail ticks).

### Design (all synthesized with Web Audio, no files, no tones held)

| Cue | When | Recipe |
|---|---|---|
| `key` | each typed character of the question (not spaces) | white noise through a band-pass at 3.2 to 5.2 kHz (random per key, Q 1.4), 1 ms attack, 22 to 34 ms decay, gain varied by about 30 % |
| `enter` | the question is sent | noise through a 900 Hz low-pass with a 90 ms decay, plus a sine falling 150 to 60 Hz in 80 ms: a thunk, not a note |
| `tick` | each guardrail check | noise through a 6 kHz band-pass (Q 6), 18 ms decay, with a 30 ms sine at 2.1 kHz under it at a third of the level |
| `blip` | each office callout lighting (4) | 22 ms sine at 1.4 kHz, very quiet |

Master gain 0.22. Longest sound 90 ms. Fastest repetition: keys 44 ms apart.
Rules: muted by default; a visible toggle that remembers the choice (`localStorage`, key `cg.landing.sound`);
no audio context until a user gesture; suspended while the tab is hidden; never created with reduced motion;
nothing on the page depends on hearing it.

## 6. Accessibility limits on the motion

- No full-screen flash and no inverted frames. The brightest change is the orb's bloom, confined to the orb,
  and it follows the scroll, so it cannot repeat by itself.
- At most 3 flashes a second anywhere: the caret blinks about once a second; the glitch is one 140 ms run
  on one word, and headline words land at least 230 ms apart on a small area.
- "Skip intro" is the first focusable element. Every control is a real button or link with a visible focus ring.
- The canvas has a text alternative; decoration is `aria-hidden`; every fact drawn on it (offices, counts, the
  checks, the claim on the arc) is also real text in the page.
- Typing is visual only: screen readers get the whole question and query at once.

## 7. Performance design

Canvas 2D only. Device pixel ratio capped at 2. The canvas redraws only when the timeline moves, never
while off-screen or in a hidden tab. Geometry is precomputed from a fixed seed; particles are a pure function
of the timeline time, so frames keep no state and scrubbing backwards works.

Adaptive quality (measurements in section 8):

| Level | Pixel ratio cap | Glow passes | Sparks | Orb | Rings and grid |
|---|---|---|---|---|---|
| 2 | 2 | 3 | all | bloom, 18 streaks | every segment |
| 1 | 1.5 | 2 | half | bloom, 9 streaks | every segment |
| 0 | 1 | 1 | none | no bloom, no streaks | every second segment |

Step-down rule (`quality.ts`). A frame is late when it arrives more than 25 ms after the previous one (under
40 frames a second). The canvas drops one level as soon as 6 of the last 40 drawn frames were late, or when
drawing alone has averaged over 10 ms across at least 20 frames. Gaps of 250 ms or more are idle time and are
not counted; the first 500 ms after mount are ignored; the window restarts after each step; quality never goes
back up during a visit.

Why the earlier rule did not engage: it added 1 for a late frame, subtracted 1 for an on-time frame and stepped
at a net 24. Under a 4x CPU slow-down only about one frame in four is late, so the on-time frames cancelled the
late ones. In the baseline run it engaged only after about 9 s on this machine, and it is expected never to
engage where the late frames are spread more evenly.

## 8. Measurements

Headless Chromium 153 (Playwright build 1243) on the development laptop, built app served by `vite preview`,
CPU slow-down through the DevTools protocol. Frame gaps are the times between animation frames in the page.
These are numbers from one machine and one run each, not a benchmark of the system.

Before (commit 15773d7):

| Setup | Phase | Median | 95th | Max | Late (>25 ms) | Quality level over time |
|---|---|---|---|---|---|---|
| Desktop 1366x768, no slow-down | intro | 16.7 ms | 16.8 ms | 17 ms | 0 % | 2 |
| Desktop 1366x768, 4x CPU | intro | 16.7 ms | 33.4 ms | 50 ms | 28 % | 2, then 1 at 8.9 s, 0 at 12.6 s |
| Phone 390x700 at pixel ratio 3, no slow-down | intro | 16.7 ms | 16.8 ms | 33 ms | 0 % | 2 |
| Phone 390x700 at pixel ratio 3, 4x CPU | intro | 16.7 ms | 33.4 ms | 50 ms | 22 % | 2, then 1 at 9.3 s; never 0 |

After (Phase G):

| Setup | Phase | Median | 95th | Max | Late (>25 ms) | Quality level over time |
|---|---|---|---|---|---|---|
| Desktop 1366x768, no slow-down | intro | 16.7 ms | 16.8 ms | 17 ms | 0 % | 2 |
| Desktop 1366x768, no slow-down | scroll | 16.7 ms | 16.7 ms | 17 ms | 0 % | 2 |
| Desktop 1366x768, 4x CPU | intro | 16.7 ms | 33.4 ms | 50 ms | 17 % | 2, then 1 at 5.5 s, 0 at 6.0 s |
| Desktop 1366x768, 4x CPU | scroll | 16.7 ms | 33.3 ms | 83 ms | 14 % | 0 |
| Phone 390x700 at pixel ratio 3, no slow-down | intro | 16.7 ms | 16.7 ms | 17 ms | 0 % | 2 (backing store 780x1400: ratio capped at 2) |
| Phone 390x700 at pixel ratio 3, no slow-down | scroll | 16.7 ms | 16.7 ms | 17 ms | 0 % | 2 |
| Phone 390x700 at pixel ratio 3, 4x CPU | intro | 16.7 ms | 16.8 ms | 50 ms | 3 % | 2, then 1 at 5.6 s (585x1050), 0 at 6.2 s (390x700) |
| Phone 390x700 at pixel ratio 3, 4x CPU | scroll | 16.7 ms | 16.8 ms | 50 ms | 1 % | 0 |

Reading: the step comes when beat 3 starts (5.4 s), which is where the load rises; beats 1 and 2 keep 60 frames
a second even slowed down, so there is nothing to step down for earlier. On the slowed phone the lower levels
bring the intro back to about 58 frames a second. On the slowed desktop the canvas is already at pixel ratio 1,
so the remaining late frames come from page work outside the canvas and stay at 14 to 17 %.

Flash check: 441 screenshots over the intro; the largest change of the mean frame level between two shots was
0.002 of full scale (a general flash needs 0.10).

Not measured: real phones, real low-end laptops, Safari, Firefox.
