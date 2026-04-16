import os
import shutil
import logging
from typing import List
from langchain_community.document_loaders import PyPDFLoader, TextLoader, UnstructuredMarkdownLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

class RAGManager:
    def __init__(self, persist_directory: str = "chroma_db", model_name: str = "granite-embedding:latest"):
        self.persist_directory = persist_directory
        self.model_name = model_name
        self.embeddings = OllamaEmbeddings(model=self.model_name)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            length_function=len,
        )
        self.vectorstore = None
        self._init_vectorstore()

    def _init_vectorstore(self):
        """Initialize or load the vectorstore."""
        self.vectorstore = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
            collection_name="planner_knowledge"
        )

    def process_file(self, file_path: str):
        """Load, split, and add a file to the vectorstore."""
        logger.info(f"Processing file: {file_path}")
        ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if ext == ".pdf":
                loader = PyPDFLoader(file_path)
            elif ext == ".md":
                loader = UnstructuredMarkdownLoader(file_path)
            else:
                loader = TextLoader(file_path, encoding="utf-8")
            
            documents = loader.load()
            chunks = self.text_splitter.split_documents(documents)
            
            if chunks:
                self.vectorstore.add_documents(chunks)
                logger.info(f"Added {len(chunks)} chunks from {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return False

    def query_documents(self, query: str, k: int = 4) -> str:
        """Retrieve relevant document chunks and format as a context string."""
        if not self.vectorstore:
            return ""
        
        try:
            results = self.vectorstore.similarity_search(query, k=k)
            if not results:
                return ""
            
            context = "\n\n".join([doc.page_content for doc in results])
            return context
        except Exception as e:
            logger.error(f"Error querying vectorstore: {e}")
            return ""

    def clear_knowledge_base(self):
        """Delete all documents and clear the persistent storage."""
        logger.info("Clearing knowledge base...")
        try:
            # Re-initialize to ensure no locks, though Chroma handles this usually
            if os.path.exists(self.persist_directory):
                # Try to delete the collection first
                self.vectorstore.delete_collection()
                # Then wipe the directory to be safe
                shutil.rmtree(self.persist_directory)
            
            # Re-init a fresh store
            os.makedirs(self.persist_directory, exist_ok=True)
            self._init_vectorstore()
            logger.info("Knowledge base cleared.")
            return True
        except Exception as e:
            logger.error(f"Error clearing knowledge base: {e}")
            return False

# Singleton instance
rag_manager = RAGManager()
