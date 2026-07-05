import os
import pickle
import hashlib
import numpy as np
from pypdf import PdfReader
import google.generativeai as genai

def load_env():
    env_paths = [".env", "../.env"]
    for path in env_paths:
        if os.path.exists(path):
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line and not line.startswith("#"):
                        key, val = line.split("=", 1)
                        val = val.strip().strip("'").strip('"')
                        os.environ[key.strip()] = val

load_env()

# Setup Gemini API key
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

INDEX_PATH = "knowledge_base/rag_index.pkl"
KNOWLEDGE_DIR = "knowledge_base"

def get_file_hash(filepath):
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

def chunk_text(text, source_name, page_num, chunk_size=800, overlap=150):
    chunks = []
    text_len = len(text)
    start = 0
    while start < text_len:
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append({
            "text": chunk,
            "source": source_name,
            "page": page_num
        })
        start += (chunk_size - overlap)
    return chunks

def load_or_create_index():
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Error loading index, starting fresh: {e}")
    return {
        "files": {}, # filename -> hash
        "chunks": [],
        "embeddings": None # np.array of shape (N, 768)
    }

def save_index(index):
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, 'wb') as f:
        pickle.dump(index, f)

def generate_embeddings_batch(texts, batch_size=100):
    if not api_key:
        raise ValueError("GEMINI_API_KEY / GOOGLE_API_KEY environment variable is not set!")
    
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        print(f"  Embedding batch {i//batch_size + 1}/{-(-len(texts)//batch_size)}...")
        try:
            result = genai.embed_content(
                model="models/embedding-001",
                content=batch,
                task_type="retrieval_document"
            )
            embeddings.extend(result['embedding'])
        except Exception as e:
            print(f"  Error generating embeddings for batch: {e}")
            # Fallback to zeros to keep dimensions matching
            embeddings.extend([[0.0] * 768 for _ in batch])
    return np.array(embeddings, dtype=np.float32)

def rebuild_index():
    if not api_key:
        print("ERROR: GEMINI_API_KEY / GOOGLE_API_KEY environment variable is not set. Cannot index files.")
        return
        
    index = load_or_create_index()
    
    # Scan for PDF files
    pdf_files = []
    for f in os.listdir(KNOWLEDGE_DIR):
        if f.lower().endswith('.pdf') and f != "rag_index.pkl":
            pdf_files.append(f)
            
    updated = False
    
    for f in pdf_files:
        filepath = os.path.join(KNOWLEDGE_DIR, f)
        file_hash = get_file_hash(filepath)
        
        # Check if file has changed or is new
        if f in index["files"] and index["files"][f] == file_hash:
            print(f"Skipping {f} (already indexed and unchanged)")
            continue
            
        print(f"Indexing {f}...")
        try:
            reader = PdfReader(filepath)
            file_chunks = []
            for page_idx, page in enumerate(reader.pages):
                text = page.extract_text()
                if text and len(text.strip()) > 50:
                    file_chunks.extend(chunk_text(text, f, page_idx + 1))
            
            if not file_chunks:
                print(f"  No text found in {f}.")
                index["files"][f] = file_hash
                updated = True
                continue
                
            # Extract texts for embedding
            texts = [c["text"] for c in file_chunks]
            new_embeddings = generate_embeddings_batch(texts)
            
            # Remove old chunks for this file if it was previously indexed (e.g. modified file)
            if f in index["files"]:
                # Filter out old chunks
                keep_indices = [i for i, c in enumerate(index["chunks"]) if c["source"] != f]
                index["chunks"] = [index["chunks"][i] for i in keep_indices]
                if index["embeddings"] is not None:
                    index["embeddings"] = index["embeddings"][keep_indices]
            
            # Append new chunks and embeddings
            index["chunks"].extend(file_chunks)
            if index["embeddings"] is None:
                index["embeddings"] = new_embeddings
            else:
                index["embeddings"] = np.vstack([index["embeddings"], new_embeddings])
                
            index["files"][f] = file_hash
            updated = True
            print(f"  Successfully indexed {f} ({len(file_chunks)} chunks)")
            
            # Save incrementally after each successful file to prevent data loss
            save_index(index)
            
        except Exception as e:
            print(f"Error indexing {f}: {e}")
            
    if updated:
        print("Index update complete!")
    else:
        print("Index is already up to date.")

if __name__ == "__main__":
    rebuild_index()
