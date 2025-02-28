import json
import logging
import numpy as np
from fastapi import FastAPI, Request, Response

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="Cohere Embeddings Mock Server")

EMBEDDING_DIMENSIONS = 1024

# good old AI
def generate_embedding_vector(text, dimensions=EMBEDDING_DIMENSIONS):
    """Generate a deterministic embedding vector for given text"""
    # Create a deterministic seed based on the text content
    seed = sum(ord(c) * (i + 1) for i, c in enumerate(text))
    
    # Generate vector using sine waves with the seed affecting the pattern
    vector = [np.sin((i + seed) / (dimensions / 10)) * 0.5 for i in range(dimensions)]
    
    # Normalize the vector to unit length (common in embeddings)
    magnitude = np.sqrt(sum(v * v for v in vector))
    if magnitude > 0:
        vector = [v / magnitude for v in vector]
    
    return vector

@app.post("/embeddings")
async def mock_bedrock_cohere(request: Request):
    try:
        body = await request.json()
        
        log.info(f"grabbing input from body")

        texts = body.get("input", [])

        if not texts:
            log.info(f"input not found {body}")
            return Response(
                content=json.dumps({"error": "No text provided for embedding"}),
                status_code=400
            )
        
        log.info("generating vectors")
        embeddings = [generate_embedding_vector(text) for text in texts]
        
        total_chars = sum(len(text) for text in texts)
        estimated_tokens = total_chars // 4 + 1
        
        log.info("constructing response")
        response = {
            "embeddings": embeddings,
            "id": f"mock-embedding-{hash(str(texts))}",
            "texts": texts,
            "model": "cohere.embed-v3",
            "usage": {
                "prompt_tokens": estimated_tokens,
                "total_tokens": estimated_tokens
            }
        }

        response_obj = {}
        response_obj["model"] = response["model"] 
        response_obj["usage"] = {}
        response_obj["usage"]["prompt_tokens"] = response["usage"]["prompt_tokens"]
        response_obj["usage"]["total_tokens"] = response["usage"]["total_tokens"]
        response_obj["data"] = []
        for e in embeddings:
            response_obj["data"].append(
                {
                    "object": "embedding",
                    "index": 0,
                    "embedding": e,
                }
            )

        return Response(
            content=json.dumps(response_obj),
            status_code=200,
            headers={"Content-Type": "application/json"},
        )
        
    except Exception as e:
        return Response(
            content=json.dumps({"error": f"Failed to process request: {str(e)}"}),
            status_code=500
        )
