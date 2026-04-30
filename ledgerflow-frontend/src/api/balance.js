import client from './client'

/**
 * Fetch computed balance for a merchant.
 * GET /api/v1/merchants/{merchantId}/balance/
 *
 * @returns {{ total_balance: number, held_balance: number, available_balance: number }}
 */
export async function getBalance(merchantId) {
  try {
    const response = await client.get(`/api/v1/merchants/${merchantId}/balance/`)
    return response.data
  } catch (error) {
    console.error('[getBalance] failed:', error.response?.data ?? error.message)
    throw error
  }}
