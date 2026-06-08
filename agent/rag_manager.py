import os
import shutil
import logging
from typing import List
from langchain_community.document_loaders import PyPDFLoader, TextLoader, UnstructuredMarkdownLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

from config import LM_STUDIO_API_URL, EMBEDDING_MODEL_KEY

logger = logging.getLogger(__name__)

class RAGManager:
    def __init__(self, persist_directory: str = "chroma_db", model_name: str = EMBEDDING_MODEL_KEY):
        self.persist_directory = persist_directory
        self.model_name = model_name
        self.embeddings = OpenAIEmbeddings(
            base_url=LM_STUDIO_API_URL,
            api_key="lm-studio",
            model=self.model_name
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            length_function=len,
        )
        self.vectorstore = None
        self._init_vectorstore()

    def _init_vectorstore(self):
        """Initialize or load the vectorstore."""
        try:
            self.vectorstore = Chroma(
                persist_directory=self.persist_directory,
                embedding_function=self.embeddings,
                collection_name="planner_knowledge"
            )
            # Simple health check
            _ = self.vectorstore.get(limit=1)
            logger.info("Vectorstore initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize vectorstore: {e}")
            # If init fails, we might have a corrupted DB. 
            # We don't wipe it automatically here to avoid data loss, 
            # but we set vectorstore to None so process_file can try to recover.
            self.vectorstore = None

    def process_file(self, file_path: str):
        """Load, split, and add a file to the vectorstore."""
        logger.info(f"Processing file: {file_path}")
        
        # Ensure vectorstore is initialized
        if self.vectorstore is None:
            self._init_vectorstore()
            if self.vectorstore is None:
                logger.error("Vectorstore is not available. Cannot process file.")
                return False

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
                try:
                    self.vectorstore.add_documents(chunks)
                except Exception as e:
                    # If we get a "Collection does not exist" or similar error, try to re-init
                    if "collection" in str(e).lower() or "not exist" in str(e).lower():
                        logger.warning(f"Detected potential collection error: {e}. Attempting to re-initialize...")
                        self._init_vectorstore()
                        if self.vectorstore:
                            self.vectorstore.add_documents(chunks)
                        else:
                            raise e
                    else:
                        raise e
                        
                logger.info(f"Added {len(chunks)} chunks from {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return False

    def query_documents(self, query: str, k: int = 4) -> str:
        """Retrieve relevant document chunks and format as a context string."""
        if not self.vectorstore:
            self._init_vectorstore()
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
            # If query fails, it might be a broken collection too
            if "collection" in str(e).lower():
                self._init_vectorstore()
            return ""

    def clear_knowledge_base(self):
        """Delete all documents and clear the persistent storage."""
        logger.info("Clearing knowledge base...")
        
        # 1. Try to delete collection through API if alive
        if self.vectorstore:
            try:
                self.vectorstore.delete_collection()
                logger.debug("Collection deleted via API.")
            except Exception as e:
                logger.warning(f"Note: Collection could not be deleted via API (may not exist): {e}")

        # 2. Reset state immediately
        self.vectorstore = None
        
        # 3. Wipe the directory entirely
        if os.path.exists(self.persist_directory):
            import time
            deleted = False
            for i in range(3):
                try:
                    shutil.rmtree(self.persist_directory)
                    deleted = True
                    logger.debug(f"Directory {self.persist_directory} removed.")
                    break
                except Exception as e:
                    logger.warning(f"shutil.rmtree attempt {i+1} failed: {e}")
                    time.sleep(1)
            if not deleted:
                logger.error(f"Failed to wipe {self.persist_directory} after 3 attempts.")
        
        # 4. Re-init a fresh store
        try:
            os.makedirs(self.persist_directory, exist_ok=True)
            self._init_vectorstore()
            logger.info("Knowledge base cleared and re-initialized.")
            return True
        except Exception as e:
            logger.error(f"Error during re-initialization: {e}")
            return False

# Singleton instance
rag_manager = RAGManager()
