export function gaugeColor(value: number): string {
  if (value >= 70) return 'var(--success)'
  if (value >= 40) return 'var(--medium)'
  return 'var(--critical)'
}
