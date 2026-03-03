import PyPDF2
import docx
import re
from typing import List

class DocumentProcessor:
    """Extract and preprocess text from uploaded documents for PDPA Analysis"""
    
    def __init__(self):
        self.supported_formats = ['.pdf', '.docx', '.txt']
    
    def extract_text(self, file_path: str) -> str:
        """Extract text based on file type"""
        if file_path.endswith('.pdf'):
            return self._extract_from_pdf(file_path)
        elif file_path.endswith('.docx'):
            return self._extract_from_docx(file_path)
        elif file_path.endswith('.txt'):
            return self._extract_from_txt(file_path)
        else:
            raise ValueError(f"Unsupported file format. Supported: {self.supported_formats}")
    
    # Extracting Methods
    def _extract_from_pdf(self, file_path: str) -> str:
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text

    def _extract_from_docx(self, file_path: str) -> str:
        doc = docx.Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])

    def _extract_from_txt(self, file_path: str) -> str:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            return file.read()

    # Preprocessing and Tokenisation Aspect
    def preprocess_text(self, text: str) -> str:
        """Enhanced cleaning for legal text"""
        # 1. Fix broken words caused by PDF line breaks (e.g., 'com- pliance')
        text = re.sub(r'(\w+)-\s*\n(\w+)', r'\1\2', text)
        
        # 2. Normalize whitespace while preserving single newlines (important for legal lists)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        
        # 3. Remove non-printable characters but keep standard legal symbols
        text = "".join(ch for ch in text if ch.isprintable() or ch in ['\n', '\t'])
        
        return text.strip()

    def chunk_text(self, text: str, chunk_size: int = 2500, chunk_overlap: int = 300) -> List[str]:
        """
        Recursive-style chunking with overlap for AI processing.
        """
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # If we're not at the end, try to find a natural break (period or newline)
            if end < len(text):
                # Look for the last period or newline in the current window to avoid mid-sentence cuts
                last_break = max(text.rfind('.', start, end), text.rfind('\n', start, end))
                if last_break != -1 and last_break > start + (chunk_size // 2):
                    end = last_break + 1
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move start forward by (chunk_size - overlap)
            start += (end - start) - chunk_overlap
            
            # Safety break to avoid infinite loops
            if end >= len(text):
                break
                
        return chunks