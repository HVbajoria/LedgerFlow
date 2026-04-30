import { useState } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { createPayout } from '../api/payouts'

/**
 * Payout request form.
 * Converts rupees → paise before sending to API.
 * Generates a fresh idempotency key per submission.
 *
 * @param {{ merchantId: string }} props
 */
export default function PayoutForm({ merchantId }) {
  const [amount, setAmount] = useState('')
  const [bankAccountId, setBankAccountId] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [validationError, setValidationError] = useState(null)
  const [result, setResult] = useState(null)   // { type: 'success'|'error', message }

  function validate() {
    if (!amount || Number(amount) <= 0) {
      return 'Amount must be greater than 0.'
    }
    if (!bankAccountId.trim()) {
      return 'Bank account ID is required.'
    }
    return null
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setResult(null)

    const error = validate()
    if (error) {
      setValidationError(error)
      return
    }
    setValidationError(null)

    const idempotencyKey = uuidv4()
    const amountPaise = Math.round(Number(amount) * 100)

    setIsSubmitting(true)
    try {
      await createPayout(
        {
          merchant_id: merchantId,
          amount_paise: amountPaise,
          bank_account_id: bankAccountId.trim(),
        },
        idempotencyKey,
      )
      setResult({ type: 'success', message: 'Payout requested successfully.' })
      setAmount('')
      setBankAccountId('')
    } catch (err) {
      const message =
        err.response?.data?.error?.message ??
        err.response?.data?.error ??
        'Something went wrong. Please try again.'
      setResult({ type: 'error', message })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
      <h3 className="text-base font-semibold text-gray-800 mb-4">Request Payout</h3>

      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Amount (₹)
          </label>
          <input
            type="number"
            min="0.01"
            step="0.01"
            placeholder="e.g. 500.00"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            disabled={isSubmitting}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
                       focus:outline-none focus:ring-2 focus:ring-gray-400
                       disabled:bg-gray-50 disabled:text-gray-400"
          />
        </div>

        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Bank Account ID
          </label>
          <input
            type="text"
            placeholder="e.g. HDFC-XXXX-1234"
            value={bankAccountId}
            onChange={(e) => setBankAccountId(e.target.value)}
            disabled={isSubmitting}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
                       focus:outline-none focus:ring-2 focus:ring-gray-400
                       disabled:bg-gray-50 disabled:text-gray-400"
          />
        </div>

        
        {validationError && (
          <p className="text-sm text-red-600">{validationError}</p>
        )}

       
        {result && (
          <div
            className={`rounded-lg px-4 py-3 text-sm ${
              result.type === 'success'
                ? 'bg-emerald-50 border border-emerald-200 text-emerald-700'
                : 'bg-red-50 border border-red-200 text-red-700'
            }`}
          >
            {result.message}
          </div>
        )}

        
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-lg bg-gray-900 text-white text-sm font-medium
                     py-2.5 px-4 hover:bg-gray-700 transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSubmitting ? 'Processing...' : 'Request Payout'}
        </button>
      </form>
    </div>
  )
}
