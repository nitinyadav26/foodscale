import React, { useState, useRef, useEffect } from 'react';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

function App() {
  // States
  const [currentView, setCurrentView] = useState('home');
  const [cameraActive, setCameraActive] = useState(false);
  const [capturedImage, setCapturedImage] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [foodAnalysis, setFoodAnalysis] = useState(null);
  const [foodLogs, setFoodLogs] = useState([]);
  const [dailyTotals, setDailyTotals] = useState({ calories: 0, protein: 0, carbs: 0, fat: 0 });
  const [weightGrams, setWeightGrams] = useState(100);
  const [userProfile, setUserProfile] = useState({
    age: 25,
    height: 170,
    weight: 70,
    gender: 'male',
    activity_level: 'moderately_active'
  });
  const [calorieGoal, setCalorieGoal] = useState(2000);

  // Refs
  const videoRef = useRef(null);
  const canvasRef = useRef(null);

  // Load food logs on mount
  useEffect(() => {
    loadFoodLogs();
  }, []);

  // Calculate calorie goal when profile changes
  useEffect(() => {
    calculateCalorieGoal();
  }, [userProfile]);

  // Camera Functions
  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: { 
          facingMode: 'environment',
          width: { ideal: 1920 },
          height: { ideal: 1080 }
        } 
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        setCameraActive(true);
      }
    } catch (error) {
      console.error('Error accessing camera:', error);
      alert('Could not access camera. Please ensure camera permissions are granted.');
    }
  };

  const stopCamera = () => {
    if (videoRef.current && videoRef.current.srcObject) {
      const stream = videoRef.current.srcObject;
      const tracks = stream.getTracks();
      tracks.forEach(track => track.stop());
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  };

  const capturePhoto = () => {
    if (videoRef.current && canvasRef.current) {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      const context = canvas.getContext('2d');

      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;

      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      
      const imageDataUrl = canvas.toDataURL('image/jpeg', 0.8);
      setCapturedImage(imageDataUrl);
      stopCamera();
      setCurrentView('analysis');
    }
  };

  // Food Analysis Functions
  const analyzeFood = async () => {
    if (!capturedImage) return;

    setAnalyzing(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/analyze-food`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          image_base64: capturedImage,
          weight_grams: weightGrams
        })
      });

      if (!response.ok) {
        throw new Error('Analysis failed');
      }

      const result = await response.json();
      setFoodAnalysis(result);
    } catch (error) {
      console.error('Analysis error:', error);
      alert('Failed to analyze food. Please try again.');
    } finally {
      setAnalyzing(false);
    }
  };

  const logFood = async () => {
    if (!foodAnalysis || !capturedImage) return;

    try {
      const formData = new FormData();
      formData.append('food_name', foodAnalysis.food_name);
      formData.append('total_calories', foodAnalysis.total_calories);
      formData.append('protein', foodAnalysis.protein);
      formData.append('carbs', foodAnalysis.carbs);
      formData.append('fat', foodAnalysis.fat);
      formData.append('weight_grams', weightGrams);
      formData.append('image_base64', capturedImage);
      formData.append('user_id', 'default_user');

      const response = await fetch(`${BACKEND_URL}/api/log-food`, {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        throw new Error('Failed to log food');
      }

      alert('Food logged successfully!');
      loadFoodLogs();
      setCurrentView('logs');
      setCapturedImage(null);
      setFoodAnalysis(null);
    } catch (error) {
      console.error('Logging error:', error);
      alert('Failed to log food. Please try again.');
    }
  };

  const loadFoodLogs = async () => {
    try {
      console.log('Loading food logs from:', `${BACKEND_URL}/api/food-logs/default_user`);
      const today = new Date().toISOString().split('T')[0];
      const response = await fetch(`${BACKEND_URL}/api/food-logs/default_user?date_filter=${today}`);
      
      console.log('Response status:', response.status);
      if (!response.ok) {
        throw new Error('Failed to load logs');
      }

      const data = await response.json();
      console.log('Loaded logs data:', data);
      setFoodLogs(data.logs);
      setDailyTotals(data.daily_totals);
    } catch (error) {
      console.error('Load logs error:', error);
    }
  };

  const deleteLog = async (logId) => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/food-logs/${logId}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        throw new Error('Failed to delete log');
      }

      loadFoodLogs();
    } catch (error) {
      console.error('Delete error:', error);
      alert('Failed to delete food log.');
    }
  };

  const calculateCalorieGoal = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/calculate-calorie-goal`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(userProfile)
      });

      if (!response.ok) {
        throw new Error('Failed to calculate calorie goal');
      }

      const result = await response.json();
      setCalorieGoal(result.daily_calorie_goal);
    } catch (error) {
      console.error('Calorie goal calculation error:', error);
    }
  };

  // Render Functions
  const renderHome = () => (
    <div className="home-view">
      <div className="hero-section">
        <h1 className="hero-title">Food Calorie Tracker</h1>
        <p className="hero-subtitle">
          Snap a photo of your food and instantly get detailed nutritional information
        </p>
        
        <div className="daily-summary">
          <h3>Today's Progress</h3>
          <div className="progress-card">
            <div className="calorie-circle">
              <div className="calorie-number">{Math.round(dailyTotals.calories)}</div>
              <div className="calorie-goal">/ {calorieGoal} cal</div>
            </div>
            <div className="macro-breakdown">
              <div className="macro-item">
                <span className="macro-label">Protein</span>
                <span className="macro-value">{dailyTotals.protein}g</span>
              </div>
              <div className="macro-item">
                <span className="macro-label">Carbs</span>
                <span className="macro-value">{dailyTotals.carbs}g</span>
              </div>
              <div className="macro-item">
                <span className="macro-label">Fat</span>
                <span className="macro-value">{dailyTotals.fat}g</span>
              </div>
            </div>
          </div>
        </div>

        <div className="action-buttons">
          <button 
            className="btn-primary"
            onClick={() => setCurrentView('camera')}
          >
            📱 Take Food Photo
          </button>
          <button 
            className="btn-secondary"
            onClick={() => setCurrentView('logs')}
          >
            📊 View Logs
          </button>
        </div>
      </div>
    </div>
  );

  const renderCamera = () => (
    <div className="camera-view">
      <div className="camera-header">
        <button 
          className="btn-back"
          onClick={() => {
            stopCamera();
            setCurrentView('home');
          }}
        >
          ← Back
        </button>
        <h2>Take Food Photo</h2>
      </div>

      <div className="camera-container">
        <video 
          ref={videoRef}
          autoPlay 
          playsInline
          style={{ display: cameraActive ? 'block' : 'none' }}
        />
        <canvas 
          ref={canvasRef} 
          style={{ display: 'none' }}
        />
        
        {!cameraActive && (
          <div className="camera-placeholder">
            <p>Camera not active</p>
            <button className="btn-primary" onClick={startCamera}>
              Start Camera
            </button>
          </div>
        )}
      </div>

      {cameraActive && (
        <div className="camera-controls">
          <button 
            className="btn-capture"
            onClick={capturePhoto}
          >
            📸 Capture Photo
          </button>
        </div>
      )}
    </div>
  );

  const renderAnalysis = () => (
    <div className="analysis-view">
      <div className="analysis-header">
        <button 
          className="btn-back"
          onClick={() => setCurrentView('camera')}
        >
          ← Back
        </button>
        <h2>Food Analysis</h2>
      </div>

      <div className="analysis-container">
        {capturedImage && (
          <div className="captured-image">
            <img src={capturedImage} alt="Captured food" />
          </div>
        )}

        <div className="weight-input">
          <label>Estimated Weight (grams):</label>
          <input
            type="number"
            value={weightGrams}
            onChange={(e) => setWeightGrams(Number(e.target.value))}
            min="1"
            max="2000"
          />
        </div>

        {!foodAnalysis && (
          <button 
            className="btn-primary"
            onClick={analyzeFood}
            disabled={analyzing}
          >
            {analyzing ? 'Analyzing...' : 'Analyze Food'}
          </button>
        )}

        {foodAnalysis && (
          <div className="analysis-results">
            <div className="food-info">
              <h3>{foodAnalysis.food_name}</h3>
              <p className="confidence">Confidence: {Math.round(foodAnalysis.confidence * 100)}%</p>
            </div>

            <div className="nutrition-card">
              <div className="nutrition-item main">
                <span className="nutrition-label">Total Calories</span>
                <span className="nutrition-value">{foodAnalysis.total_calories} cal</span>
              </div>
              <div className="nutrition-grid">
                <div className="nutrition-item">
                  <span className="nutrition-label">Protein</span>
                  <span className="nutrition-value">{foodAnalysis.protein}g</span>
                </div>
                <div className="nutrition-item">
                  <span className="nutrition-label">Carbs</span>
                  <span className="nutrition-value">{foodAnalysis.carbs}g</span>
                </div>
                <div className="nutrition-item">
                  <span className="nutrition-label">Fat</span>
                  <span className="nutrition-value">{foodAnalysis.fat}g</span>
                </div>
              </div>
            </div>

            <button 
              className="btn-primary"
              onClick={logFood}
            >
              Log This Food
            </button>
          </div>
        )}
      </div>
    </div>
  );

  const renderLogs = () => (
    <div className="logs-view">
      <div className="logs-header">
        <button 
          className="btn-back"
          onClick={() => setCurrentView('home')}
        >
          ← Back
        </button>
        <h2>Today's Food Log</h2>
      </div>

      <div className="logs-summary">
        <div className="summary-card">
          <h3>Daily Totals</h3>
          <div className="summary-grid">
            <div className="summary-item">
              <span className="summary-label">Calories</span>
              <span className="summary-value">{Math.round(dailyTotals.calories)}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Protein</span>
              <span className="summary-value">{dailyTotals.protein}g</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Carbs</span>
              <span className="summary-value">{dailyTotals.carbs}g</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Fat</span>
              <span className="summary-value">{dailyTotals.fat}g</span>
            </div>
          </div>
        </div>
      </div>

      <div className="logs-list">
        {foodLogs.length === 0 ? (
          <div className="no-logs">
            <p>No food logged today</p>
            <button 
              className="btn-primary"
              onClick={() => setCurrentView('camera')}
            >
              Log Your First Meal
            </button>
          </div>
        ) : (
          foodLogs.map(log => (
            <div key={log.log_id} className="log-item">
              <div className="log-image">
                <img src={log.image_base64} alt={log.food_name} />
              </div>
              <div className="log-info">
                <h4>{log.food_name}</h4>
                <p>{log.weight_grams}g • {Math.round(log.total_calories)} calories</p>
                <div className="log-macros">
                  <span>P: {log.protein}g</span>
                  <span>C: {log.carbs}g</span>
                  <span>F: {log.fat}g</span>
                </div>
              </div>
              <button 
                className="btn-delete"
                onClick={() => deleteLog(log.log_id)}
              >
                🗑️
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );

  return (
    <div className="App">
      {currentView === 'home' && renderHome()}
      {currentView === 'camera' && renderCamera()}
      {currentView === 'analysis' && renderAnalysis()}
      {currentView === 'logs' && renderLogs()}
    </div>
  );
}

export default App;