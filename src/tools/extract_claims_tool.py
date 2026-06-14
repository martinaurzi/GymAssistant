from langchain_core.tools import tool
import torch
from typing import Annotated

from model.model_loader import get_model_and_tokenizer

model, tokenizer = get_model_and_tokenizer()

@tool
def extract_claims_tool(post_text: str, 
                        justification: Annotated[str, "Spiegazione obbligatoria del perché stai usando questo tool proprio adesso."]) -> str:
    """
    Estrae le 3 affermazioni più importanti e verificabili da un post sportivo.
    Risponde esclusivamente in formato JSON stringa: {'claims': ['claim1', 'claim2', 'claim3']}.
    
    Argomenti:
        post_text: Il post da cui estrarre i claim.
        justification: La giustificazione obbligatoria per l'utilizzo del tool.
    """
    
    prompt_str = tokenizer.apply_chat_template([
        {"role": "system", "content": "Sei un sistema di estrazione dati che lavora ESCLUSIVAMENTE sul testo fornito dall'utente. Il tuo compito è analizzare il testo e estrarre le informazioni presenti. Rispondi ESCLUSIVAMENTE in lingua italiana. Se un'informazione non è nel testo, non includerla. Rispondi SOLO in formato JSON: {'claims': ['claim1', 'claim2', 'claim3']} senza aggiungere altre informazioni."},
        {"role": "user", "content": f"Estrai le 3 affermazioni più importanti e verificabili dal post:\n\n{post_text}"}
    ], tokenize=False, add_generation_prompt=True)
    
    inputs = tokenizer(prompt_str, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,     
            do_sample=False,        
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id
        )
    
    input_length = inputs.input_ids.shape[1]
    generated_tokens = outputs[0][input_length:]
    pred_text = tokenizer.decode(generated_tokens, skip_special_tokens=True)
    
    return pred_text