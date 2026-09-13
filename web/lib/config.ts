/**
 * The three knobs the design exposed as editor props, lifted to env so they can
 * be changed per deployment without a code edit.
 */
export const PRICE_SINGLE_EUR = Number(process.env.NEXT_PUBLIC_PRICE_SINGLE_EUR ?? 9);
export const PRICE_BUNDLE_EUR = Number(process.env.NEXT_PUBLIC_PRICE_BUNDLE_EUR ?? 39);

/**
 * When true, previews are treated as watermarked and originals are locked
 * behind a purchase. Off by default so the prototype shows the full gallery.
 */
export const WATERMARK = process.env.NEXT_PUBLIC_WATERMARK === 'true';

export const COURSE_MAP_SRC = '/course-map.html';
