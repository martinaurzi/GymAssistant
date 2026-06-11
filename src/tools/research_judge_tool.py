import os
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage
#from langchain_groq import ChatGroq
from schemas import JudgeEvaluation
from prompts import JUDGE_PROMPT

load_dotenv(".env")

from langchain_google_genai import ChatGoogleGenerativeAI

@tool
def research_judge_tool(search_results_str: str, topic: str) -> str:
    """Valuta le fonti web separate da '|' calcolando un punteggio finale ponderato 
    e selezionando solo quelle che superano i requisiti minimi di qualità (punteggi >= 7).
    
    Argomenti:
        search_results_str: La stringa contenente i risultati formattati separati da '|'
        topic: Il topic dell'articolo corrente
    """
    
    # Splittiamo la stringa generata dal tuo web_search_tool per renderla leggibile al modello
    sources = search_results_str.split("|")
    formatted_sources_text = []
    
    for idx, source in enumerate(sources, 1):
        if not source.strip(): # se la fonte è stringa vuota
            continue
        
        formatted_sources_text.append(f"RISULTATO DA VALUTARE {idx} \n{source.strip()}\n")
            
    text_to_analyze = "\n".join(formatted_sources_text) 

    # Configurazione di Groq (usiamo llama-3.3-70b)
    #judge_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0,groq_api_key=os.getenv("GROQ_API_KEY"))
    judge_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    
    # Forziamo l'output strutturato Pydantic
    structured_judge = judge_llm.with_structured_output(JudgeEvaluation)
    
    human_message_content = f"Topic del post: {topic}\n\nEcco l'elenco delle fonti raccolte:\n{text_to_analyze}"
    
    try:
        # Invocazione del modello su Groq
        evaluation: JudgeEvaluation = structured_judge.invoke([
            SystemMessage(content=JUDGE_PROMPT),
            HumanMessage(content=human_message_content)
        ])
        
        # Ordiniamo le fonti approvate (is_selected=True) per 'interestingness_score' in modo decrescente
        fonti_valutate = evaluation.evaluated_sources
        fonti_selezionate = [f for f in fonti_valutate if f.is_selected]
        fonti_scartate = [f for f in fonti_valutate if not f.is_selected]
        
        # Ordiniamo le selezionate in base a interestingness 
        fonti_selezionate.sort(key=lambda x: x.interestingness_score, reverse=True)
        
        # Costruiamo il report testuale finale che verrà restituito all'agente principale
        output_lines = [
            f"**RESOCONTO**\n",
            f" Sintesi: {evaluation.verdict_summary}\n",
            "**FONTI SELEZIONATE (Ordinate per Interesse):**"
        ]
        
        if not fonti_selezionate:
            output_lines.append("  *Nessuna fonte ha superato i criteri minimi di qualità (Relevance, Accuracy, Quality >= 7).*")
        else:
            for src in fonti_selezionate:
                output_lines.append(
                    f"\n  **{src.title}**"
                    f"\n   - URL: {src.url}"
                    f"\n   - Punteggi: [Relevance: {src.relevance_score} | Accuracy: {src.accuracy_score} | Quality: {src.quality_score} | Interest: {src.interestingness_score}]"
                    f"\n   - **SCORE PONDERATO:** {round(src.final_score, 2)}" #round serve per arrontondare a 2 cifre decimali dopo la virgola
                    f"\n   - Motivazione: {src.justification}"
                )
                
        if fonti_scartate:
            output_lines.append("\n**FONTI SCARTATE:**")
            for src in fonti_scartate:
                output_lines.append(
                    f"  - {src.title} (Final Score: {round(src.final_score, 2)})"
                    f"\n Motivazioni: {src.justification}"
                    f"\n    *Motivo dello scarto*: Uno o più punteggi fondamentali sono inferiori a 7."
                )
                
        final_report = "\n".join(output_lines)
        print(f"\n[DEBUG JUDGE TOOL - SUCCESSO]:\n{final_report}\n")
        
        return final_report
        
    except Exception as e:
        # Fallback nel caso in cui Groq o il parsing falliscano
       print(f"\n[DEBUG JUDGE TOOL - CRASH CRITICO]: Dettaglio errore: {str(e)}\n")
       return f"[ERRORE CRITICO GIUDICE FONTI]: Impossibile completare l'analisi. Dettaglio: {str(e)}"