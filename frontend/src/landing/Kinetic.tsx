import { motion } from "motion/react";
import { Fragment } from "react";

const SHOWN = { opacity: 1, y: 0 };
const HIDDEN = { opacity: 0, y: "0.35em" };

/**
 * Word-by-word type. `shown` is the share of words revealed (0 to 1) and comes from the timeline,
 * so the text can be scrubbed forwards and backwards. The words are always real text in the page.
 */
export function Kinetic({ text, shown }: { text: string; shown: number }) {
  const words = text.split(" ");
  const count = Math.ceil(shown * words.length - 1e-6);
  return (
    <>
      {words.map((word, i) => (
        <Fragment key={i}>
          <motion.span
            className="lp-word"
            initial={false}
            animate={i < count ? SHOWN : HIDDEN}
            transition={{ duration: 0.45, ease: [0.2, 0.7, 0.2, 1] }}
          >
            {word}
          </motion.span>{" "}
        </Fragment>
      ))}
    </>
  );
}
