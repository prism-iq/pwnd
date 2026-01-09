# Models Directory

This directory contains the LLM models used by the investigation framework.

## Required Model

**Mistral 7B Instruct v0.2** (GGUF format, Q4_K_M quantization)

### Download

```bash
# Download from HuggingFace
wget https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf

# Move to models directory
mv mistral-7b-instruct-v0.2.Q4_K_M.gguf models/
```

### Alternative Models

You can use other GGUF models compatible with llama.cpp. Update `backend.py` to point to your model file.

### Model Info

- **Size**: ~4.4GB
- **Quantization**: Q4_K_M (good balance of speed/quality)
- **RAM Required**: ~8GB
- **Purpose**: Intent parsing and query understanding

## Note

Models are not included in the Git repository due to size. Download them separately as shown above.
