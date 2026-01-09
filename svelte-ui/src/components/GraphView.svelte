<script>
  import { onMount } from 'svelte';

  let canvas;
  let ctx;
  let nodes = [];
  let edges = [];
  let selectedNode = null;
  let isDragging = false;
  let dragNode = null;
  let offset = { x: 0, y: 0 };
  let zoom = 1;

  onMount(async () => {
    ctx = canvas.getContext('2d');
    await loadGraphData();
    animate();

    // Handle resize
    window.addEventListener('resize', handleResize);
    handleResize();

    return () => window.removeEventListener('resize', handleResize);
  });

  async function loadGraphData() {
    try {
      const [nodesRes, edgesRes] = await Promise.all([
        fetch('/api/nodes?limit=100'),
        fetch('/api/edges?limit=200')
      ]);

      const nodesData = await nodesRes.json();
      const edgesData = await edgesRes.json();

      // Initialize node positions
      nodes = nodesData.map((n, i) => ({
        ...n,
        x: 200 + Math.cos(i * 0.5) * (100 + i * 3),
        y: 200 + Math.sin(i * 0.5) * (100 + i * 3),
        vx: 0,
        vy: 0,
        radius: getNodeRadius(n.type)
      }));

      edges = edgesData.map(e => ({
        ...e,
        source: nodes.find(n => n.id === e.from_node_id),
        target: nodes.find(n => n.id === e.to_node_id)
      })).filter(e => e.source && e.target);

    } catch (e) {
      console.error('Failed to load graph:', e);
    }
  }

  function getNodeRadius(type) {
    const sizes = {
      person: 20,
      organization: 25,
      location: 15,
      email: 10
    };
    return sizes[type] || 12;
  }

  function getNodeColor(type) {
    const colors = {
      person: '#667eea',
      organization: '#764ba2',
      location: '#2ed573',
      email: '#ff9800',
      date: '#ffc107'
    };
    return colors[type] || '#888';
  }

  function handleResize() {
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
  }

  function animate() {
    if (!ctx) return;

    // Clear
    ctx.fillStyle = '#0a0a0f';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Apply physics
    applyForces();

    // Draw edges
    ctx.strokeStyle = 'rgba(102, 126, 234, 0.3)';
    ctx.lineWidth = 1;
    edges.forEach(e => {
      if (e.source && e.target) {
        ctx.beginPath();
        ctx.moveTo(e.source.x * zoom + offset.x, e.source.y * zoom + offset.y);
        ctx.lineTo(e.target.x * zoom + offset.x, e.target.y * zoom + offset.y);
        ctx.stroke();
      }
    });

    // Draw nodes
    nodes.forEach(node => {
      const x = node.x * zoom + offset.x;
      const y = node.y * zoom + offset.y;
      const r = node.radius * zoom;

      // Glow effect for selected
      if (selectedNode === node) {
        ctx.beginPath();
        ctx.arc(x, y, r + 5, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(102, 126, 234, 0.3)';
        ctx.fill();
      }

      // Node circle
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = getNodeColor(node.type);
      ctx.fill();

      // Node label
      if (zoom > 0.5) {
        ctx.font = `${10 * zoom}px sans-serif`;
        ctx.fillStyle = '#e0e0e0';
        ctx.textAlign = 'center';
        ctx.fillText(truncate(node.name, 15), x, y + r + 12 * zoom);
      }
    });

    requestAnimationFrame(animate);
  }

  function applyForces() {
    const centerX = canvas.width / 2 / zoom - offset.x / zoom;
    const centerY = canvas.height / 2 / zoom - offset.y / zoom;

    nodes.forEach(node => {
      // Centering force
      node.vx += (centerX - node.x) * 0.001;
      node.vy += (centerY - node.y) * 0.001;

      // Repulsion between nodes
      nodes.forEach(other => {
        if (node === other) return;
        const dx = node.x - other.x;
        const dy = node.y - other.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        if (dist < 100) {
          const force = 50 / (dist * dist);
          node.vx += (dx / dist) * force;
          node.vy += (dy / dist) * force;
        }
      });

      // Apply velocity with damping
      if (node !== dragNode) {
        node.x += node.vx;
        node.y += node.vy;
        node.vx *= 0.9;
        node.vy *= 0.9;
      }
    });

    // Edge attraction
    edges.forEach(e => {
      if (!e.source || !e.target) return;
      const dx = e.target.x - e.source.x;
      const dy = e.target.y - e.source.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const force = (dist - 100) * 0.01;
      e.source.vx += (dx / dist) * force;
      e.source.vy += (dy / dist) * force;
      e.target.vx -= (dx / dist) * force;
      e.target.vy -= (dy / dist) * force;
    });
  }

  function truncate(str, len) {
    return str?.length > len ? str.slice(0, len) + '...' : str || '';
  }

  function handleMouseDown(e) {
    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left - offset.x) / zoom;
    const y = (e.clientY - rect.top - offset.y) / zoom;

    // Find clicked node
    const clicked = nodes.find(n => {
      const dx = n.x - x;
      const dy = n.y - y;
      return Math.sqrt(dx * dx + dy * dy) < n.radius;
    });

    if (clicked) {
      dragNode = clicked;
      selectedNode = clicked;
    } else {
      isDragging = true;
    }
  }

  function handleMouseMove(e) {
    if (dragNode) {
      const rect = canvas.getBoundingClientRect();
      dragNode.x = (e.clientX - rect.left - offset.x) / zoom;
      dragNode.y = (e.clientY - rect.top - offset.y) / zoom;
    } else if (isDragging) {
      offset.x += e.movementX;
      offset.y += e.movementY;
    }
  }

  function handleMouseUp() {
    dragNode = null;
    isDragging = false;
  }

  function handleWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    zoom = Math.max(0.2, Math.min(3, zoom * delta));
  }
</script>

<div class="graph-container">
  <canvas
    bind:this={canvas}
    on:mousedown={handleMouseDown}
    on:mousemove={handleMouseMove}
    on:mouseup={handleMouseUp}
    on:mouseleave={handleMouseUp}
    on:wheel={handleWheel}
  ></canvas>

  {#if selectedNode}
    <div class="node-info">
      <div class="info-type" style="background: {getNodeColor(selectedNode.type)}">{selectedNode.type}</div>
      <h4>{selectedNode.name}</h4>
      <p>ID: {selectedNode.id}</p>
    </div>
  {/if}

  <div class="graph-controls">
    <button on:click={() => zoom *= 1.2}>+</button>
    <button on:click={() => zoom *= 0.8}>−</button>
    <button on:click={() => { zoom = 1; offset = { x: 0, y: 0 }; }}>Reset</button>
  </div>
</div>

<style>
  .graph-container {
    position: relative;
    width: 100%;
    height: calc(100vh - 200px);
    min-height: 400px;
    background: #0a0a0f;
    border-radius: 8px;
    overflow: hidden;
  }

  canvas {
    width: 100%;
    height: 100%;
    cursor: grab;
  }

  canvas:active {
    cursor: grabbing;
  }

  .node-info {
    position: absolute;
    top: 1rem;
    right: 1rem;
    background: #1a1a2e;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    padding: 1rem;
    min-width: 200px;
  }

  .info-type {
    display: inline-block;
    font-size: 0.75rem;
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    color: white;
    text-transform: uppercase;
    margin-bottom: 0.5rem;
  }

  .node-info h4 {
    margin: 0.5rem 0;
    color: #e0e0e0;
  }

  .node-info p {
    margin: 0;
    font-size: 0.875rem;
    color: #888;
  }

  .graph-controls {
    position: absolute;
    bottom: 1rem;
    left: 1rem;
    display: flex;
    gap: 0.5rem;
  }

  .graph-controls button {
    width: 36px;
    height: 36px;
    background: #2a2a4a;
    border: 1px solid #3a3a5a;
    border-radius: 6px;
    color: #e0e0e0;
    font-size: 1.25rem;
    cursor: pointer;
    transition: background 0.15s;
  }

  .graph-controls button:hover {
    background: #3a3a5a;
  }

  .graph-controls button:last-child {
    width: auto;
    padding: 0 0.75rem;
    font-size: 0.875rem;
  }
</style>
