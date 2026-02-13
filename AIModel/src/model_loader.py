from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import torch
import os
from dotenv import load_dotenv

load_dotenv()

class DeepSeekLoader:
    def __init__(self, model_name="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"):
        """
        Initialize DeepSeek R1 model with stable 4-bit (FP4) quantization.
        Tailored for: NVIDIA MX230 (2GB VRAM) + 16GB System RAM.
        Strategy: Manual CPU mapping to avoid Meta-Tensor initialization crashes.
        """
        hf_token = os.getenv("HF_TOKEN")
        cache_dir = os.getenv("HF_HOME")
        
        if cache_dir:
            print(f"Directing download to custom location: {cache_dir}")
            os.makedirs(cache_dir, exist_ok=True)
            
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using primary device: {self.device}")
        
        # 1. Stable 4-bit Config
        # Using float32 for compute_dtype and fp4 for quant_type provides maximum stability 
        # for older mobile GPUs like the MX230.
        self.bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float32, 
            bnb_4bit_quant_type="fp4",            
            bnb_4bit_use_double_quant=True,
            llm_int8_enable_fp32_cpu_offload=True
        )

        print(f"Loading tokenizer for {model_name}...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            token=hf_token,
            cache_dir=cache_dir,
            trust_remote_code=True
        )
        
        print("Loading model... (Using manual CPU mapping to bypass Meta-Tensor errors)")
        
        # 2. Manual Device Mapping
        # By setting device_map={"": "cpu"}, we force the model into System RAM first.
        # This satisfies the requirement for low_cpu_mem_usage=True while avoiding 
        # the 'Tensor.item()' crash on meta-devices.
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            token=hf_token,
            quantization_config=self.bnb_config,
            device_map={"": "cpu"}, 
            cache_dir=cache_dir,
            offload_folder="E:/AIModel/offload",
            low_cpu_mem_usage=True,
            trust_remote_code=True
        )
        
        print("Model loaded successfully!")
    
    def generate_response(self, prompt, max_length=1024, temperature=0.1):
        """
        Generate response using memory-efficient inference.
        """
        # We move inputs to the designated device (CUDA/CPU)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_length,
                temperature=temperature,
                do_sample=True if temperature > 0 else False,
                top_p=0.95,
                pad_token_id=self.tokenizer.eos_token_id
            )
        
        return self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

# Singleton pattern
_model_instance = None

def get_model():
    global _model_instance
    if _model_instance is None:
        _model_instance = DeepSeekLoader()
    return _model_instance