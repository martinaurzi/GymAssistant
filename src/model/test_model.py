from model_loader import get_model_and_tokenizer 
import torch

model, tokenizer = get_model_and_tokenizer()

post_text = "--- POST HOW_TO ---\n\nTitolo: Come Ottimizzare il Setup delle Spalle sulla Panca Piana per Proteggere la Cuffia dei Rotatori\n\nL'esecuzione della panca piana con carichi submassimali richiede un posizionamento articolare preciso per minimizzare le forze di taglio a carico dell'articolazione gleno-omerale. Impostare una corretta stabilità scapolare è il fattore chiave.\n\nPROTOCOLLO DI SET-UP\n    1 Adduzione Scapolare: Prima di staccare il bilanciere dai supporti, unisci attivamente le scapole spingendole l'una contro l'altra come se volessi stringere un oggetto tra di esse.\n    2 Depressione Scapolare: Spingi le scapole verso il basso, in direzione dei glutei. Questo movimento allontana le spalle dalle orecchie e riduce lo spazio sub-acromiale, proteggendo il tendine del sovraspinato dal conflitto cinetico.\n    3 Leg Drive e Arco Fisiologico: Mantieni i piedi saldi a terra spingendo il corpo verso la parte superiore della panca, accentuando l'arco lombare naturale senza staccare i glutei dal sellino.\n\nERRORI DA EVITARE\n    1 Anteporre le spalle durante la fase concentrica massima (chiusura), perdendo il contatto delle scapole con la panca e trasferendo il carico sul deltoide anteriore.\n\nCONCLUSIONE\nMantenere il blocco scapolare per tutta la durata della serie previene gli infortuni cronici alla cuffia dei rotatori e aumenta la base d'appoggio meccanica.\n\nFonti:\n- Titolo: Scapular kinematics and shoulder injury mechanisms during the bench press exercise • Journal of Shoulder and Elbow Surgery, Fonte: [https://www.jses.org/bench-press-scapular-stability](https://www.jses.org/bench-press-scapular-stability)\n- Titolo: Guida biomeccanica al setup perfetto nella panca piana - Powerlifting Italia, Fonte: [https://www.powerliftingitalia.it/setup-panca-piana](https://www.powerliftingitalia.it/setup-panca-piana)"

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
    
print(f"\nRisposta del modello:\n{pred_text}")