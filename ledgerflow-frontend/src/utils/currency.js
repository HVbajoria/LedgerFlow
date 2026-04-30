/**
 * Convert paise (integer) to a formatted INR string.
 * formatPaise(100000) → "₹1,000.00"
 */
export function formatPaise(paise) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
  }).format(paise / 100)
}
