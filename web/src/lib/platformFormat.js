/* The film's format follows the platform it is for (Wan, 26 Oct 2026: "Video format also follow the platform format automatically").
   ws.regulab posts on Instagram and Facebook Reels and on Threads, which are upright 9:16; the LinkedIn feed shows a 1:1 video at its
   best. backend/semasa/motion.py (PLATFORM_SIZE, size_of) holds the same table. No imports, so Node tests load it as it is. */
export const PLATFORM_SIZE = { regulab: "portrait", linkedin: "square" };
export const sizeFor = (stream) => PLATFORM_SIZE[stream === "linkedin" ? "linkedin" : "regulab"];
