/**
 * The race's own emblem, used as the header mark and as the site icon.
 *
 * It points at the official site by default so it works without any setup. For
 * a real deployment put a copy in `public/brand/` (`npm run fetch:brand` does
 * it) and set NEXT_PUBLIC_BRAND_MARK=/brand/znak.jpg — a static export should
 * not depend on another site staying up.
 */
export const BRAND_MARK =
  process.env.NEXT_PUBLIC_BRAND_MARK ??
  'https://www.zagreb-marathon.com/wp-content/uploads/znak.jpg';

/**
 * Width / height of BRAND_MARK, held so the header does not reflow while it
 * loads. The Zagreb emblem is 336 × 400; a wide logo such as Željava's is
 * 606 × 313.
 */
export const BRAND_MARK_RATIO = process.env.NEXT_PUBLIC_BRAND_MARK_RATIO || '336 / 400';

/** Same emblem at favicon size. */
export const BRAND_ICON =
  process.env.NEXT_PUBLIC_BRAND_ICON ??
  'https://www.zagreb-marathon.com/wp-content/uploads/znak-150x150.jpg';

/** Square home-screen icon (180 × 180). Falls back to BRAND_ICON. */
export const BRAND_APPLE_ICON = process.env.NEXT_PUBLIC_BRAND_APPLE_ICON || '';
