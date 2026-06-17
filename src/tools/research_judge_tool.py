from typing import Annotated
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage
from schemas import JudgeEvaluation
from prompts import JUDGE_PROMPT

load_dotenv(".env")

from langchain_google_genai import ChatGoogleGenerativeAI

@tool
def research_judge_tool(
    search_results_str: str,
    topic: str,
    justification: Annotated[str, "Spiegazione obbligatoria del perché stai usando questo tool proprio adesso."]
) -> str:
    """Valuta le fonti web calcolando un punteggio finale ponderato e selezionando solo quelle che superano i requisiti minimi di 
       qualità (punteggi >= 7).
    
        Argomenti:
            - search_results_str: La stringa contenente i risultati formattati separati da '|'
            - topic: Il topic dell'articolo corrente
            - justification: La giustificazione obbligatoria per l'utilizzo del tool.
    """
    
    # Formattiamo le fonti per passarle al modello
    sources = search_results_str.split("|")
    formatted_sources_text = []
    
    for idx, source in enumerate(sources, 1):
        if not source.strip(): 
            continue
        
        formatted_sources_text.append(f"RISULTATO DA VALUTARE {idx} \n{source.strip()}\n")
            
    text_to_analyze = "\n".join(formatted_sources_text) 

    # Instanziamo il modello
    judge_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    
    structured_judge = judge_llm.with_structured_output(JudgeEvaluation)
    
    human_message_content = f"Topic del post: {topic}\n\nEcco l'elenco delle fonti raccolte:\n{text_to_analyze}"
    
    try:
        evaluation: JudgeEvaluation = structured_judge.invoke([
            SystemMessage(content=JUDGE_PROMPT),
            HumanMessage(content=human_message_content)
        ])
        
        fonti_valutate = evaluation.evaluated_sources
        fonti_selezionate = [f for f in fonti_valutate if f.is_selected]
        fonti_scartate = [f for f in fonti_valutate if not f.is_selected]
        
        # Ordiniamo le fonti in ordine di indice di interesse
        fonti_selezionate.sort(key=lambda x: x.interestingness_score, reverse=True)
        
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
                    f"\n   - **SCORE PONDERATO:** {round(src.final_score, 2)}" 
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
        
        return final_report
        
    except Exception as e:
       return f"[JUDGE TOOL]: Impossibile completare l'analisi. Dettaglio: {str(e)}"