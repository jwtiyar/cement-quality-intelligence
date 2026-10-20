import os
import pickle
import hashlib
import logging
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer

INDEX_PATH = "knowledge_base/rag_index.pkl"
KNOWLEDGE_DIR = "knowledge_base"


class _UnsupportedEncodingFilter(logging.Filter):
    """Collect recoverable pypdf font-encoding messages per source file."""

    def __init__(self):
        super().__init__()
        self.messages: set[str] = set()

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if record.name == "pypdf._cmap" and message.startswith("Advanced encoding "):
            self.messages.add(message)
            return False
        return True


_UNSUPPORTED_ENCODING_FILTER = _UnsupportedEncodingFilter()
logging.getLogger("pypdf._cmap").addFilter(_UNSUPPORTED_ENCODING_FILTER)


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

def rebuild_index(*, output_path=None, summary_path=None):
    print("Building local TF-IDF RAG index...")
    encoding_filter = _UNSUPPORTED_ENCODING_FILTER
    
    # Scan for PDF and TXT files
    knowledge_files = []
    for f in os.listdir(KNOWLEDGE_DIR):
        ext = os.path.splitext(f)[1].lower()
        if ext in ['.pdf', '.txt'] and f != "rag_index.pkl":
            knowledge_files.append((f, ext))
    if summary_path and not any(f == "latest_daily_results.txt" for f, _ in knowledge_files):
        knowledge_files.append(("latest_daily_results.txt", ".txt"))
            
    all_chunks = []
    files_meta = {}
    
    for f, ext in knowledge_files:
        filepath = os.path.join(KNOWLEDGE_DIR, f)
        if summary_path and f == "latest_daily_results.txt":
            filepath = summary_path
        file_hash = get_file_hash(filepath)
        print(f"Parsing {f}...")
        encoding_filter.messages.clear()
        try:
            file_chunks = []
            if ext == '.pdf':
                reader = PdfReader(filepath)
                for page_idx, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text and len(text.strip()) > 50:
                        file_chunks.extend(chunk_text(text, f, page_idx + 1))
            elif ext == '.txt':
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as txt_file:
                    text = txt_file.read()
                    if text and len(text.strip()) > 20:
                        file_chunks.extend(chunk_text(text, f, 1))
            
            if file_chunks:
                all_chunks.extend(file_chunks)
                files_meta[f] = {
                    "hash": file_hash,
                    "chunks_count": len(file_chunks)
                }
                print(f"  Successfully parsed {f} ({len(file_chunks)} chunks)")
            else:
                print(f"  No text found in {f}.")
            if encoding_filter.messages:
                print(
                    f"  Warning: pypdf skipped unsupported font encodings in {f}; "
                    "some extracted text may be incomplete."
                )
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
    
    output_path = output_path or INDEX_PATH
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp_path = output_path + ".tmp"
    with open(tmp_path, 'wb') as f:
        pickle.dump(index, f)
    os.replace(tmp_path, output_path)
        
    print(f"Index successfully built and saved! Total chunks: {len(all_chunks)}")

if __name__ == "__main__":
    rebuild_index()
