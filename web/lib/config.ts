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

/** Same emblem at favicon size. */
export const BRAND_ICON =
  process.env.NEXT_PUBLIC_BRAND_ICON ??
  'https://www.zagreb-marathon.com/wp-content/uploads/znak-150x150.jpg';
