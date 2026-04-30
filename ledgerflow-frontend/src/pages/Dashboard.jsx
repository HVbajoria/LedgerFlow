import { useEffect, useState } from 'react'
import { getBalance } from '../api/balance'
import BalanceCard from '../components/BalanceCard'
import PayoutForm from '../components/PayoutForm'
import PayoutHistory from '../components/PayoutHistory'
import LedgerTable from '../components/LedgerTable'

const MERCHANT_ID = import.meta.env.VITE_MERCHANT_ID ?? 'acme-merchant-id'

export default function Dashboard() {
  const [balance, setBalance] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        setLoading(true)
        setError(null)
        const data = await getBalance(MERCHANT_ID)
        if (!cancelled) setBalance(data)
      } catch (err) {
        if (!cancelled) {
          setError(
            err.response?.data?.error?.message ??
            'Failed to load balance. Please try again.'
          )
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  return (
    <div className="space-y-8">
     
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-800">Merchant Balance</h2>
          <p className="text-sm text-gray-500 mt-0.5">Live view of funds across all states</p>
        </div>

        {loading && (
          <p className="text-sm text-gray-400 animate-pulse">Loading balance...</p>
        )}

        {error && (
          <div className="rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3">
            {error}
          </div>
        )}

        {!loading && !error && balance && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <BalanceCard title="Total Balance"     amount={balance.total_balance} />
            <BalanceCard title="Held Balance"      amount={balance.held_balance}      accent="text-amber-600" />
            <BalanceCard title="Available Balance" amount={balance.available_balance} accent="text-emerald-600" />
          </div>
        )}
      </section>

      
      <section className="max-w-md">
        <PayoutForm merchantId={MERCHANT_ID} />
      </section>

      
      <section>
        <PayoutHistory merchantId={MERCHANT_ID} />
      </section>

     
      <section>
        <LedgerTable merchantId={MERCHANT_ID} />
      </section>
    </div>
  )
}
