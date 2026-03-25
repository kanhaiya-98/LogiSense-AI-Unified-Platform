import { useState, useEffect, useRef } from 'react'

const SEVERITY_STYLES = {
    CRITICAL: { bg: 'bg-red-600', text: 'text-white', pulse: true },
    HIGH: { bg: 'bg-orange-500', text: 'text-white', pulse: true },
    MEDIUM: { bg: 'bg-yellow-400', text: 'text-black', pulse: false },
    LOW: { bg: 'bg-blue-400', text: 'text-white', pulse: false },
}

const SEVERITY_ORDER = { CRITICAL: 3, HIGH: 2, MEDIUM: 1, LOW: 0 }

export default function AnomalyBadge() {
    const [events, setEvents] = useState([])
    const [connected, setConnected] = useState(false)
    const wsRef = useRef(null)

    useEffect(() => {
        // Fetch initially active anomalies
        fetch('http://localhost:8000/api/anomalies/active')
            .then(res => res.json())
            .then(data => {
                if (Array.isArray(data)) {
                    setEvents(data.slice(0, 50));
                }
            })
            .catch(err => console.error("Error fetching active anomalies:", err));

        // Connect to Observer Agent WebSocket
        const ws = new WebSocket('ws://localhost:8000/ws/anomalies')
        wsRef.current = ws

        ws.onopen = () => {
            setConnected(true)
            console.log('Connected to Observer Agent')
        }

        ws.onmessage = (msg) => {
            const event = JSON.parse(msg.data)
            // Only process real anomaly events — ignore cascade_tree, warehouse_update, etc.
            if (!event.shipment_id || !event.severity) return
            setEvents(prev => {
                const updated = [event, ...prev].slice(0, 50)
                return updated.sort((a, b) =>
                    SEVERITY_ORDER[b.severity] - SEVERITY_ORDER[a.severity]
                )
            })
        }

        ws.onclose = () => setConnected(false)
        return () => ws.close()
    }, [])

    const criticalCount = events.filter(e => e.severity === 'CRITICAL').length

    return (
        <div className='p-4'>
            {/* Connection status */}
            <div className='flex items-center gap-2 mb-4'>
                <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]' : 'bg-slate-300'}`} />
                <span className='text-sm text-slate-500 font-medium'>
                    {connected ? 'Observer Agent live' : 'Connecting...'}
                </span>
                {criticalCount > 0 && (
                    <span className='ml-auto bg-red-600 text-white text-xs font-bold px-2 py-1 rounded-full animate-pulse'>
                        {criticalCount} CRITICAL
                    </span>
                )}
            </div>

            {/* Event list */}
            <div className='space-y-2 max-h-96 overflow-y-auto'>
                {events.length === 0 && (
                    <p className='text-slate-500 text-sm'>No anomalies detected. System nominal.</p>
                )}
                {events.map((event, idx) => {
                    const style = SEVERITY_STYLES[event.severity] || SEVERITY_STYLES.LOW
                    return (
                        <div key={idx}
                            className={`rounded-lg p-3 ${style.bg} ${style.text}
                                ${style.pulse ? 'animate-pulse' : ''}`}
                        >
                            <div className='flex justify-between items-center'>
                                <span className='font-bold text-sm'>{event.severity}</span>
                                <span className='text-xs opacity-75'>{event.trigger_type}</span>
                            </div>
                            <div className='text-sm mt-1'>
                                <span className='font-mono'>{event.shipment_id}</span>
                                {event.carrier_id && (
                                    <span className='ml-2 opacity-75'>via {event.carrier_id}</span>
                                )}
                            </div>
                            {event.eta_lag_min > 0 && (
                                <div className='text-xs mt-1 opacity-75'>
                                    ETA lag: +{event.eta_lag_min} min
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}
