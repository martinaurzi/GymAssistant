from transformers import AutoModelForCausalLM, AutoTokenizer
#import bitsandbytes 
#from peft import PeftModel

base_model_path = "./src/model/finetuned_model"
tokenizer = AutoTokenizer.from_pretrained(base_model_path)
model = AutoModelForCausalLM.from_pretrained(base_model_path)

def get_model_and_tokenizer():
    return model, tokenizer