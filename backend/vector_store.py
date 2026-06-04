import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import os
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Tuple
from backend.config import VECTOR_DB_ABS_PATH

class FAISSVectorStore:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # dimension of all-MiniLM-L6-v2 is 384
        self.dimension = 384 
        
        print("Loading local embedding model: all-MiniLM-L6-v2...")
        # Load local SentenceTransformer model
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        print("Local embedding model loaded successfully!")
        
        # In-memory indices
        self.index = None
        self.metadata: List[Dict[str, str]] = [] # list of {"url": url, "title": title, "text": text}
        
    def _chunk_text(self, text: str, url: str, title: str) -> List[Dict[str, str]]:
        """Splits clean text into overlapping chunks of defined size."""
        chunks = []
        if not text:
            return chunks
            
        words = text.split()
        current_chunk = []
        current_length = 0
        
        for word in words:
            current_chunk.append(word)
            current_length += len(word) + 1 # Include space
            
            if current_length >= self.chunk_size:
                # Add current chunk to list
                chunk_text = ' '.join(current_chunk)
                chunks.append({
                    "url": url,
                    "title": title,
                    "text": chunk_text
                })
                
                # Keep overlap (keep the last few words corresponding to overlap size)
                # An overlap of 100 characters is roughly 15-20 words
                overlap_words = current_chunk[-15:] if len(current_chunk) > 15 else current_chunk
                current_chunk = list(overlap_words)
                current_length = sum(len(w) + 1 for w in current_chunk)
                
        # Append remaining text if any
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            if len(chunk_text.strip()) > 20: # skip tiny fragments
                chunks.append({
                    "url": url,
                    "title": title,
                    "text": chunk_text
                })
                
        return chunks

    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        """Retrieves text embeddings using the local SentenceTransformer model."""
        embeddings_list = self.model.encode(texts, show_progress_bar=False)
        
        # Convert to float32 NumPy array
        embeddings = np.array(embeddings_list, dtype=np.float32)
        
        # Normalize vectors to unit length (L2 norm) for cosine similarity
        faiss.normalize_L2(embeddings)
        return embeddings

    def ingest_pages(self, pages: List[Dict[str, str]]) -> int:
        """Chunks scraped pages, generates embeddings, builds and saves FAISS index."""
        all_chunks = []
        for page in pages:
            chunks = self._chunk_text(page["content"], page["url"], page["title"])
            all_chunks.extend(chunks)
            
        if not all_chunks:
            print("No text chunks extracted for ingestion.")
            return 0
            
        print(f"Generated {len(all_chunks)} chunks from {len(pages)} scraped pages. Embedding locally...")
        
        # Extract plain texts for embedding call
        chunk_texts = [c["text"] for c in all_chunks]
        embeddings = self._get_embeddings(chunk_texts)
        
        # Build FAISS inner-product index (IndexFlatIP matches cosine similarity when normalized)
        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(embeddings)
        self.metadata = all_chunks
        
        # Persist index and metadata to local folder path
        self.save_index()
        return len(all_chunks)

    def save_index(self):
        """Saves current FAISS index and metadata JSON to disk."""
        os.makedirs(VECTOR_DB_ABS_PATH, exist_ok=True)
        
        # Save FAISS binary index
        index_file = os.path.join(VECTOR_DB_ABS_PATH, "faiss.index")
        faiss.write_index(self.index, index_file)
        
        # Save Metadata as JSON
        metadata_file = os.path.join(VECTOR_DB_ABS_PATH, "metadata.json")
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
            
        print(f"Successfully saved FAISS index & metadata to folder: {VECTOR_DB_ABS_PATH}")

    def load_index(self) -> bool:
        """Loads FAISS index and metadata JSON from disk. Returns True if successful."""
        index_file = os.path.join(VECTOR_DB_ABS_PATH, "faiss.index")
        metadata_file = os.path.join(VECTOR_DB_ABS_PATH, "metadata.json")
        
        if not os.path.exists(index_file) or not os.path.exists(metadata_file):
            print(f"FAISS index files not found in: {VECTOR_DB_ABS_PATH}")
            return False
            
        try:
            # Load binary index
            self.index = faiss.read_index(index_file)
            
            # Load JSON metadata
            with open(metadata_file, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
                
            print(f"Successfully loaded FAISS index with {len(self.metadata)} chunks from: {VECTOR_DB_ABS_PATH}")
            return True
        except Exception as e:
            print(f"Error loading FAISS index: {str(e)}")
            return False

    def search(self, query: str, top_k: int = 4) -> List[Dict[str, str]]:
        """Queries FAISS index and returns top-k matching chunks with metadata."""
        if not self.index or not self.metadata:
            # Try to load from disk
            loaded = self.load_index()
            if not loaded:
                return []
                
        if not query:
            return []
            
        # Get query embedding using local model
        try:
            response = self.model.encode([query], show_progress_bar=False)
            query_vector = np.array(response, dtype=np.float32)
            
            # L2 Normalize the query vector for Cosine Similarity
            faiss.normalize_L2(query_vector)
            
            # Search FAISS index
            # IndexFlatIP.search returns (distances, indices)
            distances, indices = self.index.search(query_vector, top_k)
            
            results = []
            # Extract corresponding metadata chunks
            for idx, distance in zip(indices[0], distances[0]):
                if idx != -1 and idx < len(self.metadata):
                    chunk_data = dict(self.metadata[idx])
                    # Add similarity score for analytics/transparency
                    chunk_data["score"] = float(distance)
                    results.append(chunk_data)
                    
            return results
        except Exception as e:
            print(f"Vector search failed: {str(e)}")
            return []

# Quick testing if run directly
if __name__ == "__main__":
    store = FAISSVectorStore()
    # Ingest mock pages
    mock_pages = [
        {
            "url": "https://react.dev/reference/react",
            "title": "React Reference Hooks",
            "content": "React Hooks let you use different React features from your components. You can either use the built-in Hooks or combine them to build your own hooks. Built-in hooks include useState for state management, useEffect for side-effects, and useContext for global state."
        }
    ]
    store.ingest_pages(mock_pages)
    # Search query
    res = store.search("How do React Hooks handle state?")
    print("\nSearch Results:")
    for r in res:
        print(f"- Chunk: {r['text']}")
        print(f"  URL: {r['url']}, Score: {r['score']}")
