import { useState, useEffect, useRef } from 'react'

export default function SwapNotification() {
    const [swaps, setSwaps] = useState([])
    const [connected, setConnected] = useState(false)
    const wsRef = useRef(null)

    useEffect(() => {
        fetch('http://localhost:8000/api/swaps/recent')
            .then(res => res.json())
            .then(data => {
                setSwaps(data.slice(0, 10));
            })
            .catch(err => console.error('Failed to fetch recent swaps', err));
    }, [])

    useEffect(() => {
        const ws = new WebSocket('ws://localhost:8000/ws/anomalies')
        wsRef.current = ws
        ws.onopen = () => setConnected(true)
        ws.onclose = () => setConnected(false)

        ws.onmessage = (msg) => {
            const payload = JSON.parse(msg.data)
            if (payload.type === 'CARRIER_SWAP') {
                setSwaps(prev => [payload.data, ...prev].slice(0, 10))
            }
        }
        // Removing proactive close to survive React 18 Strict Mode double-mounts
    }, [])

    return (
        <div className='p-4'>
            <div className='flex items-center gap-2 mb-4'>
                <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]' : 'bg-slate-300'}`} />
                <span className='text-xs text-slate-500 font-medium'>Actor Agent — Carrier Swap Log</span>
            </div>

            {swaps.length === 0 && (
                <p className='text-xs text-slate-500'>No carrier swaps yet. Run demo_seed.py to trigger.</p>
            )}

            <div className='space-y-3'>
                {swaps.map((swap, i) => (
                    <div key={i} className='p-3 bg-teal-50 border border-teal-100 rounded-lg shadow-sm'
                        style={{ animation: i === 0 ? 'fadeIn 0.3s ease' : 'none' }}
                    >
                        <div className='flex justify-between items-center mb-1'>
                            <span className='text-teal-700 font-bold text-sm'>CARRIER SWAPPED</span>
                            <span className='text-xs text-slate-400 font-mono'>{swap.decision_id}</span>
                        </div>
                        <div className='text-sm text-slate-800 mb-1 font-medium'>
                            <span className='text-red-500 font-mono'>{swap.old_carrier_id}</span>
                            <span className='text-slate-400 mx-2'>→</span>
                            <span className='text-green-600 font-mono'>{swap.new_carrier_id}</span>
                        </div>
                        <div className='flex gap-4 text-xs text-slate-500'>
                            <span>{swap.shipments_count} shipments</span>
                            <span>Old rel: {(swap.old_reliability * 100).toFixed(0)}%</span>
                            <span>New rel: {(swap.new_reliability * 100).toFixed(0)}%</span>
                        </div>
                        <div className='mt-1 text-xs text-slate-400'>
                            KS stat: {swap.ks_statistic?.toFixed(3)}  ·  p={swap.ks_pvalue?.toFixed(4)}
                            <span className='ml-2 font-mono text-teal-600'>{swap.sha256_hash?.slice(0, 12) || swap.sha256?.slice(0, 12) || ''}...</span>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    )
}
