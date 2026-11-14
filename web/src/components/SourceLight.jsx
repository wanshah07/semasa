import { useLang } from "../lib/i18n";
import { LIGHT_BG, LIGHT_NAME } from "../lib/sourceLights";

/* One dot: green live, orange standby, red unlive (grey when the watchdog has not reported). The words are in the tooltip and the
   screen-reader name, so the colour is never the only way to read it. */
export default function SourceLight({ light, why, className = "" }) {
  const { t } = useLang();
  const name = t(LIGHT_NAME[light][0], LIGHT_NAME[light][1]);
  const label = why ? `${name}: ${why}` : name;
  return <span role="img" aria-label={label} title={label} data-light={light}
    className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${LIGHT_BG[light]} ${className}`} />;
}
