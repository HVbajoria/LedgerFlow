import Dashboard from './pages/Dashboard'

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <h1 className="text-xl font-semibold text-gray-900">LedgerFlow Dashboard</h1>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        <Dashboard />
      </main>
    </div>
  )
}
