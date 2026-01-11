#!/usr/bin/env python3
"""
Phi-3 Subprocess Inference Server
Isolated process to prevent segfaults from crashing main server.
Communicates via stdin/stdout JSON.
"""
import sys
import json
import signal
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger("phi3")

MODEL_PATH = "/opt/rag/llm/Phi-3-mini-4k-instruct-q4.gguf"

def load_model():
    """Load Phi-3 model"""
    try:
        from llama_cpp import Llama
        log.info("Loading Phi-3 model...")
        model = Llama(
            model_path=MODEL_PATH,
            n_ctx=2048,
            n_threads=4,
            n_batch=256,
            n_gpu_layers=0,
            use_mlock=False,
            verbose=False,
        )
        log.info("Phi-3 model loaded")
        return model
    except Exception as e:
        log.error(f"Failed to load model: {e}")
        return None

def generate(model, prompt: str, max_tokens: int = 384, temperature: float = 0.3) -> str:
    """Generate response from prompt"""
    try:
        response = model(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["<|end|>", "<|user|>", "<|system|>", "</s>", "\n\n\n"],
            echo=False,
        )
        return response["choices"][0]["text"].strip()
    except Exception as e:
        log.error(f"Generation error: {e}")
        return ""

def main():
    # Handle signals gracefully
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    model = load_model()
    if not model:
        print(json.dumps({"error": "Failed to load model"}), flush=True)
        sys.exit(1)

    # Signal ready
    print(json.dumps({"status": "ready"}), flush=True)

    # Process requests from stdin
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            prompt = request.get("prompt", "")
            max_tokens = request.get("max_tokens", 384)
            temperature = request.get("temperature", 0.3)

            if not prompt:
                print(json.dumps({"error": "No prompt provided"}), flush=True)
                continue

            result = generate(model, prompt, max_tokens, temperature)
            print(json.dumps({"result": result}), flush=True)

        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON"}), flush=True)
        except Exception as e:
            print(json.dumps({"error": str(e)}), flush=True)

if __name__ == "__main__":
    main()
