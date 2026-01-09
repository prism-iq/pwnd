"""
LLM Backend for L Investigation Framework
Mistral 7B via llama-cpp-python
"""

import json
import logging
from typing import Optional, Dict, Any, Generator
from pathlib import Path

from llama_cpp import Llama

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("llm")

# Config - Optimized for Phi-3-Mini on i7-6700
MODEL_PATH = "/opt/rag/llm/Phi-3-mini-4k-instruct-q4.gguf"
CONTEXT_LENGTH = 2048  # Reduced for faster inference
N_THREADS = 4  # i7-6700 has 4 cores, 8 threads (use 4 for balance)
N_BATCH = 512  # Batch size for prompt processing
USE_MLOCK = True  # Lock model in RAM for consistency


class LLMBackend:
    """Singleton LLM backend"""
    
    _instance: Optional["LLMBackend"] = None
    _model: Optional[Llama] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def load(self, model_path: str = MODEL_PATH) -> bool:
        """Load model into memory"""
        if self._model is not None:
            log.info("Model already loaded")
            return True
        
        if not Path(model_path).exists():
            log.error(f"Model not found: {model_path}")
            return False
        
        log.info(f"Loading model: {model_path}")
        try:
            self._model = Llama(
                model_path=model_path,
                n_ctx=CONTEXT_LENGTH,
                n_threads=N_THREADS,
                n_batch=N_BATCH,
                n_gpu_layers=0,  # CPU only
                use_mlock=USE_MLOCK,  # Lock in RAM
                verbose=False,
            )
            log.info(f"Model loaded: Phi-3-Mini (ctx={CONTEXT_LENGTH}, threads={N_THREADS}, batch={N_BATCH})")
            return True
        except Exception as e:
            log.error(f"Failed to load model: {e}")
            return False
    
    def unload(self):
        """Unload model from memory"""
        self._model = None
        log.info("Model unloaded")
    
    @property
    def is_loaded(self) -> bool:
        return self._model is not None
    
    def generate(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7, top_p: float = 0.9,
                 stop: Optional[list] = None) -> str:
        """Generate completion"""
        if not self.is_loaded:
            if not self.load():
                return ""
        
        try:
            response = self._model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=stop or ["</s>", "[/INST]"],
                echo=False,
            )
            return response["choices"][0]["text"].strip()
        except Exception as e:
            log.error(f"Generation failed: {e}")
            return ""
    
    def generate_stream(self, prompt: str, max_tokens: int = 512,
                        temperature: float = 0.7) -> Generator[str, None, None]:
        """Generate completion with streaming"""
        if not self.is_loaded:
            if not self.load():
                return
        
        try:
            for chunk in self._model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=["</s>", "[/INST]"],
                stream=True,
            ):
                yield chunk["choices"][0]["text"]
        except Exception as e:
            log.error(f"Stream generation failed: {e}")
    
    def chat(self, messages: list, max_tokens: int = 512,
             temperature: float = 0.7) -> str:
        """Chat completion (Mistral instruct format)"""
        # Build Mistral instruct prompt
        prompt = "<s>"
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"[INST] {content} [/INST]"
            elif role == "user":
                prompt += f"[INST] {content} [/INST]"
            elif role == "assistant":
                prompt += f" {content}</s>"
        
        return self.generate(prompt, max_tokens=max_tokens, temperature=temperature)
    
    def analyze(self, query: str, context: str, system_prompt: str) -> Dict[str, Any]:
        """Analyze query with context, return structured response"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuery:\n{query}"},
        ]
        
        response = self.chat(messages, max_tokens=1024, temperature=0.7)
        
        # Try to parse as JSON
        try:
            # Find JSON block
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "{" in response:
                start = response.index("{")
                end = response.rindex("}") + 1
                json_str = response[start:end]
            else:
                return {"raw": response, "confidence": 50}
            
            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            return {"raw": response, "confidence": 50}
    
    def extract_entities(self, text: str) -> list:
        """Extract entities from text"""
        prompt = f"""[INST] Extract all entities from this text. Return JSON array.
Each entity: {{"name": "...", "type": "person|organization|location|event|document|concept|asset|communication", "confidence": 0-100}}

Text: {text[:2000]}

Return ONLY the JSON array, no other text. [/INST]"""
        
        response = self.generate(prompt, max_tokens=1024, temperature=0.3)
        
        try:
            if "[" in response:
                start = response.index("[")
                end = response.rindex("]") + 1
                return json.loads(response[start:end])
        except:
            pass
        return []
    
    def extract_relationships(self, text: str, entities: list) -> list:
        """Extract relationships between known entities"""
        entity_names = [e.get("name", "") for e in entities[:20]]
        
        prompt = f"""[INST] Find relationships between these entities in the text.
Entities: {', '.join(entity_names)}

Return JSON array. Each relationship:
{{"from": "entity_name", "to": "entity_name", "type": "knows|works_for|owns|located_at|participated_in|mentioned_in|sent|received|funded|controls|related_to|witnessed|accused_of|confirmed_by|contradicts", "confidence": 0-100, "context": "brief description"}}

Text: {text[:2000]}

Return ONLY the JSON array. [/INST]"""
        
        response = self.generate(prompt, max_tokens=1024, temperature=0.3)
        
        try:
            if "[" in response:
                start = response.index("[")
                end = response.rindex("]") + 1
                return json.loads(response[start:end])
        except:
            pass
        return []


# Global instance
llm = LLMBackend()


# FastAPI service (standalone mode)
if __name__ == "__main__":
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    import uvicorn
    
    app = FastAPI(title="L Investigation LLM Backend")
    
    class GenerateRequest(BaseModel):
        prompt: str
        max_tokens: int = 512
        temperature: float = 0.7
    
    class ChatRequest(BaseModel):
        messages: list
        max_tokens: int = 512
        temperature: float = 0.7
    
    class ExtractRequest(BaseModel):
        text: str
    
    @app.on_event("startup")
    async def startup():
        llm.load()
    
    @app.get("/health")
    async def health():
        return {"status": "ok", "model_loaded": llm.is_loaded}
    
    @app.post("/generate")
    async def generate(req: GenerateRequest):
        if not llm.is_loaded:
            raise HTTPException(503, "Model not loaded")
        result = llm.generate(req.prompt, req.max_tokens, req.temperature)
        return {"text": result}
    
    @app.post("/chat")
    async def chat(req: ChatRequest):
        if not llm.is_loaded:
            raise HTTPException(503, "Model not loaded")
        result = llm.chat(req.messages, req.max_tokens, req.temperature)
        return {"text": result}
    
    @app.post("/extract/entities")
    async def extract_entities(req: ExtractRequest):
        if not llm.is_loaded:
            raise HTTPException(503, "Model not loaded")
        return {"entities": llm.extract_entities(req.text)}
    
    @app.post("/extract/relationships")
    async def extract_relationships(req: ExtractRequest):
        if not llm.is_loaded:
            raise HTTPException(503, "Model not loaded")
        entities = llm.extract_entities(req.text)
        rels = llm.extract_relationships(req.text, entities)
        return {"entities": entities, "relationships": rels}
    
    uvicorn.run(app, host="127.0.0.1", port=8001)
