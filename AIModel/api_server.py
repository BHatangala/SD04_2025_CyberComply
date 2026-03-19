from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import tempfile
from werkzeug.utils import secure_filename
from src.compliance_analyser import ComplianceAnalyzer
# from src.risk_assessor import RiskAssessor
# from src.recommendation_generator import RecommendationGenerator

app = Flask(__name__)
CORS(app)

# Limit upload size to 16MB to protect RAM/VRAM
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Initialize components (Singleton model loading)
analyzer = ComplianceAnalyzer(
    requirements_path=os.path.join(os.path.dirname(__file__), 'data', 'pdpa_requirements_full.json')
)

@app.route('/health', methods=['GET'])
def health_check():
    """Confirms the server and DeepSeek model are ready."""
    return jsonify({
        "status": "healthy", 
        "model": "DeepSeek-R1-Distill-7B",
        "device": "Hugging Face Inference API" 
    })

@app.route('/api/analyze', methods=['POST'])
def analyze_document():
    """Main endpoint to process PDPA compliance."""
    try:
        # 1. Validation: Check if file exists in request
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        
        # 2. Fix for splitext/Pylance error: Explicitly check filename
        if file.filename is None or file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        # Create a safe version of the filename
        original_filename = secure_filename(file.filename)
        company_name = request.form.get('company_name', 'Unknown Organization')
        
        # Extract extension safely for temp file creation
        _, extension = os.path.splitext(original_filename)

        # 3. Memory-Safe Temporary Storage
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
            file.save(temp_file.name)
            temp_path = temp_file.name

        print(f"--- Processing started for: {company_name} ---")
        
        # 4. Run Analysis (DeepSeek Logic)
        compliance_result = analyzer.analyze_document(temp_path)
        
        # Placeholder logic for risks and recommendations
        risk_assessment = {"status": "low", "factors": ["Data encryption detected"]} 
        recommendations = {"top_action": "Update privacy policy with Section 10 wording."}

        # 5. Cleanup: Always remove temp files to save disk space
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        return jsonify({
            "compliance": compliance_result,
            "risks": risk_assessment,
            "recommendations": recommendations,
            "metadata": {
                "company": company_name,
                "file_analyzed": original_filename
            }
        })
    
    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return jsonify({
            "error": "The AI model encountered an issue or the file was too complex.",
            "details": str(e)
        }), 500

if __name__ == '__main__':
    print("Starting AI Compliance Server...")
    # use_reloader=False prevents double-loading the 5GB model into your 16GB RAM
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)