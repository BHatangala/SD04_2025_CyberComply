from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import torch
import os
from dotenv import load_dotenv

load_dotenv()

class DeepSeekLoader:
    def __init__(self, model_name="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"):
        hf_token = os.getenv("HF_TOKEN")
        cache_dir = os.getenv("HF_HOME")
        offload_path = "E:/AIModel/offload"

        if not os.path.exists(offload_path):
            os.makedirs(offload_path, exist_ok=True)
            
        self.device = "cpu"
        
        # 1. Simplified 4-bit Config for CPU stability
        self.bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            # This is critical for preventing the Meta-Tensor error on some systems
            llm_int8_enable_fp32_cpu_offload=True 
        )

        print(f"Loading tokenizer...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            token=hf_token,
            cache_dir=cache_dir
        )
        
        print("Loading model via Manual CPU Mapping (Bypassing Meta-Tensor logic)...")
        
        # 2. Force Load to CPU
        # We replace device_map="auto" with a hardcoded CPU mapping to avoid the .item() crash
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            token=hf_token,
            quantization_config=self.bnb_config,
            device_map={"": "cpu"}, 
            torch_dtype=torch.float16,
            cache_dir=cache_dir,
            offload_folder=offload_path,
            low_cpu_mem_usage=True,
            trust_remote_code=True
        )
        
        print("Model loaded successfully!")

    def generate_response(self, prompt, max_length=1024, temperature=0.1):
        # Everything stays on CPU
        print("AI is thinking... (Generating tokens on CPU)") # Log to terminal
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_length,
                temperature=temperature,
                do_sample=True if temperature > 0 else False,
                pad_token_id=self.tokenizer.eos_token_id
            )
        print("Generation complete!")
        return self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

_model_instance = None

def get_model():
    global _model_instance
    if _model_instance is None:
        _model_instance = DeepSeekLoader()
    return _model_instance