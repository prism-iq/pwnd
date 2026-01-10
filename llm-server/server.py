#!/usr/bin/env python3
"""
HybridCore Local LLM Server
Zero-cost, full privacy, runs Phi-3 Mini locally
"""

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import threading

# Add llama_cpp to path
sys.path.insert(0, '/opt/rag/venv/lib/python3.13/site-packages')

from llama_cpp import Llama

# Configuration
MODEL_PATH = os.getenv('MODEL_PATH', '/opt/rag/llm/Phi-3-mini-4k-instruct-q4.gguf')
HOST = os.getenv('LLM_HOST', '127.0.0.1')
PORT = int(os.getenv('LLM_PORT', '8001'))
N_CTX = 4096
N_THREADS = 6

# Global model instance
llm = None
lock = threading.Lock()

def load_model():
    global llm
    print(f"[LLM] Loading model: {MODEL_PATH}")
    llm = Llama(
        model_path=MODEL_PATH,
        n_ctx=N_CTX,
        n_threads=N_THREADS,
        n_gpu_layers=0,  # CPU only
        verbose=False
    )
    print(f"[LLM] Model loaded successfully!")
    return llm

class LLMHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Quiet logging
        pass

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == '/health':
            self._send_json({
                'status': 'healthy',
                'model': os.path.basename(MODEL_PATH),
                'ready': llm is not None
            })
            return

        self._send_json({'error': 'Not found'}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == '/generate':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode()

            try:
                data = json.loads(body)
                prompt = data.get('prompt', '')
                max_tokens = data.get('max_tokens', 500)
                temperature = data.get('temperature', 0.3)

                if not prompt:
                    self._send_json({'error': 'No prompt provided'}, 400)
                    return

                # Generate response
                with lock:
                    response = llm(
                        prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        stop=['</s>', '<|end|>', '\n\n\n'],
                        echo=False
                    )

                text = response['choices'][0]['text'].strip()

                self._send_json({
                    'text': text,
                    'tokens_used': response['usage']['total_tokens']
                })

            except Exception as e:
                self._send_json({'error': str(e)}, 500)
            return

        if parsed.path == '/parse_intent':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode()

            try:
                data = json.loads(body)
                query = data.get('query', '')

                prompt = f"""Parse this query into JSON. Output ONLY valid JSON.

Intent types: "search" (find info), "connections" (who knows who), "timeline" (chronological), "explain" (explain concept)

Examples:
- "who is john" -> {{"intent": "search", "entities": ["john"], "filters": {{}}}}
- "who knows trump" -> {{"intent": "connections", "entities": ["trump"], "filters": {{}}}}
- "explain rust ownership" -> {{"intent": "explain", "entities": ["rust", "ownership"], "filters": {{}}}}

Query: {query}

JSON:"""

                with lock:
                    response = llm(
                        prompt,
                        max_tokens=100,
                        temperature=0.0,
                        stop=['</s>', '<|end|>', '\n\n'],
                        echo=False
                    )

                text = response['choices'][0]['text'].strip()

                # Parse JSON from response
                import re
                json_match = re.search(r'\{[^{}]+\}', text)
                if json_match:
                    intent = json.loads(json_match.group())
                else:
                    intent = {"intent": "search", "entities": [], "filters": {}}

                self._send_json({
                    'intent': intent,
                    'raw': text
                })

            except Exception as e:
                self._send_json({
                    'intent': {"intent": "search", "entities": [], "filters": {}},
                    'error': str(e)
                })
            return

        if parsed.path == '/analyze':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode()

            try:
                data = json.loads(body)
                query = data.get('query', '')
                context = data.get('context', '')

                prompt = f"""You are HybridCore, an intelligent assistant specialized in document analysis and OSINT investigation.

Question: {query}

Documents found:
{context[:3000]}

Instructions:
- Answer based on the documents above
- Be concise and direct
- Cite sources with [#1], [#2] etc.
- Extract key entities (names, emails, IPs, dates, amounts)
- If analyzing chat logs, identify participants and key events
- Suggest 2 relevant follow-up questions

Answer:"""

                with lock:
                    response = llm(
                        prompt,
                        max_tokens=500,
                        temperature=0.3,
                        stop=['</s>', '<|end|>'],
                        echo=False
                    )

                text = response['choices'][0]['text'].strip()

                # Extract suggested queries
                suggested = []
                lines = text.split('\n')
                for line in lines:
                    if line.strip().startswith(('1.', '2.', '3.', '-', '•')):
                        q = line.strip().lstrip('0123456789.-•) ').strip()
                        if '?' in q and len(q) > 10:
                            suggested.append(q)

                self._send_json({
                    'analysis': text,
                    'suggested_queries': suggested[:3],
                    'tokens_used': response['usage']['total_tokens']
                })

            except Exception as e:
                self._send_json({'error': str(e)}, 500)
            return

        self._send_json({'error': 'Not found'}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()


def main():
    load_model()

    server = HTTPServer((HOST, PORT), LLMHandler)
    print(f"[LLM] Server running on http://{HOST}:{PORT}")
    print(f"[LLM] Endpoints: /health, /generate, /parse_intent, /analyze")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[LLM] Shutting down...")
        server.shutdown()


if __name__ == '__main__':
    main()
