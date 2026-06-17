from dotenv import load_dotenv
import requests
import bs4

from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

load_dotenv(".env")

class RagManager:
    def __init__(self):
        self.database = "./chroma_db"

        # Splitter per dividere i documenti in chunk
        self.text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=500, chunk_overlap=50)
        
        # Inizializzazione del modello di embeddings
        self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

        # Inizializzazione di Chroma
        self.chroma = Chroma(embedding_function=self.embeddings, persist_directory=self.database)

    def load_url(self, url: str) -> Document:
        """Crea un documento estraendo il contenuto da un url"""
        
        response = requests.get(url)

        response.raise_for_status()
        
        soup = bs4.BeautifulSoup(response.text, "html.parser")

        # Puliamo il testo prendendo solo il contenuto dell'articolo
        main_content = soup.find("article") or soup.find("main") or soup.find("body") 

        html_elements_to_remove = ["script", "style", "form", "iframe", "noscript", "svg", "header", "footer", "nav", "aside"]
        
        for content in main_content(html_elements_to_remove):
            content.decompose()

        text = main_content.get_text(separator=" ", strip=True) # separator per evitare parole incollate

        return Document(
            page_content=text, 
            metadata={
                "source": url, 
                "title": soup.title.string if soup.title else "Articolo"
            })
    
    def populate_rag(self, urls: list[str]) -> bool:
        """Recupera i documenti a partire dagli urls usando la funzione load_url.

           Ogni documento viene diviso in chunks, trasformato in embeddings e poi inserito nel Vector Database Chroma
        """

        docs_to_split = []

        for url in urls:
            try:
                doc_is_present = self.chroma.get(where={"source": url})

                # Verifichiamo se il documento è già presente in Chroma DB
                if doc_is_present and doc_is_present["ids"]:
                    print(f"[RAG MANAGER]: {url} già presente in Chroma DB\n") 
                    continue

                doc = self.load_url(url)

                docs_to_split.append(doc)

            except requests.exceptions.RequestException as e:
                print(f"[RAG MANAGER]: Errore di rete per {url}: {e}") 
            except Exception as e:
                print(f"[RAG MANAGER]: Errore durante l'elaborazione di {url}: {e}")
        
        if not docs_to_split:
            print(f"[RAG MANAGER]: Nessun documento recuperato\n")
            return False
        
        # Splittiamo i documenti in chunks
        chunks = self.text_splitter.split_documents(docs_to_split)

        print(f"[RAG MANAGER]: I documenti sono stati divisi in {len(chunks)} chunks\n")

        # Aggiungiamo i chunk dei documenti in Chroma
        print(f"[RAG MANAGER]: Generazione degli embeddings...\n")

        docs_ids = self.chroma.add_documents(chunks)

        if docs_ids:
            print(f"[RAG MANAGER]: {len(docs_ids)} docs ids restituiti da .add_document(): {docs_ids}\n")
            return True
        else:
            return False

    def retrieve_documents(self, query: str, k: int = 3) -> list[str]:
        """Recupera i documenti più rilevanti alla query eseguendo una Semantic Search nel Vector Database"""
        
        retrieved_docs = self.chroma.similarity_search(query, k=k)

        if not retrieved_docs:
            print(f"[RAG MANAGER]: Nessun documento rilevante relativo alla query: {query}\n")
            return []
        
        formatted_docs = []

        for doc in retrieved_docs:
            title = doc.metadata.get("title", "Titolo non disponibile")
            source = doc.metadata.get("source", "Fonte non disponibile")
            content = doc.page_content

            formatted_info = f"Titolo: {title}, Fonte: {source}, Contenuto: {content}"

            formatted_docs.append(formatted_info)
            
        return formatted_docs