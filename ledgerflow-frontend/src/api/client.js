import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * Attach an Idempotency-Key to a single request.
 * Usage: client.post('/api/v1/payouts/', data, withIdempotencyKey(key))
 */
export function withIdempotencyKey(key) {
  return {
    headers: { 'Idempotency-Key': key },
  }
}

export default client
