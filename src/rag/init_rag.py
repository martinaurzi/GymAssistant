from rag_manager import RagManager

rag_manager = RagManager()

rag_urls = [
    "https://www.projectinvictus.it/scheda-allenamento-full-body/",
    "https://www.projectinvictus.it/ipertrofia-muscolare-la-guida-completa/",
    "https://www.projectinvictus.it/esercizi-dorsali/",
    "https://www.projectinvictus.it/esercizi-per-le-braccia/",
    "https://www.projectinvictus.it/squat-esecuzione-approfondita/",
    "https://www.projectinvictus.it/esercizi-spalle-manubri/",
    "https://www.projectinvictus.it/forza-bodybuilding/",
    "https://www.my-personaltrainer.it/nutrizione/fabbisogno-proteico.html"
]

print("Inizializzazione del RAG\n")

if(rag_manager.populate_rag(rag_urls)):
    print(f"Documenti caricati in Chroma DB\n")