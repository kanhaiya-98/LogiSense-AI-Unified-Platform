import { useState, useEffect } from 'react'
import AnomalyBadge from './components/AnomalyBadge'
import CascadeTree from './components/CascadeTree'
import SwapNotification from './components/SwapNotification'
import WarehouseHeatmap from './components/WarehouseHeatmap'
import ExplainabilityDashboard from './components/features/explainability/ExplainabilityDashboard'
import ZenPlatform from './components/zen/ZenPlatform'

function App() {
    const [activeTab, setActiveTab] = useState('LOGISENSE');
    const [explainabilityData, setExplainabilityData] = useState(null);

    const fetchExplainabilityData = () => {
        fetch('http://localhost:8000/api/explainability/demo_data')
            .then(res => res.json())
            .then(data => setExplainabilityData(data))
            .catch(err => console.error("Explainability Demo Load Error:", err));
    };

    useEffect(() => {
        fetchExplainabilityData();
    }, []);

    const renderTabs = () => {
        return (
            <>
                <div className={`w-full max-w-4xl space-y-6 ${activeTab !== 'LOGISENSE' ? 'hidden' : ''}`}>
                    {/* F2: Reasoner Agent Cascade Tree */}
                    <div className="bg-white rounded-xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-slate-100">
                        <CascadeTree />
                    </div>

                    {/* F1: Observer Agent Feed */}
                    <div className="bg-white rounded-xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-slate-100">
                        <AnomalyBadge />
                    </div>

                    {/* F3: Actor Agent Swap Notifications */}
                    <div className="bg-white rounded-xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-slate-100">
                        <SwapNotification />
                    </div>

                    {/* F4: Warehouse Congestion Heatmap */}
                    <div className="bg-white rounded-xl overflow-hidden shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-slate-100">
                        <WarehouseHeatmap />
                    </div>
                </div>

                <div className={`w-full max-w-6xl text-slate-800 ${activeTab !== 'EXPLAINABILITY' ? 'hidden' : ''}`}>
                    {explainabilityData ? (
                        <ExplainabilityDashboard
                            predictions={explainabilityData.predictions}
                            features={explainabilityData.features}
                            modelKey={explainabilityData.modelKey}
                            onRegenerate={fetchExplainabilityData}
                        />
                    ) : (
                        <div className="text-center py-20 text-slate-400">Loading ML Explanation Models...</div>
                    )}
                </div>

                <div className={`w-full max-w-6xl h-[800px] bg-white rounded-xl overflow-hidden shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-slate-100 ${activeTab !== 'ZEN' ? 'hidden' : ''}`}>
                    <ZenPlatform />
                </div>
            </>
        );
    };

    return (
        <div className="min-h-screen bg-slate-50 flex flex-col items-center py-10 w-full px-4 font-sans">
            <div className="flex flex-col items-center mb-8">
                <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight mb-2">LogiSense AI Unified Platform</h1>
                <p className="text-slate-500 font-medium">Multi-Agent Intelligence & Autonomous Supply Chain Recovery</p>
            </div>

            {/* Navigation Tabs */}
            <div className="flex space-x-2 mb-8 bg-white p-1.5 rounded-xl shadow-sm border border-slate-200">
                <button
                    onClick={() => setActiveTab('LOGISENSE')}
                    className={`px-6 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 ease-in-out ${activeTab === 'LOGISENSE' ? 'bg-gradient-to-r from-blue-500 to-indigo-500 text-white shadow-md transform scale-[1.02]' : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'}`}
                >
                    LogiSense (F1-F4)
                </button>
                <button
                    onClick={() => setActiveTab('EXPLAINABILITY')}
                    className={`px-6 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 ease-in-out ${activeTab === 'EXPLAINABILITY' ? 'bg-gradient-to-r from-purple-500 to-fuchsia-500 text-white shadow-md transform scale-[1.02]' : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'}`}
                >
                    Agent Explainability (F8)
                </button>
                <button
                    onClick={() => setActiveTab('ZEN')}
                    className={`px-6 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 ease-in-out ${activeTab === 'ZEN' ? 'bg-gradient-to-r from-emerald-400 to-teal-500 text-white shadow-md transform scale-[1.02]' : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'}`}
                >
                    Zen Platform (Dec / RTO / ETA)
                </button>
            </div>

            {renderTabs()}
        </div>
    )
}

export default App
