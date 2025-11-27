from fastapi import FastAPI, HTTPException, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os
import json
import uuid
from datetime import datetime
import base64
import google.generativeai as genai
from dotenv import load_dotenv
from google.api_core.exceptions import ResourceExhausted
import sqlite3

# Load environment variables
load_dotenv()

# ----------------------------
# Environment variables
# ----------------------------
CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '<YOUR_GEMINI_API_KEY>')
DB_NAME = "foodscale.db"

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.0-flash-exp")

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
# Database Setup
# ----------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS food_logs (
            log_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            food_name TEXT NOT NULL,
            total_calories REAL,
            protein REAL,
            carbs REAL,
            fat REAL,
            weight_grams REAL,
            image_base64 TEXT,
            created_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# ----------------------------
# Pydantic Models
# ----------------------------
class FoodAnalysisRequest(BaseModel):
    image_base64: str
    weight_grams: Optional[float] = 100

class FoodLog(BaseModel):
    log_id: Optional[str] = None
    user_id: str
    food_name: str
    total_calories: float
    protein: float
    carbs: float
    fat: float
    weight_grams: float
    image_base64: Optional[str] = None
    created_at: Optional[datetime] = None

class UserProfile(BaseModel):
    age: int
    height: float  # in cm
    weight: float  # in kg
    gender: str  # 'male' or 'female'
    activity_level: str  # 'sedentary', 'lightly_active', 'moderately_active', 'active', 'very_active'

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

    except ResourceExhausted as e:
        print(f"Gemini Quota Exceeded: {str(e)}")
        raise HTTPException(status_code=429, detail="Gemini API quota exceeded. Please try again in a minute.")
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
        total_cals = 0
        total_protein = 0
        total_carbs = 0
        total_fat = 0
        food_names = []

        for item in analysis_result["nutritional_breakdown_100g"]:
            cals = round(item["calories"] * scale_factor, 1)
            prot = round(item["protein_g"] * scale_factor, 1)
            carbs = round(item["carbs_g"] * scale_factor, 1)
            fat = round(item["fats_g"] * scale_factor, 1)
            
            adjusted_items.append({
                "item": item["item"],
                "weight_g": weight_grams,
                "calories": cals,
                "protein_g": prot,
                "carbs_g": carbs,
                "fats_g": fat,
            })
            
            total_cals += cals
            total_protein += prot
            total_carbs += carbs
            total_fat += fat
            food_names.append(item["item"])

        return {
            "food_items": adjusted_items,
            "food_name": ", ".join(food_names),
            "total_calories": round(total_cals, 1),
            "protein": round(total_protein, 1),
            "carbs": round(total_carbs, 1),
            "fat": round(total_fat, 1),
            "confidence": 0.9, # Placeholder confidence
            "raw_response": analysis_result
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Food analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/api/log-food")
async def log_food(
    food_name: str = Form(...),
    total_calories: float = Form(...),
    protein: float = Form(...),
    carbs: float = Form(...),
    fat: float = Form(...),
    weight_grams: float = Form(...),
    user_id: str = Form(...),
    image_base64: Optional[str] = Form(None)
):
    try:
        log_id = str(uuid.uuid4())
        created_at = datetime.now()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO food_logs (log_id, user_id, food_name, total_calories, protein, carbs, fat, weight_grams, image_base64, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (log_id, user_id, food_name, total_calories, protein, carbs, fat, weight_grams, image_base64, created_at))
        conn.commit()
        conn.close()
        
        return {"log_id": log_id, "message": "Food logged successfully"}
        
    except Exception as e:
        print(f"Logging error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to log food: {str(e)}")

@app.get("/api/food-logs/{user_id}")
async def get_food_logs(user_id: str, date_filter: Optional[str] = None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM food_logs WHERE user_id = ?"
        params = [user_id]
        
        if date_filter:
            # SQLite stores datetime as string, so we need to filter by date string
            # Assuming date_filter is YYYY-MM-DD
            query += " AND date(created_at) = date(?)"
            params.append(date_filter)
            
        query += " ORDER BY created_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        logs = []
        daily_totals = {
            "calories": 0,
            "protein": 0,
            "carbs": 0,
            "fat": 0
        }
        
        for row in rows:
            logs.append({
                "log_id": row["log_id"],
                "food_name": row["food_name"],
                "total_calories": row["total_calories"],
                "protein": row["protein"],
                "carbs": row["carbs"],
                "fat": row["fat"],
                "weight_grams": row["weight_grams"],
                "image_base64": row["image_base64"],
                "created_at": row["created_at"]
            })
            
            daily_totals["calories"] += row["total_calories"]
            daily_totals["protein"] += row["protein"]
            daily_totals["carbs"] += row["carbs"]
            daily_totals["fat"] += row["fat"]
            
        return {
            "logs": logs,
            "daily_totals": daily_totals
        }
        
    except Exception as e:
        print(f"Get logs error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get logs: {str(e)}")

@app.delete("/api/food-logs/{log_id}")
async def delete_food_log(log_id: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM food_logs WHERE log_id = ?", (log_id,))
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        if rows_affected == 0:
            raise HTTPException(status_code=404, detail="Log not found")
            
        return {"message": "Log deleted successfully"}
        
    except Exception as e:
        print(f"Delete log error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete log: {str(e)}")

@app.post("/api/calculate-calorie-goal")
async def calculate_calorie_goal(profile: UserProfile):
    try:
        # Mifflin-St Jeor Equation
        if profile.gender.lower() == 'male':
            bmr = (10 * profile.weight) + (6.25 * profile.height) - (5 * profile.age) + 5
        else:
            bmr = (10 * profile.weight) + (6.25 * profile.height) - (5 * profile.age) - 161
            
        activity_multipliers = {
            'sedentary': 1.2,
            'lightly_active': 1.375,
            'moderately_active': 1.55,
            'active': 1.725,
            'very_active': 1.9
        }
        
        multiplier = activity_multipliers.get(profile.activity_level, 1.2)
        daily_calories = round(bmr * multiplier)
        
        return {"daily_calorie_goal": daily_calories}
        
    except Exception as e:
        print(f"Calorie calculation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to calculate goal: {str(e)}")

# ----------------------------
# Run the app
# ----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
