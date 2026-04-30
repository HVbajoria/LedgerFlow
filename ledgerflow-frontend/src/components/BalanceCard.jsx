import { formatPaise } from '../utils/currency'

/**
 * Displays a single balance metric.
 * @param {{ title: string, amount: number, accent?: string }} props
 */
export default function BalanceCard({ title, amount, accent = 'text-gray-900' }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-6 flex flex-col gap-2 shadow-sm">
      <span className="text-sm font-medium text-gray-500">{title}</span>
      <span className={`text-2xl font-semibold tracking-tight ${accent}`}>
        {formatPaise(amount ?? 0)}
      </span>
    </div>
  )
}
