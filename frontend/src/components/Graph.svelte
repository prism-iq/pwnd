<script>
  import { onMount, onDestroy } from 'svelte'
  import { Network } from 'vis-network'
  import { DataSet } from 'vis-data'
  import { getGraph } from '../lib/api.js'
  import { notify } from '../stores/app.js'

  let container
  let network
  let loading = true
  let nodeCount = 0
  let edgeCount = 0

  const nodes = new DataSet()
  const edges = new DataSet()

  const options = {
    nodes: {
      shape: 'dot',
      size: 16,
      font: {
        size: 12,
        color: '#e5e5e5'
      },
      borderWidth: 2,
      shadow: true
    },
    edges: {
      width: 1,
      color: { color: '#404040', highlight: '#3b82f6' },
      smooth: {
        type: 'continuous'
      }
    },
    physics: {
      stabilization: {
        iterations: 100
      },
      barnesHut: {
        gravitationalConstant: -3000,
        springConstant: 0.04,
        springLength: 95
      }
    },
    interaction: {
      hover: true,
      tooltipDelay: 200
    },
    groups: {
      person: { color: { background: '#3b82f6', border: '#2563eb' } },
      organization: { color: { background: '#8b5cf6', border: '#7c3aed' } },
      location: { color: { background: '#22c55e', border: '#16a34a' } },
      document: { color: { background: '#f59e0b', border: '#d97706' } },
      email: { color: { background: '#ef4444', border: '#dc2626' } },
      default: { color: { background: '#6b7280', border: '#4b5563' } }
    }
  }

  onMount(async () => {
    try {
      const data = await getGraph()

      // Process nodes
      const graphNodes = (data.nodes || []).map(n => ({
        id: n.id,
        label: n.name || n.label || `Node ${n.id}`,
        group: n.type || 'default',
        title: `${n.type || 'entity'}: ${n.name || n.label}`
      }))

      // Process edges
      const graphEdges = (data.edges || data.relationships || []).map((e, i) => ({
        id: i,
        from: e.source || e.from,
        to: e.target || e.to,
        label: e.type || e.label || '',
        title: e.type || ''
      }))

      nodes.add(graphNodes)
      edges.add(graphEdges)

      nodeCount = graphNodes.length
      edgeCount = graphEdges.length

      // Create network
      network = new Network(container, { nodes, edges }, options)

      network.on('click', (params) => {
        if (params.nodes.length > 0) {
          const nodeId = params.nodes[0]
          const node = nodes.get(nodeId)
          notify(`Selected: ${node.label}`, 'info')
        }
      })

      network.on('stabilizationIterationsDone', () => {
        loading = false
      })

    } catch (e) {
      notify('Failed to load graph: ' + e.message, 'error')
      loading = false
    }
  })

  onDestroy(() => {
    if (network) {
      network.destroy()
    }
  })

  function zoomIn() {
    if (network) {
      const scale = network.getScale()
      network.moveTo({ scale: scale * 1.3 })
    }
  }

  function zoomOut() {
    if (network) {
      const scale = network.getScale()
      network.moveTo({ scale: scale / 1.3 })
    }
  }

  function fitAll() {
    if (network) {
      network.fit()
    }
  }
</script>

<div class="graph-container">
  <div class="graph-header">
    <div class="stats">
      <span>{nodeCount} nodes</span>
      <span>{edgeCount} edges</span>
    </div>
    <div class="controls">
      <button on:click={zoomIn}>+</button>
      <button on:click={zoomOut}>-</button>
      <button on:click={fitAll}>Fit</button>
    </div>
  </div>

  <div class="graph-area" bind:this={container}>
    {#if loading}
      <div class="loading">Loading graph...</div>
    {/if}
  </div>

  <div class="legend">
    <span class="legend-item person">Person</span>
    <span class="legend-item organization">Organization</span>
    <span class="legend-item location">Location</span>
    <span class="legend-item document">Document</span>
    <span class="legend-item email">Email</span>
  </div>
</div>

<style>
  .graph-container {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: #0a0a0a;
  }

  .graph-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 15px 20px;
    border-bottom: 1px solid #252525;
  }

  .stats {
    display: flex;
    gap: 15px;
    font-size: 13px;
    color: #888;
  }

  .controls {
    display: flex;
    gap: 5px;
  }

  .controls button {
    width: 32px;
    height: 32px;
    border: 1px solid #333;
    background: #1a1a1a;
    color: #e5e5e5;
    border-radius: 6px;
    cursor: pointer;
    font-size: 16px;
  }

  .controls button:hover {
    border-color: #3b82f6;
  }

  .graph-area {
    flex: 1;
    position: relative;
  }

  .loading {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    color: #666;
  }

  .legend {
    display: flex;
    gap: 15px;
    padding: 10px 20px;
    border-top: 1px solid #252525;
    justify-content: center;
    flex-wrap: wrap;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: #888;
  }

  .legend-item::before {
    content: '';
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }

  .legend-item.person::before { background: #3b82f6; }
  .legend-item.organization::before { background: #8b5cf6; }
  .legend-item.location::before { background: #22c55e; }
  .legend-item.document::before { background: #f59e0b; }
  .legend-item.email::before { background: #ef4444; }
</style>
