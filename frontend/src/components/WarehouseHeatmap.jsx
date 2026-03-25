// dashboard/src/components/WarehouseHeatmap.jsx — complete component
import { useState, useEffect } from 'react'
import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

// Colour scale: green (low load) → amber → red (high load)
const loadColor = (pct) => {
    if (pct >= 95) return '#dc2626'  // CRITICAL — red-600
    if (pct >= 85) return '#ea580c'  // HIGH — orange-600
    if (pct >= 70) return '#d97706'  // WARNING — amber-600
    if (pct >= 50) return '#65a30d'  // MODERATE — lime-600
    return '#16a34a'                  // NORMAL — green-600
}

const loadLabel = (pct) => {
    if (pct >= 95) return 'CRITICAL'
    if (pct >= 85) return 'CONGESTED'
    if (pct >= 70) return 'WARNING'
    return 'NORMAL'
}

const INDIA_CENTER = [20.5937, 78.9629]

export default function WarehouseHeatmap() {
    const [warehouses, setWarehouses] = useState([])
    const [connected, setConnected] = useState(false)
    const [congestions, setCongestions] = useState([])

    // ── Initial load ────────────────────────────────────────────
    useEffect(() => {
        fetch('http://localhost:8000/api/warehouses')
            .then(r => r.json()).then(setWarehouses)
            .catch(console.error)
    }, [])

    // ── WebSocket: live load updates ─────────────────────────────
    useEffect(() => {
        const ws = new WebSocket('ws://localhost:8000/ws/anomalies')
        ws.onopen = () => setConnected(true)
        ws.onclose = () => setConnected(false)
        ws.onmessage = (msg) => {
            const payload = JSON.parse(msg.data)
            // Live warehouse load sync from Observer Agent
            if (payload.type === 'warehouse_update' && Array.isArray(payload.warehouses)) {
                setWarehouses(payload.warehouses)
            }
            // Update heatmap on congestion events
            if (payload.trigger_type && ['LOAD_THRESHOLD', 'THROUGHPUT_DROP', 'ARIMA_PREEMPTIVE'].includes(payload.trigger_type)) {
                setCongestions(prev => {
                    const updated = prev.filter(c => c.warehouse_id !== payload.warehouse_id)
                    return [...updated, payload]
                })
                // Update warehouse load pct in state
                setWarehouses(prev => prev.map(wh =>
                    wh.warehouse_id === payload.warehouse_id
                        ? {
                            ...wh, current_load_pct: payload.current_load_pct,
                            throughput_per_hr: payload.throughput_per_hr
                        }
                        : wh
                ))
            }
        }
        // Deliberately avoiding ws.close() in cleanup to bypass React StrictMode auto-close bug
    }, [])

    const congestedCount = congestions.filter(c => c.severity === 'HIGH' || c.severity === 'CRITICAL').length

    return (
        <div className='bg-white rounded-xl p-4'>
            {/* Header */}
            <div className='flex items-center gap-3 mb-3'>
                <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]' : 'bg-slate-300'}`} />
                <span className='text-slate-500 font-medium text-sm'>Warehouse Heatmap</span>
                {congestedCount > 0 && (
                    <span className='ml-auto text-orange-400 font-bold animate-pulse'>
                        {congestedCount} warehouse congested
                    </span>
                )}
            </div>

            {/* Leaflet map */}
            <MapContainer center={INDIA_CENTER} zoom={5} style={{ height: '380px', borderRadius: '8px' }}
                className='z-0 outline-none'>
                <TileLayer
                    url='https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'
                    attribution='CartoDB'
                />
                {warehouses.map(wh => (
                    <CircleMarker
                        key={wh.warehouse_id}
                        center={[wh.lat || wh.latitude, wh.lng || wh.longitude]}
                        radius={Math.max(14, wh.current_load_pct / 5)}  // larger circle = more load
                        fillColor={loadColor(wh.current_load_pct)}
                        color='#1e293b'
                        weight={2}
                        fillOpacity={0.85}
                    >
                        <Tooltip permanent direction='top' offset={[0, -10]}>
                            <div className='text-xs font-mono'>
                                <div className='font-bold'>{wh.warehouse_id} — {wh.city || wh.location_city}</div>
                                <div>Load: {wh.current_load_pct?.toFixed(1)}%  [{loadLabel(wh.current_load_pct)}]</div>
                                <div>Throughput: {wh.throughput_per_hr} shipments/hr</div>
                            </div>
                        </Tooltip>
                    </CircleMarker>
                ))}
            </MapContainer>

            {/* Congestion alerts below map */}
            {congestions.map((c, i) => (
                <div key={i} className='mt-2 bg-orange-50 border border-orange-200
                                  rounded-lg p-2 text-xs text-orange-800 shadow-sm'>
                    <span className='font-bold'>{c.warehouse_id}</span>
                    {' '}{c.severity} — {c.trigger_type} — {c.current_load_pct}% load.
                    {c.recommended_action === 'REDIRECT' &&
                        ` Redirecting to ${c.alternate_warehouse_id}.`}
                    {c.recommended_action === 'STAGGER' &&
                        ` Staggering intake by ${c.stagger_minutes} min.`}
                </div>
            ))}
        </div>
    )
}
