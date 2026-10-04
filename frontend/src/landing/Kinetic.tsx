import { Fragment } from "react";

export type WordState = "off" | "ghost" | "new" | "on";

/** The state of word `i` of `total` when a share `shown` (0 to 1) of the words has landed. */
export function wordState(i: number, total: number, shown: number): WordState {
  const count = Math.ceil(shown * total - 1e-6);
  if (i < count - 1) return "on";
  if (i === count - 1) return shown >= 1 ? "on" : "new"; // the newest word stays hot until the line is complete
  return i === count && count > 0 ? "ghost" : "off"; // the next word is pre-set as a dim ghost
}

/**
 * Word-by-word type. `shown` is the share of words revealed (0 to 1) and comes from the timeline,
 * so the text can be scrubbed forwards and backwards. The words are always real text in the page;
 * the states only change how they look (landing.css, .lp-word).
 */
export function Kinetic({ text, shown }: { text: string; shown: number }) {
  const words = text.split(" ");
  return (
    <>
      {words.map((word, i) => (
        <Fragment key={i}>
          <span className="lp-word" data-state={wordState(i, words.length, shown)}>
            {word}
          </span>{" "}
        </Fragment>
      ))}
    </>
  );
}
