import React, { useState } from 'react';

const API_BASE = 'http://localhost:8000/api';

export default function ZenPlatform() {
    const [activeTab, setActiveTab] = useState('DEC');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);

    // Form State for ZenDec
    const [decForm, setDecForm] = useState({
        blast_radius: 10,
        confidence: 85,
        city: 'delhi',
        historical_summary: 'Heavy congestion expected due to festival.',
        known_pattern: true,
    });

    // Form State for ZenRTO
    const [rtoForm, setRtoForm] = useState({
        order_id: `ORD-${Math.floor(Math.random() * 10000)}`,
        buyer_id: 'BUY-999',
        pincode: '110091',
        address_raw: 'Flat 4B, Green Enclave, Sector 7, Delhi 110091',
        payment_method: 'COD',
        order_value: 2500,
        device_type: 'MOBILE',
    });

    // Form State for ZenETA
    const [etaForm, setEtaForm] = useState({
        shipment_id: `SHP-ETA-${Math.floor(Math.random() * 1000)}`,
        route_distance_km: 1200,
        carrier_id: 'CAR-01',
        sla_deadline_minutes: 2880,
        origin_lat: 28.6139,
        origin_lon: 77.2090,
        dest_lat: 19.0760,
        dest_lon: 72.8777,
    });

    const handleDecSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        setResult(null);
        try {
            const payload = {
                ...decForm,
                carriers: [
                    { carrier_id: 'CAR-01', carrier_name: 'Express Logistics', route: 'DEL-BOM', vehicle_type: 'Truck', cost_inr: 45000, eta_hours: 48, distance_km: 1400, weight_tonnes: 10 },
                    { carrier_id: 'CAR-02', carrier_name: 'Eco Transport', route: 'DEL-BOM', vehicle_type: 'Truck', cost_inr: 38000, eta_hours: 56, distance_km: 1400, weight_tonnes: 10 },
                    { carrier_id: 'CAR-03', carrier_name: 'Fast Track Fast', route: 'DEL-BOM', vehicle_type: 'Truck', cost_inr: 52000, eta_hours: 40, distance_km: 1400, weight_tonnes: 10 },
                ]
            };
            const res = await fetch(`${API_BASE}/demand/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            setResult(data);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleRtoSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        setResult(null);
        try {
            const res = await fetch(`${API_BASE}/routes/score`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(rtoForm),
            });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            setResult(data);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleEtaSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        setResult(null);
        try {
            const res = await fetch(`${API_BASE}/eta/predict`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(etaForm),
            });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            setResult(data);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="w-full h-full flex flex-col items-center bg-slate-50 text-slate-800 p-6 overflow-y-auto font-sans">
            <div className="w-full max-w-5xl mb-6">
                <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight mb-2">Zen Platform</h2>
                <p className="text-slate-500 font-medium">Decision Engine (ZenDec), Risk Scorer (ZenRTO), and ETA Predictor (ZenETA)</p>
            </div>

            <div className="w-full max-w-5xl flex space-x-4 mb-6 border-b border-slate-200 pb-2">
                {['DEC', 'RTO', 'ETA'].map((tab) => (
                    <button
                        key={tab}
                        onClick={() => { setActiveTab(tab); setResult(null); setError(null); }}
                        className={`px-4 py-2 font-semibold rounded-t-lg transition-colors ${activeTab === tab ? 'bg-gradient-to-r from-emerald-400 to-teal-500 text-white' : 'text-slate-500 hover:text-slate-900'}`}
                    >
                        {tab === 'DEC' ? 'ZenDec (Carrier TOPSIS)' : tab === 'RTO' ? 'ZenRTO (Risk Scorer)' : 'ZenETA (Prediction)'}
                    </button>
                ))}
            </div>

            <div className="w-full max-w-5xl grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
                    {activeTab === 'DEC' && (
                        <form onSubmit={handleDecSubmit} className="space-y-4">
                            <h3 className="text-xl font-bold text-slate-900 mb-4">Run Unified Decision Engine</h3>

                            <div>
                                <label className="block text-sm font-medium text-slate-600 mb-1">Blast Radius (Shipments Impacted)</label>
                                <input type="number" value={decForm.blast_radius} onChange={e => setDecForm({ ...decForm, blast_radius: parseInt(e.target.value) })} className="w-full bg-slate-50 border border-slate-200 p-2.5 rounded-lg text-slate-900 shadow-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition-all" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-600 mb-1">Observation Confidence (%)</label>
                                <input type="number" value={decForm.confidence} onChange={e => setDecForm({ ...decForm, confidence: parseFloat(e.target.value) })} className="w-full bg-slate-50 border border-slate-200 p-2.5 rounded-lg text-slate-900 shadow-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition-all" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-600 mb-1">City (For AQI / Carbon)</label>
                                <input type="text" value={decForm.city} onChange={e => setDecForm({ ...decForm, city: e.target.value })} className="w-full bg-slate-50 border border-slate-200 p-2.5 rounded-lg text-slate-900 shadow-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition-all" />
                            </div>

                            <button type="submit" disabled={loading} className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2 px-4 rounded transition-colors mt-4">
                                {loading ? 'Running TOPSIS & Gemini...' : 'Optimize Carrier Swaps'}
                            </button>
                        </form>
                    )}

                    {activeTab === 'RTO' && (
                        <form onSubmit={handleRtoSubmit} className="space-y-4">
                            <h3 className="text-xl font-bold text-slate-900 mb-4">Predict Return-To-Origin (RTO) Risk</h3>

                            <div>
                                <label className="block text-sm font-medium text-slate-600 mb-1">Order Value (INR)</label>
                                <input type="number" value={rtoForm.order_value} onChange={e => setRtoForm({ ...rtoForm, order_value: parseFloat(e.target.value) })} className="w-full bg-slate-50 border border-slate-200 p-2.5 rounded-lg text-slate-900 shadow-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition-all" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-600 mb-1">Address / Pincode</label>
                                <div className="flex gap-2">
                                    <input type="text" value={rtoForm.address_raw} onChange={e => setRtoForm({ ...rtoForm, address_raw: e.target.value })} className="flex-1 bg-slate-50 border border-slate-200 p-2.5 rounded-lg text-slate-900 shadow-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition-all" />
                                    <input type="text" value={rtoForm.pincode} onChange={e => setRtoForm({ ...rtoForm, pincode: e.target.value })} className="w-24 bg-slate-50 border border-slate-200 p-2.5 rounded-lg text-slate-900 text-center shadow-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition-all" />
                                </div>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-600 mb-1">Payment Method</label>
                                <select value={rtoForm.payment_method} onChange={e => setRtoForm({ ...rtoForm, payment_method: e.target.value })} className="w-full bg-slate-50 border border-slate-200 p-2.5 rounded-lg text-slate-900 shadow-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition-all">
                                    <option value="COD">Cash on Delivery (COD)</option>
                                    <option value="PREPAID">Prepaid (Card/UPI)</option>
                                </select>
                            </div>

                            <button type="submit" disabled={loading} className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2 px-4 rounded transition-colors mt-4">
                                {loading ? 'Executing LightGBM...' : 'Score Order Risk'}
                            </button>
                        </form>
                    )}

                    {activeTab === 'ETA' && (
                        <form onSubmit={handleEtaSubmit} className="space-y-4">
                            <h3 className="text-xl font-bold text-slate-900 mb-4">Predict Dynamic ETA</h3>

                            <div>
                                <label className="block text-sm font-medium text-slate-600 mb-1">Shipment ID</label>
                                <input type="text" value={etaForm.shipment_id} onChange={e => setEtaForm({ ...etaForm, shipment_id: e.target.value })} className="w-full bg-slate-50 border border-slate-200 p-2.5 rounded-lg text-slate-900 shadow-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition-all" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-600 mb-1">Route Distance (KM)</label>
                                <input type="number" value={etaForm.route_distance_km} onChange={e => setEtaForm({ ...etaForm, route_distance_km: parseFloat(e.target.value) })} className="w-full bg-slate-50 border border-slate-200 p-2.5 rounded-lg text-slate-900 shadow-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition-all" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-600 mb-1">SLA Deadline (Minutes)</label>
                                <input type="number" value={etaForm.sla_deadline_minutes} onChange={e => setEtaForm({ ...etaForm, sla_deadline_minutes: parseInt(e.target.value) })} className="w-full bg-slate-50 border border-slate-200 p-2.5 rounded-lg text-slate-900 shadow-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition-all" />
                            </div>

                            <button type="submit" disabled={loading} className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2 px-4 rounded transition-colors mt-4">
                                {loading ? 'Fetching Weather & Running XGBoost...' : 'Estimate Arrival Time'}
                            </button>
                        </form>
                    )}
                </div>

                {/* Results Column */}
                <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] overflow-hidden flex flex-col">
                    <h3 className="text-xl font-bold text-slate-900 mb-4">Output Payload</h3>

                    {error && (
                        <div className="bg-red-50 border border-red-200 text-red-800 p-4 rounded-lg mb-4 overflow-auto shadow-sm">
                            <p className="font-bold border-b border-red-200 pb-2 mb-2">Error</p>
                            <pre className="text-sm whitespace-pre-wrap">{error}</pre>
                        </div>
                    )}

                    {result ? (
                        <div className="flex-1 overflow-auto bg-slate-50 p-4 rounded-lg border border-slate-200 shadow-inner">
                            {activeTab === 'RTO' && result.risk_level && (
                                <div className="mb-4 p-4 rounded-lg border bg-white border-slate-200 shadow-sm">
                                    <h4 className="font-bold text-slate-800">Action Taken: <span className="text-emerald-600">{result.action_taken}</span></h4>
                                    <p className="text-sm mt-1 text-slate-600">Risk Score: <span className="font-bold font-mono text-slate-800">{result.risk_level} ({result.rto_score})</span></p>
                                    {result.fraud_flags?.length > 0 && (
                                        <div className="mt-2 text-red-600 text-xs font-medium bg-red-50 p-2 rounded border border-red-100">
                                            ⚠️ {result.fraud_flags.map(f => typeof f === 'string' ? f : JSON.stringify(f)).join(', ')}
                                        </div>
                                    )}                </div>
                            )}

                            {activeTab === 'DEC' && result.autonomy_tier && (
                                <div className="mb-4 p-4 rounded-lg border bg-white border-slate-200 shadow-sm">
                                    <h4 className="font-bold text-slate-800">Autonomy Tier: <span className="text-purple-600">{result.autonomy_tier}</span></h4>
                                    <p className="text-sm mt-1 text-slate-600">{result.autonomy_reason}</p>
                                    <p className="text-sm mt-2 text-blue-600 font-medium">{result.recommended_action}</p>
                                </div>
                            )}

                            {activeTab === 'ETA' && result.estimated_minutes && (
                                <div className="mb-4 p-4 rounded-lg border bg-white border-slate-200 shadow-sm">
                                    <h4 className="font-bold text-slate-800">Estimated Transit: <span className="text-amber-600 font-extrabold">{(result.estimated_minutes / 60).toFixed(1)} hours</span></h4>
                                    <p className="text-sm mt-1 text-slate-600">SLA Breach Prob: {(result.sla_breach_prob * 100).toFixed(1)}%</p>
                                    <p className="text-xs mt-2 text-slate-700 bg-slate-100 p-3 rounded-md border border-slate-200">{result.gemini_summary}</p>
                                </div>
                            )}

                            <pre className="text-xs text-emerald-700 font-mono bg-emerald-50 p-4 rounded-lg border border-emerald-100">
                                {JSON.stringify(result, null, 2)}
                            </pre>
                        </div>
                    ) : !error && !loading && (
                        <div className="flex-1 flex items-center justify-center text-slate-400 border-2 border-dashed border-slate-200 bg-slate-50/50 rounded-lg p-8 text-center font-medium">
                            Waiting for user execution...
                        </div>
                    )}

                    {loading && (
                        <div className="flex-1 flex flex-col items-center justify-center text-emerald-500 space-y-4">
                            <div className="w-10 h-10 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
                            <p>Processing via Agent Mesh...</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
