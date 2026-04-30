import client from './client'

/**
 * Fetch ledger entries for a merchant (credits + debits).
 * GET /api/v1/ledger/?merchant_id=...
 *
 * @returns {Array} list of ledger entry objects
 */
export async function getLedgerEntries(merchantId) {
  try {
    const response = await client.get('/api/v1/ledger/', {
      params: { merchant_id: merchantId },
    })
    return response.data
  } catch (error) {
    console.error('[getLedgerEntries] failed:', error.response?.data ?? error.message)
    throw error
  }
}
