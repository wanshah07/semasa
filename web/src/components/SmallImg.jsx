import { nextSrc, tileSrc } from "../lib/thumbs";

/* A stored picture drawn small (a post card's thumbnail, a pose to choose): its small copy where one exists, the picture itself
   when the copy does not load (lib/thumbs.js). `url` is the picture's own address; anything else is passed to the <img>. */
export default function SmallImg({ url, alt = "", ...rest }) {
  const { src, full } = tileSrc(url);
  return <img {...rest} src={src} alt={alt} onError={(e) => {
    const next = nextSrc(e.currentTarget.getAttribute("src"), full);
    if (next) e.currentTarget.src = next; else rest.onError?.(e);
  }} />;
}
