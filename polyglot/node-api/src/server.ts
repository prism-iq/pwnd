/**
 * L Investigation - Node.js Orchestrator (LUNGS)
 *
 * The lungs breathe data in/out:
 * - SSE streaming to clients (exhale)
 * - Fetch from all services (inhale)
 * - Load balancing across workers
 * - Real-time event distribution
 */

import express, { Request, Response, NextFunction } from 'express';
import { createServer } from 'http';
import { Server as SocketIO } from 'socket.io';
import { EventEmitter } from 'events';

const app = express();
const server = createServer(app);
const ALLOWED_ORIGINS = [
  'https://pwnd.icu',
  'https://www.pwnd.icu',
  'http://localhost:5173',
  'http://127.0.0.1:5173',
];

const io = new SocketIO(server, {
  cors: {
    origin: ALLOWED_ORIGINS,
    methods: ['GET', 'POST'],
    credentials: true,
  }
});

// Service endpoints (the other organs)
const ORGANS = {
  brain: 'http://127.0.0.1:8085',    // Go gateway
  cells: 'http://127.0.0.1:9001',    // Rust extraction
  veins: 'http://127.0.0.1:8002',    // Python LLM
  blood: 'http://127.0.0.1:9003',    // C++ search
};

// Breathing metrics
const metrics = {
  inhales: 0,      // requests received
  exhales: 0,      // responses sent
  oxygen: 0,       // successful ops
  co2: 0,          // errors
  heartbeats: 0,   // health checks
  startTime: Date.now(),
};

// Event bus for organ communication
const bloodstream = new EventEmitter();
bloodstream.setMaxListeners(100);

app.use(express.json({ limit: '10mb' }));

// =============================================================================
// BREATHING MIDDLEWARE (inhale/exhale tracking)
// =============================================================================

app.use((req: Request, _res: Response, next: NextFunction) => {
  metrics.inhales++;
  (req as any).breatheStart = Date.now();
  next();
});

// =============================================================================
// SSE EXHALE - Stream results to clients
// =============================================================================

app.get('/breathe/:sessionId', (req: Request, res: Response) => {
  const { sessionId } = req.params;

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');

  // Exhale function
  const exhale = (data: any) => {
    res.write(`data: ${JSON.stringify(data)}\n\n`);
    metrics.exhales++;
  };

  // Listen on bloodstream for this session
  const listener = (data: any) => exhale(data);
  bloodstream.on(`session:${sessionId}`, listener);

  // Heartbeat to keep connection alive
  const heartbeat = setInterval(() => {
    res.write(': heartbeat\n\n');
    metrics.heartbeats++;
  }, 15000);

  req.on('close', () => {
    clearInterval(heartbeat);
    bloodstream.off(`session:${sessionId}`, listener);
  });
});

// =============================================================================
// INVESTIGATE - Full body coordination
// =============================================================================

app.post('/investigate', async (req: Request, res: Response) => {
  const { query, sessionId, domain } = req.body;
  const session = sessionId || crypto.randomUUID();

  try {
    // Phase 1: Brain decides strategy (Go)
    const strategy = await callOrgan('brain', '/analyze', { query, domain });
    bloodstream.emit(`session:${session}`, { phase: 'strategy', data: strategy });

    // Phase 2: Cells extract entities (Rust) - parallel
    const extractPromise = callOrgan('cells', '/extract', { text: query });

    // Phase 3: Blood searches index (C++) - parallel
    const searchPromise = callOrgan('blood', '/search', { query, limit: 20 });

    const [entities, searchResults] = await Promise.all([extractPromise, searchPromise]);
    bloodstream.emit(`session:${session}`, { phase: 'extraction', entities, searchResults });

    // Phase 4: Veins synthesize with LLM (Python)
    const synthesis = await callOrgan('veins', '/synthesize', {
      query,
      entities,
      context: searchResults,
      strategy,
    });

    bloodstream.emit(`session:${session}`, { phase: 'synthesis', data: synthesis });

    metrics.oxygen++;
    res.json({
      success: true,
      sessionId: session,
      result: synthesis,
      entities,
      searchResults,
      timing: Date.now() - (req as any).breatheStart,
    });

  } catch (error: any) {
    metrics.co2++;
    bloodstream.emit(`session:${session}`, { phase: 'error', error: error.message });
    res.status(500).json({ error: error.message });
  }
});

// =============================================================================
// ORGAN CALLS - Internal service communication
// =============================================================================

async function callOrgan(organ: keyof typeof ORGANS, path: string, data: any): Promise<any> {
  const url = `${ORGANS[organ]}${path}`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(30000),
    });

    if (!response.ok) {
      throw new Error(`${organ} responded with ${response.status}`);
    }

    return response.json();
  } catch (error: any) {
    // Fallback for unavailable organs
    console.warn(`Organ ${organ} unavailable: ${error.message}`);
    return { fallback: true, organ, error: error.message };
  }
}

// =============================================================================
// HEALTH CHECK - Vital signs
// =============================================================================

app.get('/health', async (_req: Request, res: Response) => {
  const vitals: Record<string, any> = {
    status: 'breathing',
    uptime: Math.floor((Date.now() - metrics.startTime) / 1000),
    metrics: { ...metrics },
    organs: {},
  };

  // Check each organ
  for (const [name, url] of Object.entries(ORGANS)) {
    try {
      const start = Date.now();
      const resp = await fetch(`${url}/health`, { signal: AbortSignal.timeout(2000) });
      vitals.organs[name] = {
        status: resp.ok ? 'healthy' : 'degraded',
        latency: Date.now() - start,
      };
    } catch {
      vitals.organs[name] = { status: 'offline', latency: -1 };
    }
  }

  res.json(vitals);
});

// =============================================================================
// SOCKET.IO - Real-time bidirectional breathing
// =============================================================================

io.on('connection', (socket) => {
  console.log(`Client connected: ${socket.id}`);

  socket.on('subscribe', (sessionId: string) => {
    socket.join(`session:${sessionId}`);

    // Forward bloodstream events to socket
    const listener = (data: any) => socket.emit('update', data);
    bloodstream.on(`session:${sessionId}`, listener);

    socket.on('disconnect', () => {
      bloodstream.off(`session:${sessionId}`, listener);
    });
  });

  socket.on('investigate', async (data: { query: string; domain?: string }) => {
    const sessionId = crypto.randomUUID();
    socket.join(`session:${sessionId}`);
    socket.emit('session', { sessionId });

    // Trigger investigation
    try {
      const result = await callOrgan('brain', '/investigate', { ...data, sessionId });
      socket.emit('complete', result);
    } catch (error: any) {
      socket.emit('error', { message: error.message });
    }
  });
});

// =============================================================================
// STARTUP
// =============================================================================

const PORT = process.env.PORT || 3000;

server.listen(PORT, () => {
  console.log(`
╔═══════════════════════════════════════════════════════════╗
║       L Investigation - Node.js LUNGS                     ║
║       Breathing data in and out                           ║
╠═══════════════════════════════════════════════════════════╣
║  Endpoints:                                               ║
║    GET  /breathe/:id  - SSE stream (exhale)              ║
║    POST /investigate  - Full investigation               ║
║    GET  /health       - Vital signs                      ║
║    WS   /            - Socket.IO real-time               ║
╠═══════════════════════════════════════════════════════════╣
║  Connected Organs:                                        ║
║    Brain (Go)     → ${ORGANS.brain.padEnd(25)}           ║
║    Cells (Rust)   → ${ORGANS.cells.padEnd(25)}           ║
║    Veins (Python) → ${ORGANS.veins.padEnd(25)}           ║
║    Blood (C++)    → ${ORGANS.blood.padEnd(25)}           ║
╚═══════════════════════════════════════════════════════════╝
  `);
});

export { app, server, bloodstream };
