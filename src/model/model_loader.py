from transformers import AutoModelForCausalLM, AutoTokenizer

base_model_path = "./src/model/finetuned_model"

# Carichiamo il tokenizer e il modello 
tokenizer = AutoTokenizer.from_pretrained(base_model_path)
model = AutoModelForCausalLM.from_pretrained(base_model_path, device_map="auto")

def get_model_and_tokenizer():
    return model, tokenizer