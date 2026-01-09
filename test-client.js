#!/usr/bin/env node
/**
 * L Investigation - Node.js Test Client
 * Tests API endpoints and measures performance
 */

const http = require('http');

const API_BASE = 'http://localhost:8002';

const QUERIES = [
    'epstein connections',
    'maxwell testimony',
    'virgin islands',
    'flight logs',
    'settlement'
];

async function fetchSSE(path) {
    return new Promise((resolve, reject) => {
        const start = Date.now();
        let response = '';
        let sources = 0;
        let hasAnalysis = false;
        let hasNext = false;

        const url = new URL(path, API_BASE);
        http.get(url, (res) => {
            res.on('data', (chunk) => {
                const lines = chunk.toString().split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.type === 'chunk') {
                                response += data.text;
                                if (data.text.includes('ANALYSIS')) hasAnalysis = true;
                                if (data.text.toLowerCase().includes('next')) hasNext = true;
                            } else if (data.type === 'sources') {
                                sources = data.ids?.length || 0;
                            }
                        } catch (e) {}
                    }
                }
            });

            res.on('end', () => {
                const elapsed = Date.now() - start;
                const quality = hasAnalysis && hasNext ? 'GOOD' : 'OK';
                resolve({ elapsed, sources, quality, responseLen: response.length });
            });

            res.on('error', reject);
        }).on('error', reject);
    });
}

async function runTests() {
    console.log('======================================================');
    console.log('L Investigation - Node.js Test Client');
    console.log('======================================================\n');

    const results = [];

    for (let i = 0; i < QUERIES.length; i++) {
        const query = QUERIES[i];
        process.stdout.write(`[${i + 1}/${QUERIES.length}] ${query}... `);

        try {
            const result = await fetchSSE(`/api/ask?q=${encodeURIComponent(query)}&conversation_id=nodejs_test`);
            console.log(`${result.elapsed}ms | ${result.sources} sources | ${result.quality}`);
            results.push(result);
        } catch (e) {
            console.log(`ERROR: ${e.message}`);
        }
    }

    // Summary
    const avgTime = results.reduce((a, r) => a + r.elapsed, 0) / results.length;
    const goodCount = results.filter(r => r.quality === 'GOOD').length;

    console.log('\n======================================================');
    console.log('SUMMARY');
    console.log('======================================================');
    console.log(`Avg time: ${Math.round(avgTime)}ms`);
    console.log(`Quality: ${goodCount}/${results.length} GOOD`);
    console.log('======================================================');

    process.exit(goodCount >= 4 ? 0 : 1);
}

runTests().catch(console.error);
