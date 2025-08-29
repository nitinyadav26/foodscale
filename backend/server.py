from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import Optional, List
import os
import requests
import json
import uuid
from datetime import datetime, date
import base64
from PIL import Image
import io

# Environment variables
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')
CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')

# LogMeal API Configuration
LOGMEAL_API_TOKEN = "8dbce41a1c3e0dac3eb6a3016486d1cfea45e341"
LOGMEAL_HEADERS = {"Authorization": f"Bearer {LOGMEAL_API_TOKEN}"}
MODEL_VERSION = "v1.1"
TIMEOUT = 30

app = FastAPI(title="Food Calorie Tracker API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS.split(",") if CORS_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Pydantic Models
class UserProfile(BaseModel):
    user_id: str
    name: str
    age: int
    height: float  # cm
    weight: float  # kg
    gender: str
    activity_level: str
    goal_weight: Optional[float] = None
    daily_calorie_goal: Optional[float] = None
    created_at: datetime

class FoodLog(BaseModel):
    log_id: str
    user_id: str
    food_name: str
    calories_per_100g: float
    weight_grams: float
    total_calories: float
    protein: float
    carbs: float
    fat: float
    image_base64: str
    logged_at: datetime

class FoodAnalysisRequest(BaseModel):
    image_base64: str
    weight_grams: Optional[float] = 100

class CalorieGoalRequest(BaseModel):
    age: int
    height: float
    weight: float
    gender: str
    activity_level: str
    goal_weight: Optional[float] = None

# Helper Functions
def calculate_bmr(weight, height, age, gender):
    """Calculate Basal Metabolic Rate using Mifflin-St Jeor Equation"""
    if gender.lower() == 'male':
        return (10 * weight) + (6.25 * height) - (5 * age) + 5
    else:
        return (10 * weight) + (6.25 * height) - (5 * age) - 161

def get_activity_multiplier(activity_level):
    """Get activity multiplier for TDEE calculation"""
    multipliers = {
        'sedentary': 1.2,
        'lightly_active': 1.375,
        'moderately_active': 1.55,
        'very_active': 1.725,
        'extra_active': 1.9
    }
    return multipliers.get(activity_level.lower(), 1.2)

async def analyze_food_with_logmeal(image_bytes):
    """Analyze food using LogMeal API - Updated to match working implementation"""
    try:
        # Step 1: Image Segmentation (Single/Several Dishes Detection)
        url_segmentation = "https://api.logmeal.com/v2/image/segmentation/complete"
        files = {"image": ("food.jpg", image_bytes, "image/jpeg")}
        
        response = requests.post(url_segmentation, files=files, headers=LOGMEAL_HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        segmentation_data = response.json()
        
        image_id = segmentation_data.get("imageId")
        
        if not image_id:
            return None
            
        # Step 2: Nutritional Information  
        url_nutrition = "https://api.logmeal.com/v2/recipe/nutritionalInfo"
        nutrition_body = {"imageId": image_id}
        
        nutrition_response = requests.post(url_nutrition, headers=LOGMEAL_HEADERS, json=nutrition_body, timeout=TIMEOUT)
        nutrition_response.raise_for_status()
        nutrition_data = nutrition_response.json()
        
        return {
            "segmentation": segmentation_data,
            "nutrition": nutrition_data
        }
        
    except Exception as e:
        print(f"LogMeal API Error: {str(e)}")
        return None

# API Routes
@app.get("/")
async def root():
    return {"message": "Food Calorie Tracker API", "status": "running"}

@app.post("/api/calculate-calorie-goal")
async def calculate_calorie_goal(request: CalorieGoalRequest):
    """Calculate daily calorie goal based on user profile"""
    try:
        bmr = calculate_bmr(request.weight, request.height, request.age, request.gender)
        activity_multiplier = get_activity_multiplier(request.activity_level)
        tdee = bmr * activity_multiplier
        
        # Adjust for weight goal
        if request.goal_weight:
            weight_diff = request.goal_weight - request.weight
            # Rough calculation: 1 pound = 3500 calories, aim for 1-2 lbs per week
            calorie_adjustment = (weight_diff * 7700) / (12 * 7)  # 7700 cal per kg, 12 weeks timeline
            daily_goal = tdee + calorie_adjustment
        else:
            daily_goal = tdee
            
        return {
            "bmr": round(bmr),
            "tdee": round(tdee), 
            "daily_calorie_goal": round(daily_goal),
            "recommendation": "maintain" if not request.goal_weight else ("gain" if weight_diff > 0 else "lose")
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Calculation error: {str(e)}")

@app.post("/api/analyze-food")
async def analyze_food(request: FoodAnalysisRequest):
    """Analyze food from image and return nutritional information"""
    try:
        # Decode base64 image
        image_data = base64.b64decode(request.image_base64.split(',')[1] if ',' in request.image_base64 else request.image_base64)
        
        # Analyze with LogMeal API
        analysis_result = await analyze_food_with_logmeal(image_data)
        
        if not analysis_result:
            raise HTTPException(status_code=400, detail="Failed to analyze food image")
            
        recognition = analysis_result["recognition"]
        nutrition = analysis_result["nutrition"]
        
        # Extract food information
        food_items = recognition.get("recognition_results", [])
        if not food_items:
            raise HTTPException(status_code=400, detail="No food items detected in image")
            
        # Get primary food item (first one)
        primary_food = food_items[0]
        food_name = primary_food.get("name", "Unknown Food")
        
        # Extract nutrition per 100g
        nutrition_info = nutrition.get("nutritional_info", {})
        calories_per_100g = nutrition_info.get("calories", 0)
        protein_per_100g = nutrition_info.get("protein", 0)
        carbs_per_100g = nutrition_info.get("carbohydrates", 0)
        fat_per_100g = nutrition_info.get("fat", 0)
        
        # Scale nutrition based on weight
        weight_grams = request.weight_grams or 100
        scale_factor = weight_grams / 100
        
        scaled_nutrition = {
            "food_name": food_name,
            "weight_grams": weight_grams,
            "calories_per_100g": calories_per_100g,
            "total_calories": round(calories_per_100g * scale_factor, 1),
            "protein": round(protein_per_100g * scale_factor, 1),
            "carbs": round(carbs_per_100g * scale_factor, 1),
            "fat": round(fat_per_100g * scale_factor, 1),
            "confidence": primary_food.get("prob", 0),
            "raw_recognition": recognition,
            "raw_nutrition": nutrition
        }
        
        return scaled_nutrition
        
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
    image_base64: str = Form(...),
    user_id: str = Form(default="default_user")
):
    """Log food entry to database"""
    try:
        food_log = {
            "log_id": str(uuid.uuid4()),
            "user_id": user_id,
            "food_name": food_name,
            "calories_per_100g": (total_calories / weight_grams) * 100,
            "weight_grams": weight_grams,
            "total_calories": total_calories,
            "protein": protein,
            "carbs": carbs,
            "fat": fat,
            "image_base64": image_base64,
            "logged_at": datetime.utcnow()
        }
        
        await db.food_logs.insert_one(food_log)
        return {"message": "Food logged successfully", "log_id": food_log["log_id"]}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to log food: {str(e)}")

@app.get("/api/food-logs/{user_id}")
async def get_food_logs(user_id: str, date_filter: Optional[str] = None):
    """Get food logs for a user"""
    try:
        query = {"user_id": user_id}
        
        # Filter by date if provided
        if date_filter:
            start_date = datetime.strptime(date_filter, "%Y-%m-%d")
            end_date = start_date.replace(hour=23, minute=59, second=59)
            query["logged_at"] = {
                "$gte": start_date,
                "$lte": end_date
            }
        
        cursor = db.food_logs.find(query).sort("logged_at", -1)
        logs = await cursor.to_list(length=100)
        
        # Convert ObjectId to string and calculate totals
        total_calories = 0
        total_protein = 0
        total_carbs = 0
        total_fat = 0
        
        for log in logs:
            log["_id"] = str(log["_id"])
            total_calories += log["total_calories"]
            total_protein += log["protein"]
            total_carbs += log["carbs"]
            total_fat += log["fat"]
            
        return {
            "logs": logs,
            "daily_totals": {
                "calories": round(total_calories, 1),
                "protein": round(total_protein, 1),
                "carbs": round(total_carbs, 1),
                "fat": round(total_fat, 1)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get food logs: {str(e)}")

@app.delete("/api/food-logs/{log_id}")
async def delete_food_log(log_id: str):
    """Delete a food log entry"""
    try:
        result = await db.food_logs.delete_one({"log_id": log_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Food log not found")
        return {"message": "Food log deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete food log: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)