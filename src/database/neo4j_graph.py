import os
from neo4j import GraphDatabase
from langchain_huggingface import HuggingFaceEmbeddings

class EditorialKnowledgeGraphManager:
    
    def __init__(self):
        # Recupero credenziali e inizializzazione connessione verso il database
        uri = os.getenv("NEO4J_URI")
        username = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")
        
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        
        # Inizializzazione del modello di embeddings
        self.embeddings = HuggingFaceEmbeddings(
            model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        
        # Setup dell'indice vettoriale (Dimensione 384)
        # CREATE VECTOR INDEX è un comando nativo di Neo4j, con FOR indichiamo quali Label deve tenere in considerazione, mentre con ON indichiamo dove sarà contenuto l'embedding
        # Con indexConfig indichiamo i parametri matematici dello spazio geometrico in cui i vettori verranno inseriti
        # la dimensione del vettore dipende dal modello usato, usiamo cosine perché il modello misuta l'ampiezza dell'angolo formato dai due vettori rispetto l'origine dello spazio
        index_setup_query = """
        CREATE VECTOR INDEX topic_index IF NOT EXISTS
        FOR (t:Topic) ON (t.embedding)
        OPTIONS {indexConfig: {
          `vector.dimensions`: 384,
          `vector.similarity_function`: 'cosine'
        } }
        """
        with self.driver.session() as session:
            session.run(index_setup_query)
            print("[NEO4J]: Controllo/Creazione indice vettoriale completato.")
        
    # chiusura connessione
    def close(self):
        self.driver.close()
        
    def get_kg_summary(self) -> str:
        """
        Fase Topic Suggestion: Recupera lo stato attuale per il Planner.
        Ritorna gli ultimi post e tutti i topic coperti per evitare ripetizioni.
        """
        with self.driver.session() as session:
            # Estrazione topic già trattati finora
            topics_query = "MATCH (t:Topic) RETURN t.name AS topic" #rinominato per non scrivere record[t.name]
            topics_res = session.run(topics_query)
            #Neo4j restituisce una lista di oggetti Record, ma dobbiamo prendere solo la stringa relativa al name del topic
            topics = [record["topic"] for record in topics_res]
            
            posts_query = """
            MATCH (p:Post)-[:COVERS]->(t:Topic)
            RETURN p.title AS title, p.category AS category, p.createdAt AS createdAt, collect(t.name) AS topics
            ORDER BY createdAt DESC
            LIMIT 3
            """
            posts_res = session.run(posts_query)
            
            recent_posts = [
                {
                    "title": record["title"],
                    "category": record["category"],
                    "topics": record["topics"]
                }
                for record in posts_res
            ]
            
            # Se il database è completamente vuoto 
            if not topics and not recent_posts:
                return "Contenuto Storico: Il database è vuoto. Il blog è completamente nuovo: non è presente nessun topic o post precedente."
            
            # Formattazione dello storico in una stringa leggibile
            topics_str = ", ".join(topics)
            posts_formatted = [
                f"{{'title': '{p['title']}', 'category': '{p['category']}', 'topics': '{p['topics']}'}}" 
                for p in recent_posts
            ]
            posts_str = " | ".join(posts_formatted)
            
            return f"Contenuto Storico: {{'covered_topics': [{topics_str}], 'recent_posts': [{posts_str}]}}"
            
    def search_similar_content(self, topic: str) -> dict:
        """Ricerca semantica per coerenza editoriale."""
        query_vector = self.embeddings.embed_query(topic)
        query = """
        MATCH (t:Topic)
        WHERE t.embedding IS NOT NULL
        WITH t, vector.similarity.cosine(t.embedding, $vector) AS score
        WHERE score > 0.6
        ORDER BY score DESC
        LIMIT 1

        WITH t
        MATCH (p:Post)-[:COVERS]->(t)
        OPTIONAL MATCH (p)-[:EXTRACTED]->(c:Claim)

        RETURN t.name AS matched_topic,
            p.title AS title,
            collect(c.text) AS claims 
        LIMIT 2
        """
        with self.driver.session() as session:
            result = session.run(query, vector=query_vector)
            records = list(result)
            if not records:
                return {
                    "context": "Nessun contenuto correlato trovato nel Knowledge Graph (con score sufficiente).",
                    "matched_topic": ""
                }
            
            # Estraiamo il nome del topic trovato dal primo record
            matched_topic_name = records[0]["matched_topic"]
            
            summary = "Contenuti correlati: \n"
            for r in records:
                summary += f"- Nel post '{r['title']}' abbiamo affermato: {', '.join(r['claims'])}\n"
            
            return {
                "context": summary,
                "matched_topic": matched_topic_name
            }
            
        
    def add_approved_post(self, post_draft: dict, requested_topic: str, matched_topic: str, claims: list):
        """
        Crea il post e lo associa tramite :COVERS sia al topic richiesto sia al topic affine trovato.
        """
        # Generiamo l'embedding del topic principale dell'articolo
        topic_vector = self.embeddings.embed_query(requested_topic)
   
        query = """
        // Creazione del Post
        CREATE (p:Post {
            title: $title, 
            category: $category, 
            introduction: $introduction, 
            body: $body, 
            conclusion: $conclusion,
            createdAt: timestamp()
        })

        // Associazione o creazione del Topic Principale richiesto dall'LLM
        MERGE (t:Topic {name: $requested_topic})
        ON CREATE SET t.embedding = $topic_embedding
        ON MATCH SET t.embedding = $topic_embedding 
        CREATE (p)-[:COVERS]->(t)

        // Associazione condizionale al Topic Simile Preesistente
        CALL (p){ //per rendere disponibile p all'interno al posto di dover usare 2 volte WITH P
            WITH p
            WHERE $matched_topic IS NOT NULL 
            AND $matched_topic <> "" 
            AND $matched_topic <> $requested_topic
            
            MATCH (oldT:Topic {name: $matched_topic})
            MERGE (p)-[:COVERS]->(oldT)
        }

        // Srotolamento delle Fonti
        WITH p
        UNWIND $sources AS src_url
        MERGE (s:Source {url: src_url})
        CREATE (p)-[:USED_SOURCE]->(s)

        // Srotolamento dei Claims
        WITH p
        UNWIND $claims AS claim_text
        CREATE (c:Claim {text: claim_text})
        CREATE (p)-[:EXTRACTED]->(c)
        """
        
        with self.driver.session() as session:
            session.run(
                query,
                title=post_draft['title'],
                category=post_draft['category'],
                introduction=post_draft['introduction'],
                body=post_draft['body'],
                conclusion=post_draft['conclusion'],
                requested_topic=requested_topic,
                topic_embedding=topic_vector,
                matched_topic=matched_topic,
                sources=post_draft['sources'],
                claims=claims
            )
            print("[NEO4J]: Grafo aggiornato con successo!\n")