from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import Optional
import os
import json
import uuid
from datetime import datetime
import base64
import google.generativeai as genai

# ----------------------------
# Environment variables
# ----------------------------
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')
CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '<YOUR_GEMINI_API_KEY>')

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

app = FastAPI(title="Food Calorie Tracker API (Gemini)")

# ----------------------------
# CORS middleware
# ----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS.split(",") if CORS_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# MongoDB connection
# ----------------------------
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# ----------------------------
# Pydantic Models
# ----------------------------
class FoodAnalysisRequest(BaseModel):
    image_base64: str
    weight_grams: Optional[float] = 100

# ----------------------------
# Helper: Analyze food with Gemini
# ----------------------------
async def analyze_food_with_gemini(image_bytes: bytes):
    try:
        # Base64 encode image
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # Prompt Gemini to return structured JSON
        query = """
        You are a nutritionist. Identify all food items in this meal image.
        It can be barcode of a packaged food item, or a dish like pasta, salad, etc.
        For each item, give nutritional breakdown for 100g in JSON with this structure:
        {
          "nutritional_breakdown_100g": [
            { "item": "Food name", "calories": XX, "protein_g": XX, "carbs_g": XX, "fats_g": XX }
          ]
        }
        Only return valid JSON.
        """

        response = gemini_model.generate_content(
            [query, {"mime_type": "image/jpeg", "data": image_bytes}]
        )

        # Clean and parse JSON
        clean_text = response.text.strip().replace("```json", "").replace("```", "")
        data = json.loads(clean_text)

        return data

    except Exception as e:
        print(f"Gemini API Error: {str(e)}")
        return None

# ----------------------------
# Routes
# ----------------------------
@app.get("/")
async def root():
    return {"message": "Food Calorie Tracker API (Gemini)", "status": "running"}

@app.post("/api/analyze-food")
async def analyze_food(request: FoodAnalysisRequest):
    """Analyze food from image and return nutritional information using Gemini"""
    try:
        # Decode base64 image
        image_data = base64.b64decode(
            request.image_base64.split(',')[1]
            if ',' in request.image_base64
            else request.image_base64
        )

        # Analyze with Gemini
        analysis_result = await analyze_food_with_gemini(image_data)

        if not analysis_result or "nutritional_breakdown_100g" not in analysis_result:
            raise HTTPException(status_code=400, detail="Failed to analyze food image with Gemini")

        weight_grams = request.weight_grams or 100
        scale_factor = weight_grams / 100

        adjusted_items = []
        for item in analysis_result["nutritional_breakdown_100g"]:
            adjusted_items.append({
                "item": item["item"],
                "weight_g": weight_grams,
                "calories": round(item["calories"] * scale_factor, 1),
                "protein_g": round(item["protein_g"] * scale_factor, 1),
                "carbs_g": round(item["carbs_g"] * scale_factor, 1),
                "fats_g": round(item["fats_g"] * scale_factor, 1),
            })

        return {
            "food_items": adjusted_items,
            "raw_response": analysis_result
        }

    except Exception as e:
        print(f"Food analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# ----------------------------
# Run the app
# ----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
