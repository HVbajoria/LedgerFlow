import { useEffect, useState } from 'react'
import { getPayouts } from '../api/payouts'
import { formatPaise } from '../utils/currency'

const POLL_INTERVAL_MS = 4000

const STATUS_STYLES = {
  PENDING:    'bg-yellow-100 text-yellow-700',
  PROCESSING: 'bg-blue-100 text-blue-700',
  COMPLETED:  'bg-emerald-100 text-emerald-700',
  FAILED:     'bg-red-100 text-red-700',
}

function StatusBadge({ status }) {
  const style = STATUS_STYLES[status] ?? 'bg-gray-100 text-gray-600'
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {status}
    </span>
  )
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))
}

/**
 * Polls payout history every POLL_INTERVAL_MS and displays it in a table.
 * @param {{ merchantId: string }} props
 */
export default function PayoutHistory({ merchantId }) {
  const [payouts, setPayouts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  async function fetchPayouts() {
    try {
      const data = await getPayouts(merchantId)
      
      const list = Array.isArray(data) ? data : (data.results ?? [])
      
      list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      setPayouts(list)
      setError(null)
    } catch (err) {
      setError(
        err.response?.data?.error?.message ??
        'Failed to load payout history.'
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchPayouts()
    const interval = setInterval(fetchPayouts, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [merchantId])

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <h3 className="text-base font-semibold text-gray-800">Payout History</h3>
        <span className="text-xs text-gray-400">Auto-refreshes every {POLL_INTERVAL_MS / 1000}s</span>
      </div>

      {loading && (
        <p className="text-sm text-gray-400 animate-pulse px-6 py-4">Loading payouts...</p>
      )}

      {error && (
        <div className="mx-6 my-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3">
          {error}
        </div>
      )}

      {!loading && !error && payouts.length === 0 && (
        <p className="text-sm text-gray-400 px-6 py-6">No payouts yet.</p>
      )}

      {!loading && payouts.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                <th className="px-6 py-3">Payout ID</th>
                <th className="px-6 py-3">Amount</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Created At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {payouts.map((payout) => (
                <tr key={payout.payout_id ?? payout.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-3 font-mono text-xs text-gray-500">
                    {(payout.payout_id ?? payout.id ?? '').slice(0, 8)}…
                  </td>
                  <td className="px-6 py-3 font-medium text-gray-800">
                    {formatPaise(payout.amount_paise)}
                  </td>
                  <td className="px-6 py-3">
                    <StatusBadge status={payout.status} />
                  </td>
                  <td className="px-6 py-3 text-gray-500">
                    {formatDate(payout.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
