import { useEffect, useState } from 'react'
import { getLedgerEntries } from '../api/ledger'
import { formatPaise } from '../utils/currency'

function formatDate(iso) {
  if (!iso) return '—'
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(iso))
}

const TYPE_STYLES = {
  CREDIT: 'text-emerald-600',
  DEBIT:  'text-red-500',
}

const REF_LABELS = {
  PAYMENT:      'Payment',
  PAYOUT:       'Payout Hold',
  PAYOUT_REFUND:'Payout Refund',
  SEED:         'Seed Credit',
}

/**
 * Shows recent ledger entries (credits + debits) for a merchant.
 * @param {{ merchantId: string }} props
 */
export default function LedgerTable({ merchantId }) {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await getLedgerEntries(merchantId)
        const list = Array.isArray(data) ? data : (data.results ?? [])
        if (!cancelled) { setEntries(list); setError(null) }
      } catch (err) {
        if (!cancelled) setError('Failed to load ledger entries.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [merchantId])

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100">
        <h3 className="text-base font-semibold text-gray-800">Recent Credits &amp; Debits</h3>
      </div>

      {loading && <p className="text-sm text-gray-400 animate-pulse px-6 py-4">Loading...</p>}

      {error && (
        <div className="mx-6 my-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3">
          {error}
        </div>
      )}

      {!loading && !error && entries.length === 0 && (
        <p className="text-sm text-gray-400 px-6 py-6">No ledger entries yet.</p>
      )}

      {!loading && entries.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                <th className="px-6 py-3">Type</th>
                <th className="px-6 py-3">Amount</th>
                <th className="px-6 py-3">Reference</th>
                <th className="px-6 py-3">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {entries.map((e) => (
                <tr key={e.id} className="hover:bg-gray-50 transition-colors">
                  <td className={`px-6 py-3 font-semibold ${TYPE_STYLES[e.type] ?? 'text-gray-700'}`}>
                    {e.type === 'CREDIT' ? '+ CREDIT' : '− DEBIT'}
                  </td>
                  <td className="px-6 py-3 font-medium text-gray-800">
                    {formatPaise(e.amount_paise)}
                  </td>
                  <td className="px-6 py-3 text-gray-500">
                    {REF_LABELS[e.reference_type] ?? e.reference_type}
                    {e.reference_id && (
                      <span className="ml-1 font-mono text-xs text-gray-400">
                        {e.reference_id.slice(0, 8)}…
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-3 text-gray-500">{formatDate(e.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
