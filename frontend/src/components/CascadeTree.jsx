import { useState, useEffect, useRef } from 'react'
import * as d3 from 'd3'

const RISK_COLOR = (score) => {
    if (score >= 0.8) return '#dc2626'   // CRITICAL — red-600
    if (score >= 0.6) return '#ea580c'   // HIGH     — orange-600
    if (score >= 0.3) return '#d97706'   // MEDIUM   — amber-600
    return '#16a34a'                      // LOW      — green-600
}

export default function CascadeTree() {
    const svgRef = useRef(null)
    const [treeData, setTreeData] = useState(null)
    const [atRisk, setAtRisk] = useState(0)
    const [connected, setConnected] = useState(false)

    // ── WebSocket connection ───────────────────────────────────
    useEffect(() => {
        const ws = new WebSocket('ws://localhost:8000/ws/anomalies')

        ws.onopen = () => setConnected(true)
        ws.onclose = () => setConnected(false)

        ws.onmessage = (msg) => {
            const payload = JSON.parse(msg.data)
            if (payload.type === 'cascade_tree') {
                setTreeData(payload.payload)
                setAtRisk(payload.payload.total_at_risk)
            }
        }

        return () => ws.close()
    }, [])

    // ── D3 force-directed graph ───────────────────────────────
    useEffect(() => {
        if (!treeData || !svgRef.current) return

        const { nodes, edges } = treeData
        const width = 900, height = 600

        d3.select(svgRef.current).selectAll('*').remove()  // clear previous

        const svg = d3.select(svgRef.current)
            .attr('width', width).attr('height', height)

        // Arrow marker for directed edges
        svg.append('defs').append('marker')
            .attr('id', 'arrow').attr('viewBox', '0 -5 10 10')
            .attr('refX', 18).attr('refY', 0)
            .attr('markerWidth', 6).attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path').attr('d', 'M0,-5L10,0L0,5').attr('fill', '#94a3b8')

        const simulation = d3.forceSimulation(nodes)
            .force('link', d3.forceLink(edges)
                .id(d => d.shipment_id).distance(80))
            .force('charge', d3.forceManyBody().strength(-200))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(25))

        const link = svg.append('g').selectAll('line')
            .data(edges).enter().append('line')
            .attr('stroke', '#cbd5e1').attr('stroke-width', 2)
            .attr('marker-end', 'url(#arrow)')

        const nodeGroup = svg.append('g').selectAll('g')
            .data(nodes).enter().append('g')
            .call(d3.drag()
                .on('start', (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
                .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
                .on('end', (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null })
            )

        // Node circles
        nodeGroup.append('circle')
            .attr('r', 14)
            .attr('fill', d => RISK_COLOR(d.risk_score))
            .attr('stroke', '#ffffff').attr('stroke-width', 2)

        // Node labels (shipment ID abbreviated)
        nodeGroup.append('text')
            .text(d => d.shipment_id.replace('SHP-', ''))
            .attr('dy', 4).attr('text-anchor', 'middle')
            .attr('font-size', 9).attr('fill', 'white').attr('font-weight', 'bold')

        // Tooltip on hover
        const tooltip = d3.select('body').append('div')
            .style('position', 'absolute').style('background', '#1e293b')
            .style('color', 'white').style('padding', '8px 12px')
            .style('border-radius', '6px').style('font-size', '12px')
            .style('pointer-events', 'none').style('opacity', 0)

        nodeGroup
            .on('mouseover', (event, d) => {
                tooltip.style('opacity', 1).html(
                    `<b>${d.shipment_id}</b><br/>
           Risk: ${(d.risk_score * 100).toFixed(0)}%<br/>
           SLA breach: ${(d.sla_breach_prob * 100).toFixed(0)}%<br/>
           Priority: ${d.recommended_priority}`
                ).style('left', event.pageX + 10 + 'px').style('top', event.pageY - 10 + 'px')
            })
            .on('mouseout', () => tooltip.style('opacity', 0))

        simulation.on('tick', () => {
            link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
            nodeGroup.attr('transform', d => `translate(${d.x},${d.y})`)
        })

        return () => { simulation.stop(); tooltip.remove() }
    }, [treeData])

    return (
        <div className='bg-white rounded-xl p-4'>
            <div className='flex items-center gap-3 mb-3'>
                <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]' : 'bg-slate-300'}`} />
                <span className='text-slate-500 font-medium text-sm'>Cascade Tree</span>
                {atRisk > 0 && (
                    <span className='ml-auto text-red-400 font-bold animate-pulse'>
                        {atRisk} shipments at risk
                    </span>
                )}
            </div>

            {!treeData && <p className='text-slate-400 text-sm'>Waiting for cascade event...</p>}

            <svg ref={svgRef} className='w-full' />
        </div>
    )
}
