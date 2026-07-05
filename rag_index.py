import os
import pickle
import hashlib
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer

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

def rebuild_index():
    print("Building local TF-IDF RAG index...")
    
    # Scan for PDF files
    pdf_files = []
    for f in os.listdir(KNOWLEDGE_DIR):
        if f.lower().endswith('.pdf') and f != "rag_index.pkl":
            pdf_files.append(f)
            
    all_chunks = []
    files_meta = {}
    
    for f in pdf_files:
        filepath = os.path.join(KNOWLEDGE_DIR, f)
        file_hash = get_file_hash(filepath)
        print(f"Parsing {f}...")
        try:
            reader = PdfReader(filepath)
            file_chunks = []
            for page_idx, page in enumerate(reader.pages):
                text = page.extract_text()
                if text and len(text.strip()) > 50:
                    file_chunks.extend(chunk_text(text, f, page_idx + 1))
            
            if file_chunks:
                all_chunks.extend(file_chunks)
                files_meta[f] = {
                    "hash": file_hash,
                    "chunks_count": len(file_chunks)
                }
                print(f"  Successfully parsed {f} ({len(file_chunks)} chunks)")
            else:
                print(f"  No text found in {f} (could be a scanned PDF image).")
        except Exception as e:
            print(f"Error parsing {f}: {e}")
            
    if not all_chunks:
        print("No text chunks found in any PDFs. Index not built.")
        return
        
    print("Fitting TF-IDF vectorizer...")
    vectorizer = TfidfVectorizer(stop_words='english')
    texts = [c["text"] for c in all_chunks]
    tfidf_matrix = vectorizer.fit_transform(texts)
    
    index = {
        "files": files_meta,
        "chunks": all_chunks,
        "vectorizer": vectorizer,
        "tfidf_matrix": tfidf_matrix
    }
    
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, 'wb') as f:
        pickle.dump(index, f)
        
    print(f"Index successfully built and saved! Total chunks: {len(all_chunks)}")

if __name__ == "__main__":
    rebuild_index()
