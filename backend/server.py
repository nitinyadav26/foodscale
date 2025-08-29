from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import os
import requests
import json
import uuid
from datetime import datetime, date, timedelta
import base64
from PIL import Image
import io
import hashlib
import jwt
from passlib.context import CryptContext

# Environment variables
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')
CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')

# LogMeal API Configuration
LOGMEAL_API_TOKEN = "8dbce41a1c3e0dac3eb6a3016486d1cfea45e341"
LOGMEAL_HEADERS = {"Authorization": f"Bearer {LOGMEAL_API_TOKEN}"}
TIMEOUT = 30

# JWT Configuration
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

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

# Authentication
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Pydantic Models
class UserRegistration(BaseModel):
    email: EmailStr
    password: str
    name: str
    age: int
    height: float  # cm
    weight: float  # kg
    gender: str
    activity_level: str
    goal_weight: Optional[float] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserProfile(BaseModel):
    user_id: str
    email: str
    name: str
    age: int
    height: float  # cm
    weight: float  # kg
    gender: str
    activity_level: str
    goal_weight: Optional[float] = None
    daily_calorie_goal: Optional[float] = None
    created_at: datetime
    streak_count: int = 0
    total_foods_logged: int = 0
    badges: List[str] = []

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
    
class BluetoothWeightRequest(BaseModel):
    weight_grams: float
    user_id: str

class NutritionDisplay(BaseModel):
    food_name: str
    weight_grams: float
    total_calories: float
    protein: float
    carbs: float
    fat: float
    analyzed_at: datetime
    confidence: float

class DisplayData(BaseModel):
    status: str
    nutrition: Optional[NutritionDisplay] = None
    message: str

class Token(BaseModel):
    access_token: str
    token_type: str

# Helper Functions
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    
    user = await db.users.find_one({"email": email})
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

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

async def update_user_streak(user_id: str):
    """Update user's logging streak"""
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        return
        
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    
    # Check if user logged food today
    today_logs = await db.food_logs.find_one({
        "user_id": user_id,
        "logged_at": {
            "$gte": datetime.combine(today, datetime.min.time()),
            "$lt": datetime.combine(today + timedelta(days=1), datetime.min.time())
        }
    })
    
    if not today_logs:
        return  # No logs today, don't update streak
    
    # Check if user logged yesterday
    yesterday_logs = await db.food_logs.find_one({
        "user_id": user_id,
        "logged_at": {
            "$gte": datetime.combine(yesterday, datetime.min.time()),
            "$lt": datetime.combine(today, datetime.min.time())
        }
    })
    
    if yesterday_logs:
        # Continue streak
        await db.users.update_one(
            {"user_id": user_id},
            {"$inc": {"streak_count": 1}}
        )
    else:
        # Reset streak
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"streak_count": 1}}
        )

async def check_and_award_badges(user_id: str):
    """Check and award badges based on user activity"""
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        return
    
    new_badges = []
    current_badges = user.get("badges", [])
    
    # Badge: First Food Log
    if user.get("total_foods_logged", 0) >= 1 and "first_log" not in current_badges:
        new_badges.append("first_log")
    
    # Badge: 7-Day Streak
    if user.get("streak_count", 0) >= 7 and "week_warrior" not in current_badges:
        new_badges.append("week_warrior")
    
    # Badge: 30-Day Streak
    if user.get("streak_count", 0) >= 30 and "month_master" not in current_badges:
        new_badges.append("month_master")
    
    # Badge: 100 Foods Logged
    if user.get("total_foods_logged", 0) >= 100 and "century_tracker" not in current_badges:
        new_badges.append("century_tracker")
    
    if new_badges:
        await db.users.update_one(
            {"user_id": user_id},
            {"$addToSet": {"badges": {"$each": new_badges}}}
        )
        return new_badges
    
    return []

# API Routes
@app.get("/")
async def root():
    return {"message": "Food Calorie Tracker API", "status": "running"}

# Authentication Routes
@app.post("/api/register", response_model=Token)
async def register_user(user_data: UserRegistration):
    """Register a new user"""
    try:
        # Check if user already exists
        existing_user = await db.users.find_one({"email": user_data.email})
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Hash password
        hashed_password = hash_password(user_data.password)
        
        # Calculate daily calorie goal
        bmr = calculate_bmr(user_data.weight, user_data.height, user_data.age, user_data.gender)
        activity_multiplier = get_activity_multiplier(user_data.activity_level)
        tdee = bmr * activity_multiplier
        
        if user_data.goal_weight:
            weight_diff = user_data.goal_weight - user_data.weight
            calorie_adjustment = (weight_diff * 7700) / (12 * 7)  # 7700 cal per kg, 12 weeks timeline
            daily_goal = tdee + calorie_adjustment
        else:
            daily_goal = tdee
        
        # Create user
        user_id = str(uuid.uuid4())
        user = {
            "user_id": user_id,
            "email": user_data.email,
            "password": hashed_password,
            "name": user_data.name,
            "age": user_data.age,
            "height": user_data.height,
            "weight": user_data.weight,
            "gender": user_data.gender,
            "activity_level": user_data.activity_level,
            "goal_weight": user_data.goal_weight,
            "daily_calorie_goal": round(daily_goal),
            "created_at": datetime.utcnow(),
            "streak_count": 0,
            "total_foods_logged": 0,
            "badges": []
        }
        
        await db.users.insert_one(user)
        
        # Create access token
        access_token = create_access_token(data={"sub": user_data.email})
        
        return {"access_token": access_token, "token_type": "bearer"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/api/login", response_model=Token)
async def login_user(user_credentials: UserLogin):
    """Login user"""
    try:
        user = await db.users.find_one({"email": user_credentials.email})
        if not user or not verify_password(user_credentials.password, user["password"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        access_token = create_access_token(data={"sub": user_credentials.email})
        return {"access_token": access_token, "token_type": "bearer"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.get("/api/profile")
async def get_user_profile(current_user: dict = Depends(get_current_user)):
    """Get user profile"""
    current_user.pop("password", None)  # Remove password from response
    current_user["_id"] = str(current_user["_id"])
    return current_user

# Existing Food Tracking Routes (Enhanced with User Authentication)
@app.post("/api/analyze-food")
async def analyze_food(request: FoodAnalysisRequest):
    """Analyze food from image and return nutritional information"""
    try:
        # Decode base64 image
        try:
            if request.image_base64.startswith('data:'):
                # Handle data URL format
                header, encoded = request.image_base64.split(',', 1)
                image_data = base64.b64decode(encoded)
            else:
                # Handle raw base64
                image_data = base64.b64decode(request.image_base64)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64 image data: {str(e)}")
        
        # Analyze with LogMeal API
        analysis_result = await analyze_food_with_logmeal(image_data)
        
        if not analysis_result:
            raise HTTPException(status_code=400, detail="Failed to analyze food image")
            
        # Extract food information based on working API structure
        segmentation = analysis_result["segmentation"] 
        nutrition = analysis_result["nutrition"]
        
        # Get food names from nutrition data
        food_names = nutrition.get("foodName", ["Unknown Food"])
        primary_food_name = food_names[0] if food_names else "Unknown Food"
        
        # Extract nutrition per 100g from working API structure
        nutrition_info = nutrition.get("nutritional_info", {})
        calories_per_100g = nutrition_info.get("calories", 0)
        
        # Extract macronutrients from totalNutrients structure
        total_nutrients = nutrition_info.get("totalNutrients", {})
        protein_per_100g = total_nutrients.get("PROCNT", {}).get("quantity", 0) if total_nutrients.get("PROCNT") else 0
        carbs_per_100g = total_nutrients.get("CHOCDF", {}).get("quantity", 0) if total_nutrients.get("CHOCDF") else 0
        fat_per_100g = total_nutrients.get("FAT", {}).get("quantity", 0) if total_nutrients.get("FAT") else 0
        
        # Scale nutrition based on weight
        weight_grams = request.weight_grams or 100
        scale_factor = weight_grams / 100
        
        scaled_nutrition = {
            "food_name": primary_food_name,
            "weight_grams": weight_grams,
            "calories_per_100g": calories_per_100g,
            "total_calories": round(calories_per_100g * scale_factor, 1),
            "protein": round(protein_per_100g * scale_factor, 1),
            "carbs": round(carbs_per_100g * scale_factor, 1),
            "fat": round(fat_per_100g * scale_factor, 1),
            "confidence": 0.8,  # Default confidence since we don't have recognition results
            "raw_segmentation": segmentation,  # Use segmentation data instead
            "raw_nutrition": nutrition
        }
        
        return scaled_nutrition
        
    except Exception as e:
        print(f"Food analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/api/store-nutrition-display")
async def store_nutrition_display(nutrition: NutritionDisplay):
    """Store nutrition data for LCD display"""
    try:
        # Store the nutrition data with timestamp
        nutrition_data = nutrition.dict()
        nutrition_data["stored_at"] = datetime.utcnow()
        
        # Store in a separate collection for LCD display
        await db.nutrition_display.insert_one(nutrition_data)
        
        # Keep only the latest 10 entries (cleanup old data)
        cursor = db.nutrition_display.find().sort("stored_at", -1).skip(10)
        old_records = await cursor.to_list(length=None)
        
        if old_records:
            old_ids = [record["_id"] for record in old_records]
            await db.nutrition_display.delete_many({"_id": {"$in": old_ids}})
        
        return {"message": "Nutrition data stored for LCD display", "status": "success"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store nutrition data: {str(e)}")

@app.get("/api/lcd-display", response_model=DisplayData)
async def get_nutrition_for_lcd():
    """API endpoint for LCD display to get latest nutrition information - NO AUTH REQUIRED"""
    try:
        # Get the most recent nutrition analysis
        latest_analysis = await db.nutrition_display.find_one(
            {},
            sort=[("stored_at", -1)]
        )
        
        if not latest_analysis:
            return DisplayData(
                status="no_data",
                nutrition=None,
                message="No nutrition data available"
            )
        
        # Convert to response format
        nutrition_data = NutritionDisplay(
            food_name=latest_analysis["food_name"],
            weight_grams=latest_analysis["weight_grams"],
            total_calories=latest_analysis["total_calories"],
            protein=latest_analysis["protein"],
            carbs=latest_analysis["carbs"],
            fat=latest_analysis["fat"],
            analyzed_at=latest_analysis["analyzed_at"],
            confidence=latest_analysis["confidence"]
        )
        
        return DisplayData(
            status="success",
            nutrition=nutrition_data,
            message="Latest nutrition data retrieved"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get LCD display data: {str(e)}")

@app.get("/api/lcd-display/simple")
async def get_simple_nutrition_for_lcd():
    """Simplified API endpoint for basic LCD displays (plain text format)"""
    try:
        # Get the most recent nutrition analysis
        latest_analysis = await db.nutrition_display.find_one(
            {},
            sort=[("stored_at", -1)]
        )
        
        if not latest_analysis:
            return {
                "status": "no_data",
                "display_text": "No data available"
            }
        
        # Create simple display format
        display_text = f"Food: {latest_analysis['food_name']}\n"
        display_text += f"Weight: {latest_analysis['weight_grams']}g\n"
        display_text += f"Calories: {latest_analysis['total_calories']} cal\n"
        display_text += f"Protein: {latest_analysis['protein']}g\n"
        display_text += f"Carbs: {latest_analysis['carbs']}g\n"
        display_text += f"Fat: {latest_analysis['fat']}g"
        
        return {
            "status": "success",
            "food_name": latest_analysis["food_name"],
            "weight_grams": latest_analysis["weight_grams"],
            "calories": latest_analysis["total_calories"],
            "protein": latest_analysis["protein"],
            "carbs": latest_analysis["carbs"],
            "fat": latest_analysis["fat"],
            "confidence": latest_analysis["confidence"],
            "display_text": display_text,
            "analyzed_at": latest_analysis["analyzed_at"].isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get simple LCD data: {str(e)}")

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
    """Log food entry to database with gamification"""
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
        
        # Update user statistics
        await db.users.update_one(
            {"user_id": user_id},
            {"$inc": {"total_foods_logged": 1}}
        )
        
        # Update streak
        await update_user_streak(user_id)
        
        # Check for new badges
        new_badges = await check_and_award_badges(user_id)
        
        response = {"message": "Food logged successfully", "log_id": food_log["log_id"]}
        if new_badges:
            response["new_badges"] = new_badges
            
        return response
        
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

# Bluetooth Weight Scale Integration
@app.post("/api/bluetooth-weight")
async def receive_bluetooth_weight(request: BluetoothWeightRequest):
    """Receive weight data from Bluetooth scale"""
    try:
        # Store weight measurement
        weight_record = {
            "measurement_id": str(uuid.uuid4()),
            "user_id": request.user_id,
            "weight_grams": request.weight_grams,
            "measured_at": datetime.utcnow()
        }
        
        await db.weight_measurements.insert_one(weight_record)
        
        return {
            "message": "Weight recorded successfully",
            "weight_grams": request.weight_grams,
            "measurement_id": weight_record["measurement_id"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record weight: {str(e)}")

@app.get("/api/user-stats/{user_id}")
async def get_user_stats(user_id: str):
    """Get comprehensive user statistics"""
    try:
        user = await db.users.find_one({"user_id": user_id})
        
        # Get food logging statistics
        total_logs = await db.food_logs.count_documents({"user_id": user_id})
        
        # If user doesn't exist in users collection, return default stats
        if not user:
            return {
                "user_id": user_id,
                "streak_count": 0,
                "total_foods_logged": total_logs,
                "badges": [],
                "daily_calorie_goal": 2000
            }
        
        # Get current streak
        current_streak = user.get("streak_count", 0)
        
        # Get badges
        badges = user.get("badges", [])
        
        # Badge descriptions
        badge_info = {
            "first_log": {"name": "First Steps", "description": "Logged your first meal"},
            "week_warrior": {"name": "Week Warrior", "description": "7-day logging streak"},
            "month_master": {"name": "Month Master", "description": "30-day logging streak"},
            "century_tracker": {"name": "Century Tracker", "description": "100 foods logged"}
        }
        
        user_badges = [{"id": badge, **badge_info.get(badge, {"name": badge, "description": "Achievement unlocked"})} for badge in badges]
        
        return {
            "user_id": user_id,
            "streak_count": current_streak,
            "total_foods_logged": total_logs,
            "badges": user_badges,
            "daily_calorie_goal": user.get("daily_calorie_goal", 2000)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user stats: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)