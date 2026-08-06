import { useMemo } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
} from 'reactflow'
import 'reactflow/dist/style.css'

interface GraphNode {
  id: string
  label: string
  type?: string
}

interface GraphEdge {
  source: string
  target: string
  label?: string
}

interface Props {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

// 节点类型 → 颜色映射（Stock / Industry / Event / Policy / Competitor 等）
const TYPE_COLORS: Record<string, string> = {
  Stock: '#3b82f6',
  Company: '#3b82f6',
  Industry: '#22c55e',
  Event: '#f59e0b',
  Policy: '#a855f7',
  Competitor: '#ef4444',
  Person: '#06b6d4',
  Product: '#ec4899',
  Technology: '#14b8a6',
  Organization: '#6366f1',
  Country: '#84cc16',
  Metric: '#64748b',
  Concept: '#8b5cf6',
}

/**
 * 个股知识图谱力导向图（ReactFlow 渲染）
 * 环形自动布局，节点按类型着色，AGE 不可用时由父组件降级为空态。
 */
export function StockKnowledgeGraph({ nodes, edges }: Props) {
  const { rfNodes, rfEdges } = useMemo(() => {
    const N = nodes.length
    const cx = 300
    const cy = 250
    const radius = 210

    const rfNodes: Node[] = nodes.map((n, i) => {
      const angle = N > 1 ? (2 * Math.PI * i) / N : 0
      const color = TYPE_COLORS[n.type ?? ''] ?? '#6b7280'
      return {
        id: n.id,
        position:
          N === 1
            ? { x: cx, y: cy }
            : { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) },
        data: { label: n.label },
        style: {
          background: color,
          color: '#ffffff',
          borderRadius: '8px',
          padding: '8px 12px',
          fontSize: '12px',
          fontWeight: 600,
          border: '1px solid rgba(255,255,255,0.4)',
        },
      }
    })

    const rfEdges: Edge[] = edges
      .filter((e) => e.source && e.target)
      .map((e, i) => ({
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        label: e.label,
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
        labelStyle: { fontSize: 10, fill: '#64748b' },
      }))

    return { rfNodes, rfEdges }
  }, [nodes, edges])

  return (
    <div className="h-[420px] w-full rounded-lg border bg-card">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesConnectable={false}
        deleteKeyCode={null}
        proOptions={{ hideAttribution: true }}
        minZoom={0.3}
        maxZoom={2}
      >
        <Controls />
        <MiniMap pannable zoomable />
        <Background color="#94a3b8" gap={16} size={1} />
      </ReactFlow>
    </div>
  )
}